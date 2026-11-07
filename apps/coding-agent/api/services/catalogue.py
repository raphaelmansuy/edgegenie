"""Configurable model catalogue, in a single validated place, with the old contract intact.

`StaticModelCatalog` shipped first, and its `allowed`/`check` pair is what the orchestrator and the
routes already call. This class keeps that shape exactly and puts the registry behind it — one
interface, one implementation per source (08 §5, "the port is extended, not duplicated").

`allowed_models` in `Settings` is still honoured as an *additional* allow-list for tests and demo
mode. It is no longer the source of truth for the deployed app: the seed file and discovery are.
"""

from __future__ import annotations

from ..config import Settings
from ..domain.llm import ModelState, ProviderKind

#: Demo and test models, offered by the fake agent. Not a provider: a replay.
FAKE_PREFIX = "fake/"


class SettingsModelCatalog:
    """The pre-registry contract, backed by the registry when one is wired.

    `static` keeps behaviour identical for the tests and for demo mode, where `allowed_models` is the
    whole catalogue and no store exists.
    """

    def __init__(self, cfg: Settings, service=None, extra_allowed: dict[str, list[str]] | None = None) -> None:
        self._cfg = cfg
        self._service = service
        self._extra = extra_allowed or {}

    # -- the old contract -----------------------------------------------------
    def allowed(self, user_id: str) -> list[dict]:
        """`[{id, name, default}]`, synchronously, for the orchestrator's existing calls.

        A registry read is async, so when a service is wired the caller should use `specs()` instead;
        this method then answers from the static list, which is a *subset* guard, not the catalogue.
        """
        if self._service is not None:
            cached = self._service.last()
            if cached is not None:
                return [
                    {"id": m.id.value, "name": m.display_name, "default": m.id.value == cached.default_model}
                    for m in cached.models
                    if m.selectable or m.state is ModelState.NOT_ENABLED
                ]
        ids = list(self._cfg.allowed_models) + self._extra.get(user_id, [])
        return [
            {"id": m, "name": m.split("/")[-1], "default": m == self._cfg.default_model}
            for m in dict.fromkeys(ids)
        ]

    def check(self, user_id: str, model: str) -> None:
        """Refuse a model the catalogue does not offer. The message names the model and the reason."""
        from ..domain.llm import ModelError, ModelId, NotSelectable, UnknownModel

        try:
            mid = ModelId.parse(model)
        except ModelError:
            raise UnknownModel(model) from None
        if mid.provider is ProviderKind.FAKE:
            if model not in {m["id"] for m in self.allowed(user_id)}:
                raise NotSelectable(model, f"{model} is not offered in demo mode")
            return
        cached = self._service.last() if self._service is not None else None
        if cached is None:
            # No catalogue has been assembled yet: fall back to the configured allow-list, which is
            # exactly today's behaviour and therefore safe during a boot race.
            if model in {m["id"] for m in self.allowed(user_id)}:
                return
            raise UnknownModel(model)
        spec = cached.find(mid.value)
        if spec is None:
            raise UnknownModel(mid.value)
        if not spec.selectable:
            raise NotSelectable(mid.value, spec.refusal or f"{spec.display_name} is not available here")

    # -- the extended contract ------------------------------------------------
    async def specs(self, user_id: str):
        if self._service is None:
            return []
        cat = await self._service.catalogue(user_id)
        return list(cat.models)

    async def find(self, model_id: str):
        if self._service is None:
            return None
        return await self._service.find(model_id)

    async def grants(self, model_id: str):
        if self._service is None:
            return None
        return await self._service.grant_for(model_id)
