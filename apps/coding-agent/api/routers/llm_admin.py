"""`/api/llm/config/*`: the screens an administrator uses to configure external models.

Everything here is written to the registry **database**. When the database is not reachable the
routes refuse with that reason instead of changing something that would vanish at the next restart:
a setting that looks saved and is not is worse than a setting that cannot be changed.

Two rules, both enforced here and tested:

* **who may write** is `APP_LLM_ADMINS` (emails). Empty means nobody. Reading the configuration is
  open to every signed-in user, because the picker already shows them the catalogue; only *changing*
  it for everyone needs a name on the list. Personal keys stay a per-user action (`/credentials`).
* **no response contains a credential.** A provider row says whether *a key exists*, never what it is.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..domain.llm import (
    Capability,
    InvalidModel,
    ModelId,
    ProviderKind,
    UnknownModel,
    custom_model,
)
from ..domain.llm.custom import EXTERNAL

log = logging.getLogger("app.api.llm.admin")
router = APIRouter(prefix="/api/llm/config")

#: Stores that can hold an administrator's choices. The seed and degraded stores cannot.
_WRITABLE = ("database", "memory")


class NewModel(BaseModel):
    provider: str = Field(min_length=2, max_length=40)
    model: str = Field(min_length=1, max_length=120)
    name: str = Field(default="", max_length=80)
    context: int = Field(default=128_000, ge=1)
    output: int = Field(default=8_000, ge=1)
    capability: str = Field(default="tools_and_reasoning", max_length=30)
    makeDefault: bool = False


class ModelPatch(BaseModel):
    enabled: bool


class DefaultModel(BaseModel):
    model: str = Field(min_length=3, max_length=200)


class ProviderPatch(BaseModel):
    enabled: bool | None = None
    baseUrl: str | None = Field(default=None, max_length=300)


def _registry(request: Request):
    registry = getattr(request.app.state, "llm", None)
    if registry is None:  # pragma: no cover - build() always wires it
        raise HTTPException(503, "the model registry is not configured")
    return registry


def _admins(request: Request) -> frozenset[str]:
    raw = getattr(request.app.state.settings, "llm_admins", "") or ""
    return frozenset(p.strip().lower() for p in raw.replace(";", ",").split(",") if p.strip())


def _who(request: Request) -> str:
    """The name to show and to record: the e-mail when the proxy gave one, else the user id.

    Behind the Databricks proxy `request.state.user_id` is `<numeric id>@<app id>`, which no
    administrator would write in a list and no auditor would recognise; the e-mail is both.
    """
    return (request.headers.get("x-forwarded-email") or request.state.user_id).strip()


def can_configure(request: Request) -> bool:
    """A listed e-mail or a listed user id. Either spelling works, so the list is easy to write."""
    admins = _admins(request)
    return any(n.strip().lower() in admins
               for n in (request.headers.get("x-forwarded-email", ""), request.state.user_id) if n)


def _writer(request: Request):
    """The store, once we know this user may write and the store can keep what they write."""
    if not can_configure(request):
        raise HTTPException(403, "only an administrator of this app can change the model configuration; "
                            "ask the owner to add you to APP_LLM_ADMINS")
    registry = _registry(request)
    if registry.source not in _WRITABLE:
        raise HTTPException(503, _not_saveable(registry))
    return registry


def _not_saveable(registry) -> str:
    if registry.source == "degraded":
        return "The model database is unreachable, so nothing can be saved. Try again in a minute."
    return ("This app has no model database, so configuration cannot be saved. "
            "Set APP_LLM_PG_ENDPOINT (Lakebase) and redeploy.")


def _model_row(spec, *, default: str) -> dict[str, Any]:
    row = spec.to_dict()
    row.update({
        "enabled": spec.enabled,
        "isDefault": spec.id.value == default,
        # Databricks rows follow discovery; only external rows can be switched off or removed.
        "managed": spec.id.provider is ProviderKind.DATABRICKS,
    })
    return row


@router.get("")
async def configuration(request: Request) -> dict[str, Any]:
    """Everything the configuration screen shows, including models that are switched off."""
    registry = _registry(request)
    store = registry.store
    models = await store.all_models() if hasattr(store, "all_models") else list(await store.models(""))
    cat = await registry.catalogue.catalogue(request.state.user_id, getattr(request.state, "groups", frozenset()))
    default = cat.default_model
    keys = {c.provider.value for c in await registry.credentials.list(user_id=request.state.user_id)}
    providers = []
    for row in await store.providers():
        kind = row.get("kind")
        providers.append({
            "id": row["id"], "name": row["display_name"], "kind": kind,
            "enabled": bool(row.get("enabled", True)), "baseUrl": row.get("base_url", "") or "",
            "wire": row.get("wire", ""),
            "external": kind != ProviderKind.DATABRICKS.value and kind != ProviderKind.FAKE.value,
            "hasKey": row["id"] in keys,
            "example": next((d.example for k, d in EXTERNAL.items() if k.value == kind), ""),
        })
    return {
        "source": registry.source,
        "location": getattr(store, "location", ""),
        "canConfigure": can_configure(request),
        "canSave": registry.source in _WRITABLE,
        "reason": "" if registry.source in _WRITABLE else _not_saveable(registry),
        "externalAllowed": registry.allow_external,
        "vault": {"mode": registry.credentials.mode, "available": registry.credentials.available},
        "default": default,
        "providers": providers,
        "models": [_model_row(m, default=default) for m in models],
    }


@router.post("/models", status_code=201)
async def add_model(request: Request, body: NewModel) -> dict[str, Any]:
    registry = _writer(request)
    try:
        provider = ProviderKind(body.provider)
        capability = Capability(body.capability)
    except ValueError:
        raise HTTPException(422, {"field": "provider", "detail": "unknown provider or capability"}) from None
    try:
        spec = custom_model(provider, body.model, display_name=body.name, context=body.context,
                            output=body.output, capability=capability, added_by=_who(request))
    except InvalidModel as exc:
        raise HTTPException(422, {"field": exc.field, "detail": exc.detail}) from exc
    store = registry.store
    if not any(p["id"] == provider.value for p in await store.providers()):
        raise HTTPException(422, {"field": "provider", "detail": f"{provider.value} is not set up in this registry"})
    try:
        await store.upsert_model(spec)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if body.makeDefault:
        await store.set_default_model(spec.id.value, _who(request))
        registry.catalogue.set_default(spec.id.value)
    registry.catalogue.invalidate()
    log.info("model added: %s by %s", spec.id.value, _who(request))
    return {"saved": True, "model": _model_row(spec, default=store.default_model)}


@router.patch("/models/{model_id:path}")
async def patch_model(request: Request, model_id: str, body: ModelPatch) -> dict[str, Any]:
    registry = _writer(request)
    spec = await _external(registry, model_id)
    if not body.enabled and await _default_of(registry, request) == spec.id.value:
        raise HTTPException(409, "this is the default model; choose another default before switching it off")
    await registry.store.set_model_enabled(spec.id.value, body.enabled)
    registry.catalogue.invalidate()
    return {"saved": True, "id": spec.id.value, "enabled": body.enabled}


@router.delete("/models/{model_id:path}", status_code=204)
async def remove_model(request: Request, model_id: str) -> None:
    registry = _writer(request)
    spec = await _external(registry, model_id)
    if await _default_of(registry, request) == spec.id.value:
        raise HTTPException(409, "this is the default model; choose another default before removing it")
    await registry.store.delete_model(spec.id.value)
    registry.catalogue.invalidate()


@router.put("/default")
async def set_default(request: Request, body: DefaultModel) -> dict[str, Any]:
    registry = _writer(request)
    try:
        canonical = ModelId.parse(body.model).value
    except UnknownModel:
        raise HTTPException(422, {"field": "model", "detail": f"{body.model!r} is not a model id"}) from None
    spec = await registry.catalogue.find(canonical, request.state.user_id)
    if spec is None or not spec.enabled:
        raise HTTPException(404, f"{canonical} is not in the catalogue, or is switched off")
    if not spec.selectable:
        raise HTTPException(409, spec.refusal or f"{canonical} cannot be chosen as a model right now")
    await registry.store.set_default_model(canonical, _who(request))
    registry.catalogue.set_default(canonical)
    return {"saved": True, "default": canonical}


@router.patch("/providers/{provider_id}")
async def patch_provider(request: Request, provider_id: str, body: ProviderPatch) -> dict[str, Any]:
    registry = _writer(request)
    row = next((p for p in await registry.store.providers() if p["id"] == provider_id), None)
    if row is None:
        raise HTTPException(404, f"{provider_id!r} is not a provider of this registry")
    if row.get("kind") in (ProviderKind.DATABRICKS.value, ProviderKind.FAKE.value):
        raise HTTPException(409, "the Databricks provider follows the workspace and cannot be edited here")
    if body.baseUrl:
        if not body.baseUrl.startswith("https://"):
            raise HTTPException(422, {"field": "baseUrl", "detail": "a provider address must start with https://"})
    await registry.store.update_provider(provider_id, enabled=body.enabled, base_url=body.baseUrl)
    registry.catalogue.invalidate()
    return {"saved": True, "id": provider_id}


async def _default_of(registry, request: Request) -> str:
    cat = await registry.catalogue.catalogue(request.state.user_id,
                                             getattr(request.state, "groups", frozenset()), refresh=True)
    return cat.default_model


async def _external(registry, model_id: str):
    spec = await registry.catalogue.find(model_id, "")
    if spec is None:
        raise HTTPException(404, f"{model_id!r} is not in the catalogue")
    if spec.id.provider in (ProviderKind.DATABRICKS, ProviderKind.FAKE):
        raise HTTPException(409, "Databricks models follow what the workspace serves and cannot be edited here")
    return spec
