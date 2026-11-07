"""Catalogue assembly: seed ∪ database ∪ discovery, with **field-level** precedence.

Three inputs, one deterministic output. The precedence is explicit per field, not per record, because
that is the part that is easy to get wrong (03 §Catalogue assembly):

| Field | Precedence | Why |
|---|---|---|
| existence, ready state | discovery | only the workspace knows |
| `display_name`, `group` | database -> seed | an operator's naming beats a default |
| `context_window`, `max_output` | measured -> documented -> default | a measurement beats a document beats a guess |
| `grants` | database only | authorisation is not a build artefact |
| `health` | probe only, never static | a cached opinion is not a health check |
| `credential_ref` | database only | a reference to a secret, never the secret |

**A row is never deleted by discovery** (FR-14, D8): a model that disappears becomes `not_served` and
keeps its grants, so it can be resumed if it comes back. Deleting on a momentary read failure would
silently revoke access, which is precisely what the old `None`-means-do-not-filter rule protects.

Reads the store and discovery ports it is given; it does no I/O of its own.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any

from ..domain.llm import (
    Capability,
    CredentialKind,
    CredentialSource,
    Grant,
    LimitEvidence,
    ModelSpec,
    ModelState,
    ProviderKind,
)


@dataclass(frozen=True, slots=True)
class Catalogue:
    """The answer to "which models exist for this user", with where the answer came from."""

    models: tuple[ModelSpec, ...]
    source: str                 # seed | memory | database | degraded
    updated_at: float
    default_model: str = ""
    providers: tuple[dict, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": [m.to_dict() for m in self.models],
            "default": self.default_model,
            "source": self.source,
            "updatedAt": iso(self.updated_at),
        }

    def find(self, model_id: str) -> ModelSpec | None:
        return next((m for m in self.models if m.id.value == model_id), None)

    def of_provider(self, kind: ProviderKind) -> tuple[ModelSpec, ...]:
        return tuple(m for m in self.models if m.id.provider is kind)


_EVIDENCE_RANK = {
    LimitEvidence.MEASURED: 3,
    LimitEvidence.DOCUMENTED: 2,
    LimitEvidence.DEFAULT: 1,
}

_STATE_RANK = {
    ModelState.AVAILABLE: 0,
    ModelState.UNKNOWN: 1,
    ModelState.DEGRADED: 2,
    ModelState.UNAUTHORISED: 3,
    ModelState.NOT_ENABLED: 4,
    ModelState.NOT_SERVED: 5,
}

_PROVIDER_RANK = {
    ProviderKind.DATABRICKS: 0,
    ProviderKind.OPENAI: 1,
    ProviderKind.ANTHROPIC: 2,
    ProviderKind.GOOGLE_VERTEX: 3,
    ProviderKind.FAKE: 4,
}


def stronger_limits(a, b):
    """The higher-evidence of two `Limits`. Ties keep `a`, so a stored measurement is not displaced."""
    if b is None:
        return a
    if a is None:
        return b
    return b if _EVIDENCE_RANK[b.evidence] > _EVIDENCE_RANK[a.evidence] else a


class ModelService:
    """Composes the store and discovery into one catalogue. The only catalogue a route reads."""

    def __init__(self, store, discovery=None, *, default_model: str = "",
                 allow_external: bool = True, vault=None, ttl: float = 30.0) -> None:
        self._store = store
        self._discovery = discovery
        self._default = default_model
        self._allow_external = allow_external
        self._vault = vault
        self._ttl = ttl
        self._last: Catalogue | None = None
        self._cached_at = 0.0

    # -- reads ----------------------------------------------------------------
    async def catalogue(self, user_id: str, groups: frozenset[str] = frozenset(),
                        *, refresh: bool = False) -> Catalogue:
        """The merged catalogue, filtered for this user. Cached for `ttl` (C-6, NFR-1)."""
        now = time.time()
        if refresh or self._last is None or now - self._cached_at >= self._ttl:
            models = await self._merge()
            self._last = Catalogue(
                models=tuple(models),
                source=getattr(self._store, "source", "memory"),
                updated_at=now,
                default_model=self._resolve_default(models),
                providers=tuple(await self._store.providers()),
            )
            self._cached_at = now
        return await self._authorise(self._last, user_id, groups)

    def last(self) -> Catalogue | None:
        """The last known catalogue, for the degraded path when the store throws (E-15)."""
        return self._last

    async def find(self, model_id: str, user_id: str = "") -> ModelSpec | None:
        """One model, from the store first, then from the last assembled catalogue."""
        spec = await self._store.find(model_id)
        if spec is None and self._last is not None:
            spec = self._last.find(model_id)
        return spec

    async def grant_for(self, model_id: str) -> Grant | None:
        return await self._store.grants(model_id)

    def invalidate(self) -> None:
        self._cached_at = 0.0

    # -- assembly -------------------------------------------------------------
    async def _merge(self) -> list[ModelSpec]:
        try:
            stored = list(await self._store.models(""))
        except Exception:  # noqa: BLE001 - a dead store must not empty the catalogue (E-15)
            stored = list(self._last.models) if self._last else []
        by_id: dict[str, ModelSpec] = {m.id.value: m for m in stored}

        discovered = await self._discovered()
        if discovered is not None:
            seen = {s.id.value for s in discovered}
            for spec in discovered:
                existing = by_id.get(spec.id.value)
                by_id[spec.id.value] = _merge_one(existing, spec) if existing else spec
            # A gateway row discovery no longer lists is `not_served`, never deleted (FR-14).
            for key, spec in list(by_id.items()):
                if spec.id.provider is ProviderKind.DATABRICKS and key not in seen:
                    by_id[key] = replace(spec, state=ModelState.NOT_SERVED)

        out = [await self._decorate(spec) for spec in by_id.values()]
        return _order(out)

    async def _discovered(self) -> list[ModelSpec] | None:
        """`None` means unreadable, and unreadable changes nothing about the catalogue."""
        if self._discovery is None:
            return None
        try:
            result = await self._discovery.fetch(None)
        except Exception:  # noqa: BLE001 - discovery must never fail a catalogue read
            return None
        if getattr(result, "readable", None) is False:
            return None
        specs = getattr(result, "specs", result)
        return list(specs) if specs is not None else None

    async def _decorate(self, spec: ModelSpec) -> ModelSpec:
        """Add the facts that do not come from the row: health history, egress policy, key presence."""
        changed = spec
        reader = getattr(self._store, "health_state", None)
        if reader is not None:
            health = await reader(spec.id.value)
            if health is not None:
                state, detail, at = health
                try:
                    changed = replace(changed, state=ModelState(state), detail=detail, checked_at=at)
                except ValueError:      # a health row from a newer build: keep the catalogue row
                    pass
        if not self._allow_external and spec.id.provider not in (
                ProviderKind.DATABRICKS, ProviderKind.FAKE):
            changed = replace(changed, refusal="external providers are disabled in this workspace")
        if spec.credential_kind is not CredentialKind.NONE and not spec.credential_hint:
            changed = replace(changed, credential_source=CredentialSource.NONE)
        return changed

    async def _authorise(self, cat: Catalogue, user_id: str,
                         groups: frozenset[str]) -> Catalogue:
        """Copy the catalogue with only what this user may see, and their own key hint.

        Grants are applied here rather than in `_merge` so the merged catalogue is shared between
        users: the expensive part is one merge, and the cheap part is a predicate per user.
        """
        visible: list[ModelSpec] = []
        for spec in cat.models:
            grant = await self._store.grants(spec.id.value)
            if grant is not None and not grant.allows(user_id, groups):
                continue
            visible.append(await self._with_credential(spec, user_id))
        if len(visible) == len(cat.models) and all(
                v.credential_hint == s.credential_hint for v, s in zip(visible, cat.models)):
            return cat
        default = cat.default_model if any(m.id.value == cat.default_model for m in visible) else ""
        return replace(cat, models=tuple(visible),
                       default_model=default or self._resolve_default(visible))

    async def _with_credential(self, spec: ModelSpec, user_id: str) -> ModelSpec:
        """Say which key is in play, by `last4` only, so the picker can show `key …7f3a`."""
        kind = spec.credential_kind
        if kind is CredentialKind.NONE or self._vault is None:
            return spec
        try:
            ref = await self._vault.find(spec.id.provider, user_id=user_id)
        except Exception:  # noqa: BLE001 - a vault outage must not empty the catalogue
            return spec
        if ref is None:
            return replace(spec, credential_source=CredentialSource.NONE, credential_hint="")
        source = (CredentialSource.ENV if ref.id.startswith("env:")
                  else CredentialSource.USER if ref.scope_kind == "user"
                  else CredentialSource.WORKSPACE)
        hint = f"{ref.kind.replace('_', ' ')} …{ref.last4}" if ref.last4 else ref.kind
        return replace(spec, credential_source=source, credential_hint=hint,
                       credential_ref_id=ref.id)

    def _resolve_default(self, models: list[ModelSpec]) -> str:
        if self._default and any(m.id.value == self._default for m in models):
            return self._default
        available = next((m for m in models if m.state is ModelState.AVAILABLE), None)
        if available is not None:
            return available.id.value
        return models[0].id.value if models else ""


def _merge_one(existing: ModelSpec, discovered: ModelSpec) -> ModelSpec:
    """Per-field precedence between a stored row and a live discovery row.

    Existence and readiness come from discovery; names, groups and limits come from the stored row,
    because an operator's naming and a measured cap beat a default — and a discovery row has neither.
    A row that had been `not_served` and is listed again becomes available (the arrow 04 draws).
    """
    state = discovered.state if existing.state is ModelState.UNKNOWN else existing.state
    if existing.state is ModelState.NOT_SERVED:
        state = ModelState.AVAILABLE
    return replace(
        existing,
        display_name=existing.display_name or discovered.display_name,
        limits=stronger_limits(existing.limits, discovered.limits),
        state=state,
    )


def _order(models: list[ModelSpec]) -> list[ModelSpec]:
    """Deterministic order: provider rank, availability, then name. A list that reorders itself
    cannot be learned (D14), and the picker relies on this order for its groups."""
    return sorted(models, key=lambda m: (_PROVIDER_RANK.get(m.id.provider, 9),
                                         _STATE_RANK.get(m.state, 9),
                                         m.display_name.lower()))


def iso(epoch: float) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(epoch, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def capability_of(value: str) -> Capability:
    return Capability(value)


__all__ = ["Catalogue", "ModelService", "iso", "stronger_limits"]
