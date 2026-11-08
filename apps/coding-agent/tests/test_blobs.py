"""The blob store's contract, run against every implementation.

One list of behaviours, two classes, no skips. That is what makes the two interchangeable rather than
merely similar — and it is what enforces Liskov as a fact instead of as a claim in a document
(specs/009 [BLB-5], [06 §veto V3]).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from api.adapters.blob import FileBlobStore, MemoryBlobStore
from api.domain.blob import Family, validate

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
CSV = b"hour,trips\n18,42\n19,51\n"


class Clock:
    """A movable clock, so a 24-hour sweep is a test rather than a wait."""

    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


@pytest.fixture(params=["memory", "files"])
def store(request):
    clock = Clock()
    if request.param == "memory":
        yield MemoryBlobStore(clock=clock), clock
    else:
        with tempfile.TemporaryDirectory() as tmp:
            yield FileBlobStore(Path(tmp), clock=clock), clock


def spec_for(name: str, raw: bytes, *, vision: bool = True):
    return validate(name, raw, "", model_sees_images=vision)


# -- round trip ----------------------------------------------------------------------------------

async def test_put_then_read_returns_the_same_bytes(store):
    s, _ = store
    row = await s.put("ses_1", "user_a", spec_for("shot.png", PNG), PNG)
    assert row.state == "ready"
    assert await s.bytes_for(row.id, "user_a") == PNG


async def test_put_records_the_metadata_it_promised(store):
    s, _ = store
    # A declared type is part of the metadata: without one, text carries no signature of its own and
    # `text/plain` is the honest answer.
    row = await s.put("ses_1", "user_a", validate("data.csv", CSV, "text/csv", model_sees_images=True), CSV)
    meta = await s.meta(row.id, "user_a")
    assert meta.mime == "text/csv"
    assert meta.family == Family.TEXT.value
    assert meta.size == len(CSV)
    assert meta.sha256 == spec_for("data.csv", CSV).sha256
    assert meta.original_name == "data.csv"


async def test_the_id_is_unguessable_and_matches_the_pattern(store):
    s, _ = store
    row = await s.put("ses_1", "user_a", spec_for("a.csv", CSV), CSV)
    assert row.id.startswith("blb_") and len(row.id) == 16


# -- idempotence ---------------------------------------------------------------------------------

async def test_the_same_bytes_twice_is_one_blob(store):
    """A retry must not produce a second row that looks like a different file."""
    s, _ = store
    one = await s.put("ses_1", "user_a", spec_for("a.csv", CSV), CSV)
    two = await s.put("ses_1", "user_a", spec_for("a.csv", CSV), CSV)
    assert one.id == two.id


async def test_the_same_bytes_in_another_session_is_a_separate_blob(store):
    s, _ = store
    one = await s.put("ses_1", "user_a", spec_for("a.csv", CSV), CSV)
    two = await s.put("ses_2", "user_a", spec_for("a.csv", CSV), CSV)
    assert one.id != two.id


# -- ownership -----------------------------------------------------------------------------------

async def test_another_users_blob_is_not_found(store):
    """404, not 403: a 403 would confirm the id exists (spec 009 [E-20], [BLB-4])."""
    s, _ = store
    row = await s.put("ses_1", "user_a", spec_for("a.csv", CSV), CSV)
    with pytest.raises(LookupError):
        await s.meta(row.id, "user_b")
    with pytest.raises(LookupError):
        await s.bytes_for(row.id, "user_b")


async def test_an_unknown_id_is_not_found(store):
    s, _ = store
    with pytest.raises(LookupError):
        await s.meta("blb_000000000000", "user_a")


# -- lifecycle -----------------------------------------------------------------------------------

async def test_mark_attached_moves_the_state_and_counts_a_reference(store):
    s, _ = store
    row = await s.put("ses_1", "user_a", spec_for("a.csv", CSV), CSV)
    await s.mark_attached(row.id, "turn_1", "a.csv")
    assert (await s.meta(row.id, "user_a")).state == "attached"
    assert await s.refcount(row.id) == 1


async def test_two_turns_referencing_one_blob_count_twice(store):
    s, _ = store
    row = await s.put("ses_1", "user_a", spec_for("a.csv", CSV), CSV)
    await s.mark_attached(row.id, "turn_1", "a.csv")
    await s.mark_attached(row.id, "turn_2", "a.csv")
    assert await s.refcount(row.id) == 2


# -- the sweeper, and the race it must not lose ---------------------------------------------------

async def test_sweep_deletes_an_unreferenced_ready_blob_after_24h(store):
    s, clock = store
    row = await s.put("ses_1", "user_a", spec_for("a.csv", CSV), CSV)
    clock.now += 24 * 60 * 60 + 1
    report = await s.sweep(clock.now)
    assert report["ready"] == 1
    with pytest.raises(LookupError):
        await s.meta(row.id, "user_a")


async def test_sweep_keeps_a_ready_blob_inside_24h(store):
    s, clock = store
    row = await s.put("ses_1", "user_a", spec_for("a.csv", CSV), CSV)
    clock.now += 60
    assert (await s.sweep(clock.now))["ready"] == 0
    assert (await s.meta(row.id, "user_a")).id == row.id


async def test_sweep_NEVER_deletes_a_referenced_blob(store):
    """[V3]: if a sweep can delete a blob a turn references, the feature is unsafe to ship."""
    s, clock = store
    row = await s.put("ses_1", "user_a", spec_for("a.csv", CSV), CSV)
    await s.mark_attached(row.id, "turn_1", "a.csv")
    clock.now += 365 * 24 * 60 * 60          # a year
    assert (await s.sweep(clock.now))["ready"] == 0
    assert await s.bytes_for(row.id, "user_a") == CSV


async def test_sweep_reports_what_it_deleted(store):
    s, clock = store
    await s.put("ses_1", "user_a", spec_for("a.csv", CSV), CSV)
    await s.put("ses_1", "user_a", spec_for("b.png", PNG), PNG)
    clock.now += 25 * 60 * 60
    report = await s.sweep(clock.now)
    assert report == {"pending": 0, "ready": 2}


# -- session deletion ----------------------------------------------------------------------------

async def test_deleting_a_session_removes_its_bytes(store):
    """[E-29]: archiving must not orphan bytes."""
    s, _ = store
    keep = await s.put("ses_keep", "user_a", spec_for("k.csv", CSV), CSV)
    await s.put("ses_gone", "user_a", spec_for("g.csv", CSV), CSV)
    gone = await s.delete_session("ses_gone")
    assert gone == 1
    assert await s.bytes_for(keep.id, "user_a") == CSV


async def test_deleting_a_session_leaves_another_intact(store):
    s, _ = store
    other = await s.put("ses_2", "user_a", spec_for("o.csv", CSV), CSV)
    await s.delete_session("ses_1")
    assert (await s.meta(other.id, "user_a")).session_id == "ses_2"
