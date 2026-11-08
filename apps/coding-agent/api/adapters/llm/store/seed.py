"""Load the seed catalogue: `seed/llm_models.yaml` -> validated providers and `ModelSpec`s.

Two rules make this file safe to ship:

* **It is validated, not trusted.** Every row is parsed into the domain's value objects, so a typo in
  the YAML is a boot error rather than a model that fails at call time.
* **It grants nothing.** Grants come only from the database (05 §llm_model_grant); a seed file that
  could grant access would put authorisation in a repository.

Pure apart from reading one file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ....domain.llm import (
    Capability,
    CredentialKind,
    CredentialSource,
    LimitEvidence,
    Limits,
    ModelId,
    ModelSpec,
    ModelState,
    ProviderKind,
    WireProtocol,
)

#: `api/adapters/llm/store/seed.py` -> `apps/coding-agent/seed/llm_models.yaml`
DEFAULT_SEED_PATH = Path(__file__).resolve().parents[4] / "seed" / "llm_models.yaml"


class SeedError(ValueError):
    """A seed row that cannot be understood. Named field, so a typo is one line to fix."""

    def __init__(self, row: str, message: str) -> None:
        super().__init__(f"seed row {row!r}: {message}")
        self.row = row


@dataclass(frozen=True, slots=True)
class SeedProvider:
    id: str
    display_name: str
    kind: ProviderKind
    wire: WireProtocol
    base_url: str = ""
    npm: str = ""
    credential: str = ""


@dataclass(frozen=True, slots=True)
class Seed:
    providers: tuple[SeedProvider, ...]
    models: tuple[ModelSpec, ...]
    default_model: str = ""

    def provider_for(self, kind: ProviderKind) -> SeedProvider | None:
        return next((p for p in self.providers if p.kind is kind), None)


def _wire(value: str | None, fallback: WireProtocol) -> WireProtocol:
    if not value:
        return fallback
    try:
        return WireProtocol(value)
    except ValueError:
        raise SeedError(value, f"{value!r} is not a wire protocol") from None


def _capability(value: str | None) -> Capability:
    if not value:
        return Capability.TOOLS
    try:
        return Capability(value)
    except ValueError:
        raise SeedError(value, f"{value!r} is not a capability") from None


def _state(value: str | None) -> ModelState:
    if not value:
        return ModelState.UNKNOWN
    try:
        return ModelState(value)
    except ValueError:
        raise SeedError(value, f"{value!r} is not a model state") from None


def _evidence(value: str | None) -> LimitEvidence:
    if not value:
        return LimitEvidence.DEFAULT
    try:
        return LimitEvidence(value)
    except ValueError:
        raise SeedError(value, f"{value!r} is not a limit evidence label") from None


def _credential(value: str | None) -> CredentialKind:
    """A provider's credential requirement, expressed in the seed as a word rather than an enum."""
    mapping = {
        None: CredentialKind.NONE,
        "": CredentialKind.NONE,
        "workspace_token": CredentialKind.NONE,
        "api_key": CredentialKind.API_KEY,
        "service_account_json": CredentialKind.SERVICE_ACCOUNT_JSON,
        "access_token": CredentialKind.ACCESS_TOKEN,
    }
    if value not in mapping:
        raise SeedError(str(value), f"{value!r} is not a credential kind")
    return mapping[value]


def _spec(row: dict[str, Any], providers: dict[ProviderKind, SeedProvider]) -> ModelSpec:
    raw_id = str(row.get("id") or "")
    try:
        mid = ModelId.parse(raw_id)
    except Exception:
        raise SeedError(raw_id, "id must be provider/model with a known provider") from None
    provider = providers.get(mid.provider)
    if provider is None:
        raise SeedError(raw_id, f"no provider row for {mid.provider.value}")
    wire = _wire(row.get("wire"), provider.wire)
    credential = _credential(row.get("credential", provider.credential))
    limits = Limits(
        int(row.get("context") or 0) or 64_000,
        int(row.get("output") or 0) or 4_000,
        _evidence(row.get("evidence")),
        str(row.get("source") or "assumed"),
    )
    return ModelSpec(
        id=mid,
        display_name=str(row.get("display_name") or mid.name),
        provider_name=provider.display_name,
        wire=wire,
        endpoint=str(row.get("endpoint") or mid.name),
        limits=limits,
        capability=_capability(row.get("capability")),
        credential_kind=credential,
        credential_source=(CredentialSource.WORKSPACE_TOKEN
                           if credential is CredentialKind.NONE
                           else CredentialSource.NONE),
        state=_state(row.get("state")),
        group=str(row.get("group") or ""),
        # Declared in the seed, never inferred from the name: a name is a guess, and a wrong "yes" ships
        # a picture to a model that cannot see it (specs/009 [D7]).
        sees_images=bool(row.get("sees_images", False)),
        origin="seed",
    )


def load(path: Path | str | None = None) -> Seed:
    """Parse and validate the seed file. Missing file is an empty seed, not a crash (C-5 spirit)."""
    target = Path(path) if path else DEFAULT_SEED_PATH
    if not target.exists():
        return Seed((), (), "")
    data = yaml.safe_load(target.read_text("utf-8")) or {}
    providers: list[SeedProvider] = []
    for raw in data.get("providers") or []:
        pid = str(raw.get("id") or "")
        try:
            kind = ProviderKind(str(raw.get("kind") or pid))
        except ValueError:
            raise SeedError(pid, f"{raw.get('kind')!r} is not a provider kind") from None
        providers.append(
            SeedProvider(
                id=pid,
                display_name=str(raw.get("display_name") or pid),
                kind=kind,
                wire=_wire(raw.get("wire"), WireProtocol.OPENAI),
                base_url=str(raw.get("base_url") or ""),
                npm=str(raw.get("npm") or ""),
                credential=str(raw.get("credential") or ""),
            )
        )
    by_kind = {p.kind: p for p in providers}
    models: list[ModelSpec] = []
    default = ""
    for raw in data.get("models") or []:
        spec = _spec(raw, by_kind)
        models.append(spec)
        if raw.get("default"):
            default = spec.id.value
    if not default and models:
        default = models[0].id.value
    return Seed(tuple(providers), tuple(models), default)
