"""ModelResolver: one id in, everything a child process needs out. The single resolution path.

Seven steps (03 §The resolution pipeline), and no vendor branch among them:

1. parse and canonicalise the id (`domain/llm/model.py`, A1)
2. alias-map a legacy id (A1, NFR-7)
3. find the row in the catalogue (`ModelService`, A1)
4. authorise (`domain/llm/policy.py`)
5. resolve the provider descriptor (`adapters/llm/providers/*`, A2)
6. clamp the limits (`domain/llm/limits.py`, A3)
7. find the credential **reference** — never the secret (`CredentialService`, A4)

`resolve()` returns a `ResolvedModel` and an optional `Secret`. The secret is separate because the
`ResolvedModel` is a fact that gets recorded, and a fact must never contain a key.
"""

from __future__ import annotations

import logging
import time

from ..adapters.llm.providers import adapter_for
from ..domain.llm import (
    Capability,
    CredentialKind,
    CredentialSource,
    ModelId,
    ModelSpec,
    ModelState,
    NoCredential,
    ProviderKind,
    ResolvedModel,
    UnknownModel,
    WireProtocol,
    agent_prefix,
    clamp,
    may_use,
)
from ..ports import Secret

log = logging.getLogger("app.llm.resolve")


class ModelResolver:
    """`id -> ResolvedModel`. I/O only through the catalogue and the credential service."""

    def __init__(self, catalogue, credentials, *, host: str = "", allow_external: bool = True) -> None:
        self._catalogue = catalogue
        self._credentials = credentials
        self._host = host
        self._allow_external = allow_external

    async def resolve(self, model_id: str, *, user_id: str, session_id: str = "",
                      groups: frozenset[str] = frozenset(), with_secret: bool = False,
                      ) -> tuple[ResolvedModel, Secret | None]:
        """The whole pipeline. Raises a typed `ModelError`; never returns a half-built model.

        `with_secret=False` is the default because most callers — the picker, the inspector, the turn
        pin — need the facts and must not touch a key. Only a spawn asks for the secret.
        """
        # 1 + 2. parse, canonicalise, alias-map
        mid = ModelId.parse(model_id)
        # 3. the row
        spec = await self._catalogue.find(mid.value, user_id)
        if spec is None:
            raise UnknownModel(mid.value)
        if not self._allow_external and spec.id.provider not in (ProviderKind.DATABRICKS,
                                                                ProviderKind.FAKE):
            from ..domain.llm import NotSelectable

            raise NotSelectable(mid.value, "external providers are disabled in this workspace")
        # 4. authorise
        grant = await self._catalogue.grant_for(mid.value)
        may_use(spec, user_id, grant, groups).raise_if_denied(spec)

        # 5. the descriptor, from the adapter that owns this wire
        adapter = adapter_for(spec.id.provider)
        project = ""
        secret: Secret | None = None
        ref_id = ""
        source = CredentialSource.WORKSPACE_TOKEN if spec.id.provider is ProviderKind.DATABRICKS \
            else CredentialSource.NONE

        if spec.credential_kind is not CredentialKind.NONE:
            found = await self._credentials.find(spec.id.provider, user_id=user_id)
            if found is None:
                raise NoCredential(mid.value, spec.provider_name)
            ref_id = found.id
            source = (CredentialSource.ENV if found.id.startswith("env:")
                      else CredentialSource.USER if found.scope_kind == "user"
                      else CredentialSource.WORKSPACE)
            if spec.id.provider is ProviderKind.GOOGLE_VERTEX:
                project = found.project_hint

        desc = adapter.descriptor(spec, host=self._host, project=project)

        # 6. the limits, clamped. This is the only number the app ever asks for.
        limits = clamp(spec.limits,
                       requested_context=spec.limits.context,
                       requested_output=spec.limits.output)

        wire = _wire_for(spec)
        resolved = ResolvedModel(
            id=spec.id,
            provider=spec.id.provider,
            wire=wire,
            endpoint=desc.agent_key or desc.model_key,
            base_url=desc.base_url,
            limits=limits,
            capability=spec.capability,
            # The declared fact travels with the resolution, so the agent file can state it.
            sees_images=bool(getattr(spec, "sees_images", False)),
            env_var=adapter.env_var(spec) if spec.credential_kind is not CredentialKind.NONE else "",
            npm=desc.npm,
            options=_options(desc),
            agent_id=_agent_id(spec, desc.agent_key or desc.model_key, wire),
            credential_ref=ref_id or _workspace_ref(spec),
            credential_source=source,
        )

        # 7. the secret, only when the caller is about to spawn
        if with_secret and spec.credential_kind is not CredentialKind.NONE:
            secret = await self._credentials.open_ref(ref_id, user_id=user_id, session_id=session_id)
        self._log(resolved, source)
        return resolved, secret

    async def options(self, user_id: str, *, groups: frozenset[str] = frozenset()) -> list[ModelSpec]:
        """The catalogue, as the picker sees it. No secrets are touched."""
        cat = await self._catalogue.catalogue(user_id, groups)
        return list(cat.models)

    def _log(self, resolved: ResolvedModel, source: CredentialSource) -> None:
        """One structured line per resolution (NFR-8). Never the secret, only its source."""
        log.info("llm.resolve model=%s provider=%s wire=%s credential=%s outcome=ok",
                 resolved.id.value, resolved.provider.value, resolved.wire.value, source.value)


def _wire_for(spec: ModelSpec) -> WireProtocol:
    """A spec's declared wire, or the adapter's default for a row that omits it."""
    if spec.wire is not None:
        return spec.wire
    return adapter_for(spec.id.provider).wire  # type: ignore[attr-defined]


def _options(desc) -> dict:
    """Provider options the agent needs, flattened for the config writer. Templated only."""
    out: dict = {}
    if desc.extra_headers:
        out["headers"] = dict(desc.extra_headers)
    if desc.extra_body:
        out.update(dict(desc.extra_body))
    if not desc.tool_streaming:
        out["toolStreaming"] = False
    return out


def _agent_id(spec: ModelSpec, model_key: str, wire: WireProtocol) -> str:
    """The id the agent itself advertises, when the dialects differ (E-21).

    The agent's catalogue is `<provider-prefix>/<model key>`; the app stores `<provider>/<model>`. This
    is the single place the two are related, so `set_model` sends a value the agent knows.
    """
    if spec.id.provider is ProviderKind.FAKE:
        return model_key
    return f"{agent_prefix(spec.id.provider, wire)}/{model_key}"


def _workspace_ref(spec: ModelSpec) -> str:
    """The audit reference for a model whose credential is the workspace token."""
    return "workspace-token" if spec.id.provider is ProviderKind.DATABRICKS else ""


def capability_or_default(value: str | None) -> Capability:
    try:
        return Capability(value or Capability.TOOLS.value)
    except ValueError:
        return Capability.TOOLS


def state_rank(state: ModelState) -> int:
    """Lower is better. Shared with the picker's ordering so the two cannot disagree."""
    return {
        ModelState.AVAILABLE: 0,
        ModelState.UNKNOWN: 1,
        ModelState.DEGRADED: 2,
        ModelState.UNAUTHORISED: 3,
        ModelState.NOT_ENABLED: 4,
        ModelState.NOT_SERVED: 5,
    }.get(state, 9)


def now() -> float:
    return time.time()
