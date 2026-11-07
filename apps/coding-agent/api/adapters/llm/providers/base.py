"""The adapter contract, and the one behaviour every adapter shares: a bounded probe.

Concrete adapters supply four things and inherit the rest:

* `kind` — the provider kind this class serves;
* `npm` — the package the agent needs for this wire;
* `base_url(spec, host, project)` — the URL the wire expects;
* `probe(...)` — one cheap call, classified.

`descriptor()` and `env_var()` are the interface the resolver uses; they are written once here so
four adapters cannot disagree about the shape.
"""

from __future__ import annotations

from typing import Any

import httpx

from ....domain.llm import ModelSpec, ProviderKind, ResolvedModel, WireProtocol
from ....ports import ChildEnv, ProviderDescriptor, Secret

#: One fixed variable name for every external provider (D4). Fewer names, fewer leaks: the config
#: references `{env:LLM_PROVIDER_KEY}` and never a vendor's own variable.
PROVIDER_KEY_ENV = "LLM_PROVIDER_KEY"
#: The workspace token, the only credential a Databricks model needs.
WORKSPACE_TOKEN_ENV = "DATABRICKS_TOKEN"

PROBE_TIMEOUT = 12.0


class BaseAdapter:
    """Shared plumbing. A subclass that overrides `descriptor` breaks the contract, not the build."""

    kind: ProviderKind
    npm: str = "@ai-sdk/openai-compatible"
    wire: WireProtocol = WireProtocol.OPENAI
    #: Whether the wire needs the credential as an `Authorization: Bearer` header (probe only).
    bearer: bool = True

    def descriptor(self, spec: ModelSpec, *, host: str = "", project: str = "") -> ProviderDescriptor:
        return ProviderDescriptor(
            kind=self.kind,
            wire=spec.wire,
            base_url=self.base_url(spec, host=host, project=project),
            npm=self.npm,
            model_key=spec.endpoint,
            tool_streaming=self.tool_streaming(spec),
            extra_headers=self.headers(spec),
            extra_body=self.extra_body(spec),
            agent_key=self.agent_key(spec),
        )

    def agent_key(self, spec: ModelSpec) -> str:
        """The model's name in the agent's catalogue. Same as the API's name unless overridden."""
        return spec.endpoint

    def base_url(self, spec: ModelSpec, *, host: str = "", project: str = "") -> str:
        raise NotImplementedError

    def tool_streaming(self, spec: ModelSpec) -> bool:
        """Off where a documented trap requires it (Anthropic over the gateway turns it off)."""
        return True

    def headers(self, spec: ModelSpec) -> dict[str, str]:
        return {}

    def extra_body(self, spec: ModelSpec) -> dict[str, Any]:
        return {}

    def env_var(self, spec: ModelSpec) -> str:
        """The variable the credential arrives in. Empty when the workspace token covers the model."""
        return PROVIDER_KEY_ENV

    async def child_env(self, resolved: ResolvedModel, secret: Secret) -> ChildEnv:
        """How the agent process authenticates. The default is the one fixed variable (D4)."""
        return ChildEnv(vars={resolved.env_var or PROVIDER_KEY_ENV: secret.value})

    def auth_headers(self, secret: Secret | None) -> dict[str, str]:
        """Headers for the probe. Never stored, never logged."""
        if secret is None:
            return {}
        return {"Authorization": f"Bearer {secret.value}"} if self.bearer else {"x-api-key": secret.value}

    async def probe(self, desc: ProviderDescriptor, secret: Secret | None,
                    *, client: httpx.AsyncClient | None = None) -> tuple[str, str]:
        """One bounded liveness call. Returns `(state, provider's own words)`.

        `state` is a health state, not a boolean: 401 and 500 need different copy and different
        actions, so flattening them into "unhealthy" would throw away the only actionable part.
        """
        raise NotImplementedError

    @staticmethod
    async def _post(url: str, payload: dict, headers: dict[str, str],
                    client: httpx.AsyncClient | None = None) -> tuple[str, str]:
        """POST and classify. Shared so the four probes cannot disagree about what a 401 means."""
        from ....domain.llm import classify

        own = client is None
        http = client or httpx.AsyncClient(timeout=PROBE_TIMEOUT)
        try:
            r = await http.post(url, json=payload, headers=headers)
            if r.status_code < 300:
                return "available", ""
            return _state_for_status(r.status_code, r.text)[0], _detail(r.text, classify(r.text).detail)
        except httpx.HTTPError as exc:
            from ....domain.redact import redact

            return "degraded", redact(f"{type(exc).__name__}: {exc}")[:400]
        finally:
            if own:
                await http.aclose()


def _state_for_status(status: int, text: str) -> tuple[str, str]:
    from ....domain.llm import classify

    if status in (401, 403):
        return "unauthorised", text
    return classify(text).state, text


def _detail(text: str, fallback: str, limit: int = 400) -> str:
    from ....domain.redact import redact

    return (redact(fallback or text) or "")[:limit]
