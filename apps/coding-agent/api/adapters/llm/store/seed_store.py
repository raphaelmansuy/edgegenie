"""The seed catalogue as a store: the app's catalogue when there is no database (C-5).

This is what makes "the app boots without a database" a design rather than a hope. It is a
`MemoryRegistryStore` pre-loaded from `seed/llm_models.yaml`, with `source` set so the API can say
where the list came from — the settings screen states it, so a user who adds a key to an app in this
mode is told it was not saved instead of discovering it next session.

Grants are never seeded (05 §llm_model_grant): every user sees every seeded model, which is today's
behaviour and therefore not a regression.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ....domain.llm import ModelSpec, ModelState
from .memory import MemoryRegistryStore
from .seed import Seed, load as load_seed


class SeedRegistryStore(MemoryRegistryStore):
    """A catalogue built from the seed file. `source` is `seed` or `degraded`, never `database`."""

    def __init__(self, seed: Seed | None = None, *, source: str = "seed",
                 path: Path | str | None = None) -> None:
        super().__init__(source=source)
        self.seed = seed if seed is not None else load_seed(path)
        self.default_model = self.seed.default_model

    @classmethod
    async def open(cls, *, path: Path | str | None = None,
                   source: str = "seed") -> SeedRegistryStore:
        """Async construction, so `main.build()` can select a store uniformly."""
        store = cls(path=path, source=source)
        await store.load()
        return store

    async def load(self) -> None:
        for provider in self.seed.providers:
            await self.upsert_provider(
                {
                    "id": provider.id,
                    "display_name": provider.display_name,
                    "kind": provider.kind.value,
                    "wire": provider.wire.value,
                    "base_url": provider.base_url,
                    "npm": provider.npm,
                    "enabled": True,
                }
            )
        for spec in self.seed.models:
            self._models[spec.id.value] = spec

    def mark_all_unknown(self, detail: str) -> None:
        """A degraded boot keeps every row and marks health unknown: absence of evidence, not absence."""
        for key, spec in list(self._models.items()):
            if spec.state is ModelState.UNKNOWN:
                self._models[key] = replace(spec, detail=detail[:400])

    def keep(self, specs: list[ModelSpec]) -> None:
        """Overlay whatever was last known, so a lost connection does not change the list (E-15)."""
        for spec in specs:
            self._models[spec.id.value] = spec
