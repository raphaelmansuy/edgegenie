"""The in-memory registry: the demo and test implementation, and the day-one one.

It is a first-class implementation, not a stub. `agent_mode="fake"` and every unit test use it
(01 E9's precedent: `MemoryEventStore`), so the registry's behaviour is exercised without Postgres
and C-5 is satisfied by construction.

It is also the *fallback* when a Postgres registry dies mid-flight: `PgRegistryStore` calls
`degrade_to(last_known)` so a dropped connection does not empty the picker (E-15).
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from ....domain.llm import Grant, LimitEvidence, Limits, ModelId, ModelSpec, ModelState


class MemoryRegistryStore:
    """Providers, models, grants, health history and turn pins, in dicts."""

    source = "memory"

    def __init__(self, *, source: str = "memory") -> None:
        self.source = source
        self._providers: dict[str, dict] = {}
        self._models: dict[str, ModelSpec] = {}
        self._grants: dict[str, Grant] = {}
        self._health: dict[str, list[tuple[str, str, float]]] = {}
        self._turns: dict[str, dict] = {}
        self._turns_by_session: dict[str, list[dict]] = {}
        self._discovery: list[dict] = []
        self._settings: dict[str, str] = {}
        self.default_model = ""

    # -- reads ----------------------------------------------------------------
    async def providers(self) -> list[dict]:
        return list(self._providers.values())

    async def models(self, user_id: str = "") -> list[ModelSpec]:
        return list(self._models.values())

    async def find(self, model_id: str) -> ModelSpec | None:
        return self._models.get(model_id)

    async def grants(self, model_id: str) -> Grant | None:
        return self._grants.get(model_id)

    async def health_state(self, model_id: str) -> tuple[str, str, float] | None:
        rows = self._health.get(model_id)
        return rows[-1] if rows else None

    async def health_history(self, model_id: str, limit: int = 50) -> list[tuple[str, str, float]]:
        return list(reversed(self._health.get(model_id, [])))[:limit]

    # -- writes ---------------------------------------------------------------
    async def upsert_provider(self, provider: dict) -> None:
        self._providers[str(provider["id"])] = dict(provider)

    async def upsert_model(self, spec: ModelSpec) -> None:
        """Upsert by canonical id. Two rows may never disagree about one model (E-2)."""
        key = spec.id.value
        existing = self._models.get(key)
        if existing is not None and existing.endpoint != spec.endpoint:
            raise ValueError(
                f"{key} is already registered against endpoint {existing.endpoint!r}; "
                f"refusing to replace it with {spec.endpoint!r}"
            )
        self._models[key] = spec

    # -- administration (the same operations the Postgres store offers) -------------
    async def all_models(self) -> list[ModelSpec]:
        return list(self._models.values())

    async def get_setting(self, key: str) -> str:
        return self._settings.get(key, "")

    async def set_setting(self, key: str, value: str, by: str = "") -> None:
        self._settings[key] = value

    async def set_default_model(self, model_id: str, by: str = "") -> None:
        self._settings["default_model"] = model_id
        self.default_model = model_id

    async def set_model_enabled(self, model_id: str, enabled: bool) -> bool:
        spec = self._models.get(model_id)
        if spec is None:
            return False
        self._models[model_id] = replace(spec, enabled=enabled)
        return True

    async def delete_model(self, model_id: str) -> bool:
        return self._models.pop(model_id, None) is not None

    async def update_provider(self, provider_id: str, *, enabled: bool | None = None,
                              base_url: str | None = None) -> bool:
        row = self._providers.get(provider_id)
        if row is None:
            return False
        if enabled is not None:
            row["enabled"] = enabled
        if base_url is not None:
            row["base_url"] = base_url
        return True

    async def set_grant(self, grant: Grant) -> None:
        self._grants[grant.model_id] = grant

    async def record_health(self, model_id: str, state: str, detail: str, *, source: str = "probe") -> None:
        at = time.time()
        self._health.setdefault(model_id, []).append((state, detail[:400], at))
        spec = self._models.get(model_id)
        if spec is not None:
            self._models[model_id] = spec.with_health(ModelState(state), detail[:400], at)

    async def record_turn_model(self, pin: dict) -> None:
        """Insert-once. A second write for the same turn is a no-op, never an overwrite (C-8)."""
        turn_id = str(pin["turnId"])
        if turn_id in self._turns:
            return
        row = {**pin, "at": pin.get("at") or time.time()}
        self._turns[turn_id] = row
        self._turns_by_session.setdefault(str(pin.get("sessionId", "")), []).append(row)

    async def turn_models(self, session_id: str) -> list[dict]:
        return list(self._turns_by_session.get(session_id, []))

    async def record_discovery(self, provider: str, outcome: str, seen: int, detail: str = "") -> None:
        self._discovery.append(
            {"provider": provider, "outcome": outcome, "modelsSeen": seen, "detail": detail[:400],
             "at": time.time()}
        )

    async def discovery_runs(self, limit: int = 20) -> list[dict]:
        return list(reversed(self._discovery))[:limit]

    async def note_limits(self, model_id: str, output: int, source: str) -> None:
        """Lower a cap from an observed rejection. Never raise it (05 §Limit evidence)."""
        spec = self._models.get(model_id)
        if spec is None or output <= 0 or spec.limits.output <= output:
            return
        self._models[model_id] = replace(
            spec, limits=Limits(spec.limits.context, output, LimitEvidence.MEASURED, source))

    def replace_all(self, specs: list[ModelSpec]) -> None:
        """Discovery's whole-catalogue update, in one step, keeping rows it does not mention."""
        for spec in specs:
            self._models[spec.id.value] = spec

    async def close(self) -> None:  # pragma: no cover - nothing to close
        return
