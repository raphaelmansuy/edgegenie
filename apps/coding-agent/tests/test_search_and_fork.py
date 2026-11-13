"""Search inside conversations (`[R-15]`) and forking one (`[R-16]`).

Both are cheap here for one reason: the journal is an ordered, addressable log. So both are tested as what
they are — a query and a prefix — and then through the routes, because a pure function nobody calls is the
defect this repository has found more than once.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# `tests/` is not a package on the path when pytest runs from the app folder; the other suites insert it
# the same way so `make_client` can be imported rather than re-implemented.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from api.domain.journal_ops import Event, can_fork, fork_point, fork_prefix, rank, search


def ev(seq: int, type_: str, turn: str = "", text: str = "") -> Event:
    return Event(seq, type_, turn, text)


# ============================================================== [R-16] fork
CONVO = [
    ev(1, "turn.started", "t1", "write the notebook"),
    ev(2, "message.delta", "t1", "I wrote it. It has five cells."),
    ev(3, "turn.completed", "t1"),
    ev(4, "turn.started", "t2", "now run it"),
    ev(5, "message.delta", "t2", "it returned 5 rows"),
    ev(6, "turn.blocked", "t2", "requirements without verified evidence"),
]


def test_a_fork_copies_the_prefix_up_to_that_turn():
    prefix = fork_prefix(CONVO, turn_id="t1")
    assert [e.seq for e in prefix] == [1, 2, 3], "the fork took more than the prefix"


def test_a_fork_at_the_last_turn_copies_everything():
    assert [e.seq for e in fork_prefix(CONVO, turn_id="t2")] == [1, 2, 3, 4, 5, 6]


def test_a_fork_keeps_a_BLOCKED_turn_as_it_was():
    """A "clean" fork would be a rewrite of the past. A user branching to try a different ending still needs
    to see the ending they had."""
    prefix = fork_prefix(CONVO, turn_id="t2")
    assert any(e.type == "turn.blocked" for e in prefix)


def test_a_turn_that_never_finished_cannot_be_forked_from():
    """Cutting mid-turn would open a session on a spinner forever."""
    open_turn = [ev(1, "turn.started", "t9", "x"), ev(2, "message.delta", "t9", "partway")]
    assert not can_fork(open_turn, "t9")
    assert fork_prefix(open_turn, turn_id="t9") is None


def test_an_unknown_turn_cannot_be_forked_from():
    assert not can_fork(CONVO, "nope")


def test_a_turn_with_several_terminal_events_forks_at_the_last():
    """A turn that was audited can emit more than one terminal-ish event; the fork belongs at its real end."""
    events = CONVO + [ev(7, "turn.completed", "t2")]
    assert fork_point(events, "t2") == 7
    assert [e.seq for e in fork_prefix(events, turn_id="t2")][-1] == 7


# ============================================================== [R-15] search
def test_search_finds_the_turn_not_just_the_conversation():
    hits, more = search(CONVO, "five cells", session_id="s1")
    assert not more and len(hits) == 1
    assert hits[0].turn_id == "t1"
    assert "five cells" in hits[0].snippet


def test_search_is_an_AND_across_words():
    """`gold late` must not return every conversation that mentions gold."""
    events = [ev(1, "message.delta", "t1", "gold arrived late"), ev(2, "message.delta", "t1", "gold only")]
    hits, _ = search(events, "gold late", session_id="s1")
    assert len(hits) == 1 and hits[0].seq == 1


def test_search_is_case_insensitive():
    assert search(CONVO, "FIVE CELLS", session_id="s1")[0]


def test_search_finds_nothing_in_a_redacted_secret():
    """`[E-19]`: the redaction happened before the commit, and a search that could undo it would undo the
    reason it exists."""
    redacted = [ev(1, "turn.started", "t1", "my key is [redacted: API key]")]
    hits, _ = search(redacted, "dapi1234", session_id="s1")
    assert hits == []


def test_search_reports_that_there_are_more():
    many = [ev(i, "message.delta", f"t{i}", "revenue") for i in range(1, 30)]
    hits, more = search(many, "revenue", session_id="s1", limit=5)
    assert len(hits) == 5 and more


def test_search_returns_newest_first():
    hits, _ = search(CONVO, "the", session_id="s1")
    assert [h.seq for h in hits] == sorted((h.seq for h in hits), reverse=True)


def test_an_empty_query_finds_nothing_rather_than_everything():
    assert search(CONVO, "   ", session_id="s1") == ([], False)


def test_an_empty_text_event_is_not_a_match():
    """A `turn.completed` carries no words; it must not match every query."""
    events = [ev(1, "turn.completed", "t1", "")]
    assert search(events, "anything", session_id="s1") == ([], False)


def test_rank_prefers_a_turn_the_caller_names():
    hits, _ = search(CONVO, "the", session_id="s1")
    preferred = rank(hits, prefer_turns={"t1"})
    assert preferred[0].turn_id == "t1"
    assert rank(hits, prefer_turns=set()) == hits


# ============================================================== through the routes
@pytest.fixture()
def client():
    """`make_client` builds the app with the fake agent; it takes a scenario, not a path."""
    from test_api import make_client  # the repository's one TestClient builder

    return make_client()


def test_the_search_route_answers_and_is_empty_for_no_query(client):
    r = client.get("/api/search", params={"q": ""})
    assert r.status_code == 200
    assert r.json()["hits"] == []


def test_the_search_route_returns_hits_shape(client):
    r = client.get("/api/search", params={"q": "revenue"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"hits", "more", "query"}
    for hit in body["hits"]:
        assert set(hit) >= {"sessionId", "turnId", "seq", "snippet", "title"}


def test_forking_an_unknown_session_is_404(client):
    r = client.post("/api/sessions/nope/fork", json={"turnId": "t1"})
    assert r.status_code == 404


def test_forking_an_unknown_turn_is_422_with_a_sentence(client):
    created = client.post("/api/sessions", json={"folder": "/Users/x/agent_scratch"}).json()
    r = client.post(f"/api/sessions/{created['id']}/fork", json={"turnId": "does-not-exist"})
    assert r.status_code == 422
    assert "never finished" in r.json()["detail"]
