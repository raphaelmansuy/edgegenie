"""A truncation the reader can SEE, and that always parses. Pure.

The defect this closes. Every tool returned through `_trim`, which was:

    text = json.dumps(payload, indent=2)
    if len(text) <= MAX_CHARS: return text
    return text[:MAX_CHARS] + f"\\n... [truncated, {len(text)} chars total]"

A byte-slice of a serialised object is not JSON. Measured on a 200-table `dbx_list_tables` reply:

    json.loads(_trim(payload))
    → JSONDecodeError: Invalid control character at: line 204 column 29 (char 6000)

The repository had already learned this twice — `read_notebook` grew an explicit `next_offset`, and
`grep_notebook` grew an explicit `no_matches` with a retry hint (`docs/genie-code-replacement-spec.md`
§4.8, §4.9, §4.11: *"a tool that returns an empty success is more dangerous than one that raises"*).
Neither fix reached `_trim`, which is the path twenty other tools use.

**The contract.** A caller either gets the whole payload, or gets a **window** that says:

    {"tables": [...], "returned": 38, "total": 200, "next_offset": 38}

`next_offset: null` means "this is everything". A reader that sees an offset knows it has not seen the
world, which is the only property that matters: an agent that *knows* it is missing data pages; an agent
handed a fragment reports it as the truth.

**Why the window is measured, not estimated.** The first implementation computed each item's serialised
cost and stopped as the running total approached the budget. That was wrong by ~1 200 characters on a
200-table reply, because `indent=2` adds indentation proportional to *nesting depth*, which a per-item
cost does not know about. The page is now **rendered and measured**: the largest prefix that fits is
found by halving, so the answer is exact at any depth. A bounded payload that overruns its own bound is
not bounded.

Two edge cases, both tested:
  * **one item larger than the whole budget** is returned whole, with `truncated: true` and
    `next_offset: null`. A page of zero items cannot be paged; a slice is unparseable; and refusing is
    worse than showing too much.
  * **the boundary** (`budget-1`, `budget`, `budget+1`) is tested, because an off-by-one in a truncation
    is the difference between "all" and "nearly all" and nothing says which.

`[R-3]`, `[E-6]`, `[E-7]`. Mirrored by `web/src/domain/paging.ts` for the "38 of 200" label.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Window:
    """One page of a payload, and what it is a page OF."""

    items: list[Any]
    returned: int
    total: int
    next_offset: int | None
    #: True when a single item could not fit and was returned whole anyway ([E-7]).
    oversize: bool = False

    @property
    def complete(self) -> bool:
        return self.next_offset is None


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, default=str)


def _items_of(payload: Any) -> tuple[str, list[Any]]:
    """The list to page, and the key it lives under. `""` means the payload WAS the list."""
    if isinstance(payload, list):
        return "", payload
    key = next((k for k, v in payload.items() if isinstance(v, list) and v), "")
    return key, list(payload[key]) if key else []


def _page(payload: Any, key: str, start: int, count: int, total: int) -> dict[str, Any]:
    """One candidate page, as the object that will be rendered.

    The ONE place a page's shape is decided, so what is measured and what is returned cannot differ —
    which is how the estimate-based version overran its own budget.
    """
    items = payload if isinstance(payload, list) else payload[key]
    end = start + count
    if isinstance(payload, list):
        out: dict[str, Any] = {"items": items[start:end]}
    else:
        # Every other key is kept: an agent needs the identity fields (`catalog`, `path`) even from a
        # page, and dropping them is how a window becomes a different answer.
        out = {k: v for k, v in payload.items() if k != key}
        out[key] = items[start:end]
    out["returned"] = count
    out["total"] = total
    out["next_offset"] = end if end < total else None
    return out


def window(payload: Any, budget: int, offset: int = 0) -> tuple[Window, dict[str, Any]]:
    """The largest page of `payload` that renders within `budget`, plus the object to render.

    Returning both is deliberate: the caller renders exactly what was measured. A function that returns
    only the `Window` forces the caller to reconstruct the page, and a reconstruction can disagree with
    the measurement by one key — which is a budget overrun nobody notices.
    """
    key, items = _items_of(payload)
    total = len(items)
    start = max(0, min(int(offset or 0), total))
    if start >= total:
        return Window([], 0, total, None), _page(payload, key, start, 0, total)

    # Halving, then a settle: `lo` is known to fit, `hi` is known not to.
    lo, hi = 0, total - start
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(_dump(_page(payload, key, start, mid, total))) <= budget:
            lo = mid
        else:
            hi = mid - 1

    if lo == 0:
        # Not even one item fits. Return it whole: a page of zero items cannot be paged, and a slice is
        # unparseable. `truncated` says why it is bigger than the budget ([E-7]).
        page = _page(payload, key, start, 1, total)
        page["next_offset"] = None
        page["truncated"] = True
        return Window([items[start]], 1, total, None, oversize=True), page

    end = start + lo
    w = Window(list(items[start:end]), lo, total, end if end < total else None)
    return w, _page(payload, key, start, lo, total)


def render(payload: Any, budget: int, offset: int = 0) -> str:
    """The text a tool returns: either the whole payload, or a page of it. **Always parses.**

    A payload that fits is returned **byte-identically** to before this module existed, so no existing
    caller's assertion moves. Only an overflowing payload changes shape — and that is the case that
    used to be unparseable.
    """
    whole = _dump(payload)
    if len(whole) <= budget:
        return whole

    if not isinstance(payload, (list, dict)):
        # A string or a number too large to return: say so, in a form that parses.
        return _dump({"truncated": True, "kind": type(payload).__name__, "length": len(whole)})

    if isinstance(payload, list) and not payload:
        return whole
    if isinstance(payload, dict) and not any(isinstance(v, list) and v for v in payload.values()):
        # A dict with no list cannot be paged, so it is summarised rather than sliced.
        keys = list(payload)[:40]
        return _dump({"truncated": True, "total_keys": len(payload), "keys": keys,
                      "note": "this object is too large to return whole; ask for one field"})

    _w, page = window(payload, budget, offset)
    return _dump(page)
