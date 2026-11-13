"""One registration serves tool dispatch, attachment resolution, capability probing and views."""

from dataclasses import dataclass
from .asset import WorkError


@dataclass(frozen=True)
class Registration:
    kind: str
    label: str
    scope: str
    handler: object
    description: str


class AssetRegistry:
    def __init__(self, registrations=()):
        self._items = {item.kind: item for item in registrations}

    def register(self, item: Registration):
        if item.kind in self._items:
            raise ValueError(f"duplicate asset handler: {item.kind}")
        self._items[item.kind] = item

    def unregister(self, kind):
        self._items.pop(kind, None)

    def handler(self, kind: str):
        return self.entry(kind).handler

    def entry(self, kind: str) -> Registration:
        try:
            return self._items[kind]
        except KeyError:
            raise WorkError(f"Asset kind {kind} is unavailable.", 422) from None

    def entries(self):
        return tuple(self._items.values())
