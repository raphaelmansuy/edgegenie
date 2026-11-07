"""Health: probe, classify, cache. Never a boolean, never an opinion without a timestamp.

Three rules, each from a measured failure:

* **probes are rate limited** and skipped when a turn just succeeded, because a probe costs money
  (E-24). `LLM_PROBE_SECONDS` defaults to 900.
* **a failure is classified before it is stored**, and the stored `detail` is the provider's own
  sentence, redacted and capped at 400 characters — a 401 body can contain part of the key (06).
* **a cap rejection lowers the stored cap**, and never raises one: a number in an error may be a
  proxy's cap, not the model's (05 §Limit evidence, E-4).
"""

from __future__ import annotations

import logging
import time

from ..domain.llm import (
    Cause,
    CredentialKind,
    ModelSpec,
    ProviderKind,
    cap_from_error,
    classify,
)
from ..domain.redact import redact

log = logging.getLogger("app.llm.health")

#: At most one probe per model per interval. A probe is a paid call, not a health check ping.
DEFAULT_INTERVAL = 900.0


class HealthService:
    """Probes models and records what happened, through the store and the adapters."""

    def __init__(self, store, credentials, *, interval: float = DEFAULT_INTERVAL,
                 host: str = "", enabled: bool = True) -> None:
        self._store = store
        self._credentials = credentials
        self._interval = interval
        self._host = host
        self._enabled = enabled
        self._last_probe: dict[str, float] = {}

    # -- reads ----------------------------------------------------------------
    async def state_of(self, model_id: str) -> tuple[str, str, float] | None:
        return await self._store.health_state(model_id)

    # -- probes ---------------------------------------------------------------
    async def probe(self, spec: ModelSpec, *, user_id: str, force: bool = False) -> tuple[str, str]:
        """One bounded call. Returns `(state, detail)` and records a health row.

        A model needing a key this user does not have is `unauthorised` **without** a network call:
        that is the honest classification and it costs nothing.
        """
        if not force and not self._due(spec.id.value):
            row = await self._store.health_state(spec.id.value)
            return (row[0], row[1]) if row else ("unknown", "")
        self._last_probe[spec.id.value] = time.time()

        from ..adapters.llm.providers import adapter_for

        adapter = adapter_for(spec.id.provider)
        secret = None
        if spec.credential_kind is not CredentialKind.NONE:
            ref = await self._credentials.find(spec.id.provider, user_id=user_id)
            if ref is None:
                return await self._record(spec, "unauthorised",
                                          f"{spec.provider_name} needs a key before this model can run.",
                                          source="probe")
            try:
                secret = await self._credentials.open_ref(ref.id, user_id=user_id)
            except Exception as exc:  # noqa: BLE001 - a vault refusal is a health fact
                return await self._record(spec, "unauthorised", str(exc)[:400], source="probe")
        elif spec.id.provider is ProviderKind.DATABRICKS:
            # The workspace token is the credential; without it there is nothing to probe with.
            try:
                secret = await self._credentials.open_for(ProviderKind.DATABRICKS, user_id=user_id)
            except Exception:  # noqa: BLE001
                return await self._record(spec, "unknown",
                                          "no workspace token to probe with", source="probe")

        desc = adapter.descriptor(spec, host=self._host,
                                  project=getattr(secret, "project_hint", "") or "")
        try:
            state, detail = await adapter.probe(desc, secret)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 - a probe must never raise into a request
            state, detail = "degraded", f"{type(exc).__name__}: {exc}"
        return await self._record(spec, state, detail, source="probe")

    async def note_turn(self, spec: ModelSpec, text: str, *, turn_id: str = "") -> str:
        """Classify a turn's failure and record it. Returns the state it produced.

        This is the only path that writes a limit correction, and only downward (E-4).
        """
        result = classify(text)
        detail = redact(result.detail)[:400]
        if result.cause is Cause.CAP_EXCEEDED:
            cap = cap_from_error(text)
            if cap:
                await self._store.note_limits(spec.id.value, cap,
                                              f"observed at {turn_id or 'a turn'}")
                detail = f"the endpoint caps output at {cap}; the stored cap was lowered"
        await self._record(spec, result.state, detail, source="turn")
        return result.state

    # -- internals ------------------------------------------------------------
    def _due(self, model_id: str) -> bool:
        if not self._enabled:
            return False
        last = self._last_probe.get(model_id)
        return last is None or (time.time() - last) >= self._interval

    async def _record(self, spec: ModelSpec, state: str, detail: str, *, source: str) -> tuple[str, str]:
        safe = redact(" ".join((detail or "").split()))[:400]
        try:
            await self._store.record_health(spec.id.value, state, safe, source=source)
        except Exception:  # noqa: BLE001 - recording health must not fail the caller
            log.warning("could not record health for %s", spec.id.value)
        return state, safe
