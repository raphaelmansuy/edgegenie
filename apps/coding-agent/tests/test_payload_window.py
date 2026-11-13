"""The payload window: a truncation that parses. `[R-3]`, `[F-2]`.

The defect: `_trim` byte-sliced the serialised payload, so a result over the budget was **not JSON**.
Measured on a 200-table reply, `json.loads` raised
`Invalid control character at: line 204 column 29 (char 6000)`.

Every test here is written from the failure it prevents, not from the implementation:

  * the payload parses, at every budget, for every shape;
  * the rendered page **fits the budget it was given** — the first implementation overran by ~1 200
    characters because it estimated per-item cost and `indent=2` indents by nesting depth;
  * paging from `next_offset` reconstructs the original list **exactly**;
  * one oversized item terminates instead of looping;
  * a payload that fits is returned **byte-identically**, so no existing caller's assertion moves.
"""

from __future__ import annotations

import json

import pytest

from api.domain.payload import render, window

BIG = {"tables": [
    {"name": f"catalog.schema.table_with_a_fairly_long_name_{i}", "type": "MANAGED",
     "comment": "a comment about this table"}
    for i in range(200)
]}


# ---------------------------------------------------------------- the defect, directly
def test_the_payload_that_used_to_be_unparseable_now_parses():
    """The exact shape that produced `Invalid control character at char 6000`."""
    out = render(BIG, 6000)
    parsed = json.loads(out)          # would raise before [R-3]
    assert parsed["returned"] < parsed["total"]
    assert parsed["next_offset"] == parsed["returned"]


@pytest.mark.parametrize("budget", [400, 1500, 3000, 6000, 20_000])
def test_every_page_parses_and_fits_the_budget_it_was_given(budget):
    """A bounded payload that overruns its own bound is not bounded."""
    out = render(BIG, budget)
    assert json.loads(out), "the page is not parseable JSON"
    assert len(out) <= budget, f"rendered {len(out)} chars for a budget of {budget}"


# ---------------------------------------------------------------- paging is lossless
@pytest.mark.parametrize("budget", [400, 1500, 3000])
def test_paging_from_next_offset_reconstructs_the_list_exactly(budget):
    got: list[dict] = []
    offset, pages = 0, 0
    while True:
        page = json.loads(render(BIG, budget, offset))
        got += page["tables"]
        pages += 1
        assert pages < 500, "paging did not terminate"
        if page["next_offset"] is None:
            break
        offset = page["next_offset"]
    assert got == BIG["tables"], "paging lost or reordered an item"


def test_the_last_page_says_it_is_the_last():
    page = json.loads(render(BIG, 6000, offset=len(BIG["tables"]) - 1))
    assert page["next_offset"] is None
    assert page["returned"] == 1


def test_an_offset_past_the_end_is_an_empty_complete_page_not_an_error():
    page = json.loads(render(BIG, 6000, offset=10_000))
    assert page["tables"] == []
    assert page["returned"] == 0
    assert page["next_offset"] is None


def test_a_negative_offset_is_read_as_zero_rather_than_raising():
    """A tool is not the place to punish a model's arithmetic; the response says where it started."""
    page = json.loads(render(BIG, 1500, offset=-5))
    assert page["tables"][0] == BIG["tables"][0]


# ---------------------------------------------------------------- the boundary
@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_the_boundary_between_fits_and_does_not_fit(delta):
    """An off-by-one in a truncation is the difference between "all" and "nearly all", and nothing in
    the payload would say which. So the budget exactly at the payload's length is tested in both
    directions."""
    whole = json.dumps(BIG, indent=2, default=str)
    budget = len(whole) + delta
    page = json.loads(render(BIG, budget))
    if delta >= 0:
        assert render(BIG, budget) == whole, "a payload that fits must be returned unchanged"
    else:
        assert page["returned"] < 200


# ---------------------------------------------------------------- edge cases [E-6] [E-7]
def test_one_item_larger_than_the_whole_budget_terminates():
    """[E-7]. A page of zero items cannot be paged; a slice is unparseable. Return the item whole."""
    payload = {"rows": [{"x": "y" * 9000}]}
    out = render(payload, 500)
    page = json.loads(out)
    assert page["truncated"] is True
    assert page["returned"] == 1
    assert page["next_offset"] is None, "an offset would loop forever on an item that never fits"


def test_a_dict_with_no_list_is_summarised_rather_than_sliced():
    payload = {f"k{i}": "v" * 200 for i in range(50)}
    page = json.loads(render(payload, 500))
    assert page["truncated"] is True
    assert page["total_keys"] == 50
    assert page["keys"], "the reader needs to know which keys exist"


def test_a_bare_list_windows_itself():
    page = json.loads(render([{"i": i} for i in range(500)], 800))
    assert page["items"][0] == {"i": 0}
    assert page["next_offset"] == page["returned"]


def test_a_bare_string_too_large_is_reported_not_sliced():
    page = json.loads(render("z" * 9000, 200))
    assert page["truncated"] is True
    assert page["kind"] == "str"


def test_an_empty_list_is_returned_unchanged():
    payload = {"tables": []}
    assert render(payload, 6000) == json.dumps(payload, indent=2, default=str)


# ---------------------------------------------------------------- identity fields survive
def test_a_page_keeps_the_keys_that_identify_what_is_being_paged():
    """An agent needs `catalog`/`path` even from a page. Dropping them turns a window into a different
    answer — a list of tables with no idea which schema they belong to."""
    payload = {"catalog": "main", "schema": "gold", "tables": BIG["tables"]}
    page = json.loads(render(payload, 1500))
    assert page["catalog"] == "main"
    assert page["schema"] == "gold"
    assert page["returned"] < 200


# ---------------------------------------------------------------- the window API
def test_window_reports_totals_even_when_nothing_changes():
    w, page = window(BIG, 10_000_000)
    assert w.complete and w.returned == w.total == 200
    assert page["next_offset"] is None
