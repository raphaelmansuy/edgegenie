"""Ledger state is separate from the transcript. Every update has an expected version."""

from typing import Protocol


async def ledger_rows(store, kind, **filters):
    """Consume every bounded page when a service needs a complete decision set."""
    cursor = ""
    while True:
        page = await store.page(kind, cursor=cursor, limit=100, **filters)
        for row in page["items"]:
            yield row
        cursor = page["nextCursor"]
        if not cursor:
            return


class LedgerStore(Protocol):
    durable: bool

    async def get(self, kind: str, key: str) -> dict: ...
    async def put(self, kind: str, row: dict, expected: int | None = None) -> dict: ...
    async def page(
        self,
        kind: str,
        *,
        session_id: str = "",
        owner: str = "",
        cursor: str = "",
        limit: int = 50,
        states: tuple[str, ...] = (),
    ) -> dict: ...
    async def reserve(self, kind: str, key: str, row: dict) -> tuple[dict, bool]: ...
    async def batch(self, writes: list[tuple[str, dict, int | None]]) -> list[dict]: ...
    async def commit_transition(self, journal, event, snapshot: dict, turn: dict): ...
    async def storage(self, sid: str) -> dict: ...
    async def purge_session(self, journal, sid: str) -> None: ...
    async def prune_previous(self, before: float, limit: int = 100) -> int: ...
    async def prune_wakeups(self, limit: int = 100) -> int: ...
    async def close(self) -> None: ...
