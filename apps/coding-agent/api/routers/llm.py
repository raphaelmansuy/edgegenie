"""`/api/llm/*`: the catalogue's detail, credentials, health and provenance.

One rule governs every route here: **no response contains a credential**, its ciphertext, or anything
derived from its plaintext beyond `last4` and a fingerprint. `tests/test_llm_api.py` plants a key in
each kind and scans every response body, so the rule is enforced rather than promised (C-1/S1).

The routes are thin: validate, delegate to a service, map a typed error to a status. No provider name
appears here (Axiom A2).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..adapters.llm.vault import VaultRefused
from ..domain.llm import (
    CredentialError,
    CredentialKind,
    ModelError,
    NoCredential,
    NotGranted,
    NotSelectable,
    ProviderKind,
    UnknownModel,
    with_project,
)
from ..services.model_service import iso

log = logging.getLogger("app.api.llm")
router = APIRouter(prefix="/api/llm")


# -- schemas -----------------------------------------------------------------
class AddCredential(BaseModel):
    provider: str = Field(min_length=2, max_length=40)
    kind: str = Field(default="api_key", max_length=40)
    secret: str = Field(min_length=8, max_length=200_000)
    #: `user` (default) or `workspace`. A workspace key is usable by everyone and revealed to nobody.
    scope: str = Field(default="user", pattern="^(user|workspace)$")
    #: The GCP project a service-account key bills to, for a key that does not name one.
    project: str = Field(default="", max_length=64)


class TestCredential(BaseModel):
    """Test before save (K3). The secret is used once and not stored.

    `secret` has no minimum length here on purpose: a key that is too short must come back as a
    **named field error the form can point at**, not as an opaque 422 from the request validator.
    """

    provider: str = Field(min_length=2, max_length=40)
    kind: str = Field(default="api_key", max_length=40)
    secret: str = Field(min_length=1, max_length=200_000)
    model: str | None = None
    project: str = Field(default="", max_length=64)


class ProbeRequest(BaseModel):
    model: str = Field(min_length=3, max_length=200)


def _registry(request: Request):
    registry = getattr(request.app.state, "llm", None)
    if registry is None:  # pragma: no cover - build() always wires it
        raise HTTPException(503, "the model registry is not configured")
    return registry


def _user(request: Request) -> str:
    return request.state.user_id


def _groups(request: Request) -> frozenset[str]:
    return getattr(request.state, "groups", frozenset())


def _provider(value: str) -> ProviderKind:
    try:
        return ProviderKind(value)
    except ValueError:
        raise HTTPException(422, f"{value!r} is not a provider this app knows") from None


# -- catalogue ---------------------------------------------------------------
@router.get("/models")
async def models(request: Request) -> dict[str, Any]:
    """The full catalogue: state, limits with evidence, capability, credential hint, grouping."""
    registry = _registry(request)
    cat = await registry.catalogue.catalogue(_user(request), _groups(request))
    return cat.to_dict()


@router.get("/models/{model_id:path}")
async def model_detail(request: Request, model_id: str) -> dict[str, Any]:
    registry = _registry(request)
    spec = await registry.catalogue.find(model_id, _user(request))
    if spec is None:
        raise HTTPException(404, f"no model named {model_id!r} is in the catalogue")
    return spec.to_dict()


@router.post("/models/probe")
async def probe(request: Request, body: ProbeRequest) -> dict[str, Any]:
    """Probe one model now. Rate limited by `LLM_PROBE_SECONDS` unless the caller forces it.

    A probe spends a token, so it is never part of a page load (E-24).
    """
    registry = _registry(request)
    spec = await registry.catalogue.find(body.model, _user(request))
    if spec is None:
        raise HTTPException(404, f"no model named {body.model!r} is in the catalogue")
    state, detail = await registry.health.probe(spec, user_id=_user(request))
    return {"model": spec.id.value, "state": state, "detail": detail}


# -- discovery ---------------------------------------------------------------
@router.get("/discovery")
async def discovery_runs(request: Request) -> dict[str, Any]:
    registry = _registry(request)
    return {
        "source": registry.source,
        "runs": await registry.store.discovery_runs(20),
        "externalEnabled": registry.allow_external,
    }


@router.post("/discovery/refresh")
async def refresh_discovery(request: Request) -> dict[str, Any]:
    """Force a discovery pass. The scheduled refresh makes this unnecessary (C-6)."""
    registry = _registry(request)
    if registry.discovery is None:
        raise HTTPException(409, "discovery needs a workspace host")
    registry.discovery.invalidate()
    registry.catalogue.invalidate()
    discovery = registry.discovery
    result = await discovery.fetch(None)
    await registry.store.record_discovery(discovery.provider_id, result.outcome,
                                          len(result.specs), result.detail)
    for spec in result.specs:
        try:
            await registry.store.upsert_model(spec)
        except ValueError:
            continue
    cat = await registry.catalogue.catalogue(_user(request), _groups(request), refresh=True)
    return {**cat.to_dict(), "discovery": {"outcome": result.outcome, "seen": len(result.specs),
                                           "detail": result.detail}}


# -- health ------------------------------------------------------------------
@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    """Per provider: how many models, how many usable, the last failure's own words.

    It must not probe: a readiness check that calls out fails the app for a remote reason.
    """
    registry = _registry(request)
    cat = await registry.catalogue.catalogue(_user(request), _groups(request))
    by_provider: dict[str, dict] = {}
    for spec in cat.models:
        row = by_provider.setdefault(spec.id.provider.value, {
            "id": spec.id.provider.value, "name": spec.provider_name, "models": 0,
            "usable": 0, "state": "ok", "detail": "", "lastProbe": None,
        })
        row["models"] += 1
        if spec.selectable and spec.state.usable:
            row["usable"] += 1
        if spec.state.value in ("degraded", "unauthorised") and spec.detail:
            row["state"] = spec.state.value
            row["detail"] = spec.detail
        stamp = spec.checked_at or 0
        if stamp and (row["lastProbe"] is None or stamp > row["lastProbe"]):
            row["lastProbe"] = stamp
    providers = []
    for row in by_provider.values():
        providers.append({**row, "lastProbe": iso(row["lastProbe"]) if row["lastProbe"] else None})
    return {
        "source": cat.source,
        "updatedAt": iso(cat.updated_at),
        "vault": {"mode": registry.credentials.mode, "available": registry.credentials.available},
        "providers": providers,
    }


# -- credentials -------------------------------------------------------------
@router.get("/credentials")
async def list_credentials(request: Request) -> dict[str, Any]:
    registry = _registry(request)
    refs = await registry.credentials.list(user_id=_user(request))
    return {
        "credentials": [r.public() for r in refs],
        "vault": {"mode": registry.credentials.mode, "available": registry.credentials.available},
        "canSave": registry.credentials.available,
    }


@router.put("/credentials")
async def put_credential(request: Request, body: AddCredential) -> dict[str, Any]:
    """Store a key. Returns `last4` and a fingerprint and **nothing derived from the plaintext**."""
    registry = _registry(request)
    if not registry.credentials.available:
        raise HTTPException(503, _cannot_save(registry))
    provider = _provider(body.provider)
    try:
        secret = with_project(_credential_kind(body.kind), body.secret, body.project)
        ref = await registry.credentials.put(provider, body.kind, secret,
                                            user_id=_user(request), scope=body.scope)
    except CredentialError as exc:
        raise HTTPException(422, {"field": exc.field, "detail": str(exc)}) from exc
    except VaultRefused as exc:
        raise HTTPException(503, str(exc)) from exc
    registry.catalogue.invalidate()
    return {"credential": ref.public(), "saved": True}


@router.delete("/credentials/{ref}", status_code=204)
async def revoke_credential(request: Request, ref: str) -> None:
    registry = _registry(request)
    await registry.credentials.revoke(ref, user_id=_user(request))
    registry.catalogue.invalidate()


@router.post("/credentials/test")
async def test_credential(request: Request, body: TestCredential) -> dict[str, Any]:
    """Validate and probe **without storing** (K3). The secret exists only for this request."""
    from ..domain.llm import validate as validate_secret

    provider = _provider(body.provider)
    kind = _credential_kind(body.kind)
    try:
        parsed = validate_secret(kind, with_project(kind, body.secret, body.project))
    except CredentialError as exc:
        return {"ok": False, "field": exc.field, "detail": str(exc),
                "copy": f"{exc.field}: {exc}"}
    registry = _registry(request)
    spec = await registry.catalogue.find(body.model or _first_model_for(registry, provider),
                                        _user(request))
    if spec is None:
        return {"ok": True, "detail": "the key is well formed; add a model to test it against",
                "credential": parsed.public()}
    from ..adapters.llm.providers import adapter_for
    from ..ports import Secret

    adapter = adapter_for(spec.id.provider)
    desc = adapter.descriptor(spec, project=parsed.project_hint)
    state, detail = await adapter.probe(desc, Secret(value=parsed.secret, kind=kind.value))
    return {"ok": state == "available", "state": state, "detail": detail,
            "credential": parsed.public()}


def _first_model_for(registry, provider: ProviderKind) -> str:
    cat = registry.catalogue.last()
    if cat is None:
        return ""
    hit = next((m for m in cat.models if m.id.provider is provider), None)
    return hit.id.value if hit else ""


def _credential_kind(value: str) -> CredentialKind:
    try:
        return CredentialKind(value)
    except ValueError:
        raise HTTPException(422, f"{value!r} is not a credential kind") from None


def _cannot_save(registry) -> str:
    source = registry.source
    if source == "degraded":
        return ("Keys cannot be saved: the model database is unreachable. "
                "Databricks models work. External models need a key.")
    return "Keys cannot be saved: no key-encryption key is configured for this app."


# -- provenance --------------------------------------------------------------
@router.get("/sessions/{sid}/turns")
async def session_turns(request: Request, sid: str) -> dict[str, Any]:
    """Which model each turn used. Insert-once, so a later switch cannot rewrite history (FR-10)."""
    registry = _registry(request)
    return {"session": sid, "turns": await registry.store.turn_models(sid)}


def map_error(exc: Exception) -> HTTPException:
    """One place that turns a domain failure into a status. Nothing else in a route inspects a type."""
    if isinstance(exc, UnknownModel):
        # 422, not 404: an id the catalogue cannot resolve is a bad request at the boundary (A1), which
        # is the status the pre-registry catalogue returned. The detail routes answer 404 for a GET.
        return HTTPException(422, str(exc))
    if isinstance(exc, NotGranted):
        return HTTPException(403, str(exc))
    if isinstance(exc, NoCredential):
        return HTTPException(409, str(exc))
    if isinstance(exc, NotSelectable):
        return HTTPException(409, str(exc))
    if isinstance(exc, ModelError):
        return HTTPException(exc.status, str(exc))
    if isinstance(exc, CredentialError):
        return HTTPException(422, {"field": exc.field, "detail": str(exc)})
    return HTTPException(500, "the model could not be resolved")
