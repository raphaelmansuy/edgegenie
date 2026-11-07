"""Discovery: what the workspace serves *right now*, with the fields the registry needs.

It keeps the three rules that made the old `ServingBrowser` correct:

1. **`None` means do not filter.** An unreadable list is not an empty list (FR-14, E-22). The first
   deployed app emptied its catalogue on a permission error and revoked access.
2. **Chat endpoints that are ready only.** An embeddings endpoint is not a model you can talk to.
3. **Cached for a TTL.** Discovery is not a per-request call (C-6).

What it adds: the endpoint list becomes `ModelSpec`s, so limits and readiness travel with the names,
and a run record says why the list changed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ....domain.llm import ModelId, ModelSpec, ModelState, ProviderKind, WireProtocol
from ....domain.llm.limits import DEFAULT_LIMITS, LimitEvidence, Limits
from ...databricks.http import DbxHttp

TTL_SECONDS = 300


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """One pass. `specs` is empty when the pass failed, and `outcome` says which failure it was."""

    specs: tuple[ModelSpec, ...]
    outcome: str            # ok | denied | error
    detail: str = ""

    @property
    def readable(self) -> bool:
        return self.outcome == "ok"


class DatabricksDiscovery:
    """`/api/2.0/serving-endpoints` -> `ModelSpec`s, cached for `LLM_DISCOVERY_SECONDS`."""

    def __init__(self, host: str, token_provider, http: DbxHttp | None = None,
                 ttl: float = TTL_SECONDS) -> None:
        self._http = http or DbxHttp(host, token_provider)
        self._ttl = ttl
        self._cache: tuple[float, DiscoveryResult] | None = None

    async def fetch(self, token: str | None) -> DiscoveryResult:
        if self._cache and time.monotonic() - self._cache[0] < self._ttl:
            return self._cache[1]
        try:
            body = await self._http.get("/api/2.0/serving-endpoints", token)
        except PermissionError as exc:
            # Do NOT cache a denial as if it were a fact about the workspace: the next call retries.
            return DiscoveryResult((), "denied", str(exc)[:400])
        except RuntimeError as exc:
            return DiscoveryResult((), "error", str(exc)[:400])
        specs = tuple(_spec(e) for e in body.get("endpoints", []) if _is_chat(e))
        result = DiscoveryResult(specs, "ok")
        self._cache = (time.monotonic(), result)
        return result

    async def served(self, token: str | None) -> frozenset[str] | None:
        """Compatibility for the existing `/api/models` filter: names, or None when unreadable."""
        result = await self.fetch(token)
        if not result.readable:
            return None
        return frozenset(s.endpoint for s in result.specs)

    def invalidate(self) -> None:
        self._cache = None

    @property
    def provider_id(self) -> str:
        """The provider this discovery adapter reads, so a caller never has to name a vendor."""
        return ProviderKind.DATABRICKS.value

    @property
    def age_seconds(self) -> float | None:
        return time.monotonic() - self._cache[0] if self._cache else None


def _is_chat(endpoint: dict) -> bool:
    return (endpoint.get("task", "llm/v1/chat") == "llm/v1/chat"
            and (endpoint.get("state") or {}).get("ready", "READY") == "READY")


def _spec(endpoint: dict) -> ModelSpec:
    """One served endpoint as a spec. Anything beyond existence and readiness is `default` evidence.

    The workspace API is verified only for `name`, `task` and `state.ready` (01 U1). Reading more and
    labelling it `measured` would be the exact dishonesty Axiom A3 forbids, so a discovered model
    keeps the conservative limits until the seed or a probe supplies better ones.
    """
    name = str(endpoint.get("name") or "")
    foundation = str((endpoint.get("foundation_model") or {}).get("name") or "")
    display = foundation.rsplit(".", 1)[-1] if foundation else name
    return ModelSpec(
        id=ModelId(ProviderKind.DATABRICKS, name.lower()),
        display_name=display,
        provider_name="Databricks AI Gateway",
        wire=WireProtocol.SERVING,
        endpoint=name,
        limits=Limits(DEFAULT_LIMITS.context, DEFAULT_LIMITS.output, LimitEvidence.DEFAULT, "discovery"),
        state=ModelState.AVAILABLE,
        origin="discovery",
    )
