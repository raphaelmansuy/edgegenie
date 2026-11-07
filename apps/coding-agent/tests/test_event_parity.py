"""Event vocabulary parity between Python and TypeScript.

`web/src/domain/events.ts` must name exactly the events `api/domain/events.py` can emit. A mismatch
is a silent bug: the server sends `document.saved`, the client has no branch for it, and the write
disappears from the transcript without an error anywhere.

The mirror is a JSON fixture rather than a regex over the TypeScript, because the TS file is the one
that has to be *edited* when an event is added, and a fixture makes that edit explicit. This test is
the thing that forces it: adding an event in Python without updating the client fails here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from api.domain.events import EVENT_TYPES

ROOT = Path(__file__).resolve().parents[1]
TS_EVENTS = ROOT / "web" / "src" / "domain" / "events.ts"
PARITY = ROOT / "web" / "src" / "domain" / "event-parity.json"


def ts_event_types() -> set[str]:
    """Every event name the TypeScript union declares."""
    source = TS_EVENTS.read_text()
    block = source.split("export type EventType", 1)[1].split("export const", 1)[0]
    return set(re.findall(r'"([a-z][a-z_.]*\.[a-z_.]+)"', block))


def test_python_and_typescript_name_the_same_events():
    """The real check: the two vocabularies are one vocabulary."""
    py = set(EVENT_TYPES)
    ts = ts_event_types()
    missing_in_ts = sorted(py - ts)
    extra_in_ts = sorted(ts - py)
    assert not missing_in_ts, f"the client has no branch for: {missing_in_ts}"
    assert not extra_in_ts, f"the client expects events the server never sends: {extra_in_ts}"


def test_the_parity_fixture_is_current():
    """The JSON mirror is what the client test reads, so it must not drift either."""
    recorded = set(json.loads(PARITY.read_text())["types"])
    assert recorded == set(EVENT_TYPES), (
        "re-run: python -c \"import json;from api.domain.events import EVENT_TYPES;"
        "json.dump({'types':list(EVENT_TYPES)},open('web/src/domain/event-parity.json','w'),indent=1)\""
    )
