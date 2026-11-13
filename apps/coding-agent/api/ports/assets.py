"""Segregated asset capabilities. Unsupported operations are absent from a handler."""

from typing import Protocol
from ..domain.asset import Actor, AssetContent, AssetRef, Plan


class Readable(Protocol):
    async def read(self, ref: AssetRef, who: Actor) -> AssetContent: ...
    async def describe(self, ref: AssetRef, who: Actor) -> dict: ...


class Listable(Protocol):
    async def find(self, query: str, who: Actor, limit: int) -> list[dict]: ...


class Changeable(Protocol):
    async def plan(
        self, ref: AssetRef, base: str, operations: list[dict], who: Actor, *, content: str | None = None
    ) -> Plan: ...
    async def apply(self, plan: Plan, who: Actor) -> AssetContent: ...
    async def restore(
        self, ref: AssetRef, expect: str, content: str, who: Actor, language: str
    ) -> AssetContent: ...


class Runnable(Protocol):
    async def submit(self, ref: AssetRef, params: dict, who: Actor, key: str) -> dict: ...
    async def observe(self, native_id: str, who: Actor) -> dict: ...
    async def cancel(self, native_id: str, who: Actor) -> None: ...


class Removable(Protocol):
    async def remove(self, ref: AssetRef, expect: str, who: Actor) -> None: ...


class ResourceProducing(Protocol):
    async def created_resources(self, native_id: str, who: Actor) -> list[dict]: ...


class FragmentReadable(Protocol):
    def read_fragment(self, value: AssetContent, *, cell: int | None = None) -> tuple[str, dict]: ...
