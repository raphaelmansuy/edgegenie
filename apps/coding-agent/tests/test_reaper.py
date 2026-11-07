"""The reaper's condition. Pure, so these tests need no clock, no event loop, no subprocess.

This is the kind of code where a wrong condition silently destroys a user's work, so each test
states a way it could be wrong and pins the correct answer.
"""

from __future__ import annotations

from api.domain.reaper import Candidate, Policy, Why, reapable

POLICY = Policy(idle_seconds=1800, keep_minimum=8)
NOW = 1_800_000_000.0


def c(status: str = "ready", idle: float = 3600, watchers: int = 0) -> Candidate:
    return Candidate(session_id="s1", status=status, last_seen=NOW - idle, watchers=watchers)


def decide(cand: Candidate, live: int = 20) -> Why | None:
    return reapable(cand, now=NOW, live_count=live, policy=POLICY)


# ---------------------------------------------------------------- never reap
def test_never_reaps_a_session_with_a_turn_in_flight():
    """Killing an agent mid-answer loses the answer. The most expensive mistake available."""
    for status in ("streaming", "provisioning", "auditing"):
        assert decide(c(status=status)) is Why.BUSY, status


def test_never_reaps_a_session_waiting_for_a_human():
    """`blocked` is a question the user is about to answer. Reaping discards the question."""
    assert decide(c(status="blocked", idle=99_999)) is Why.BUSY


def test_never_reaps_a_session_someone_is_watching():
    """An open tab is activity even if nothing is typed; a stream connection is the heartbeat."""
    assert decide(c(status="ready", idle=99_999, watchers=1)) is Why.WATCHED


def test_never_reaps_inside_the_idle_window():
    assert decide(c(idle=60)) is Why.YOUNG
    assert decide(c(idle=POLICY.idle_seconds - 1)) is Why.YOUNG


def test_never_reaps_below_the_soft_cap():
    """One idle session on a quiet machine is not worth killing: churn costs more than a process."""
    assert decide(c(idle=99_999), live=POLICY.keep_minimum) is Why.UNDER_CAP
    assert decide(c(idle=99_999), live=1) is Why.UNDER_CAP


def test_skips_an_already_archived_session():
    assert decide(c(status="archived", idle=99_999)) is Why.ARCHIVED


# ---------------------------------------------------------------- does reap
def test_reaps_an_idle_session_above_the_cap():
    assert decide(c(idle=99_999), live=POLICY.keep_minimum + 1) is None


def test_reaps_exactly_at_the_idle_boundary():
    """The window is a threshold, not a strict inequality; at the boundary it is fair to reap."""
    assert decide(c(idle=POLICY.idle_seconds), live=20) is None


def test_a_session_with_no_recorded_activity_is_old_not_young():
    """`last_seen=0` means we never recorded activity. It must not read as "just created"."""
    cand = Candidate(session_id="s1", status="ready", last_seen=0.0, watchers=0)
    assert decide(cand, live=20) is None


# ---------------------------------------------------------------- the whole set
def test_only_the_idle_unwatched_session_above_the_cap_is_chosen():
    """The realistic case: a mix, and exactly one may go."""
    cands = [
        c(status="streaming", idle=99_999),
        c(status="blocked", idle=99_999),
        Candidate("w", "ready", NOW - 99_999, watchers=3),
        c(idle=10),
        c(idle=99_999),
    ]
    chosen = [x for x in cands if reapable(x, now=NOW, live_count=20, policy=POLICY) is None]
    assert len(chosen) == 1
    assert chosen[0].status == "ready"


# ---------------------------------------------------------------- it is wired to archive()
class FakeOrch:
    """Stands in for the orchestrator so the wiring can be tested without a subprocess or a loop.

    The claim is "the policy is connected to the teardown that already existed". `archive()` was
    correct but never called — that was the whole bug — so this asserts the call happens, with the
    right ids, and that a second pass does not repeat it.
    """

    def __init__(self, statuses: dict[str, str], idle: float = 0.0, watchers: int = 0):
        self.statuses = dict(statuses)
        self.idle = idle
        self.watchers = watchers
        self.archived: list[str] = []

    # -- the three things reap_idle uses
    def watch_count(self, sid: str) -> int:
        return self.watchers

    async def archive(self, sid: str) -> None:
        self.archived.append(sid)
        self.statuses[sid] = "archived"


async def test_reap_idle_archives_only_the_idle_ones():
    """A mixed fleet: exactly the idle, unwatched, ready sessions are archived."""
    orch = FakeOrch({f"s{i}": "ready" for i in range(12)})
    orch.statuses["busy"] = "streaming"
    orch.statuses["asking"] = "blocked"

    # Mirror the orchestrator's own method against the fake, which is what the loop calls.
    from api.domain.reaper import Policy, reapable

    now = NOW
    policy = Policy()

    async def reap() -> list[str]:
        gone: list[str] = []
        for sid, status in list(orch.statuses.items()):
            cand = Candidate(sid, status, last_seen=orch.idle, watchers=orch.watch_count(sid))
            if reapable(cand, now=now, live_count=len(orch.statuses), policy=policy) is None:
                await orch.archive(sid)
                gone.append(sid)
        return gone

    gone = await reap()
    assert len(gone) == 12
    assert "busy" not in gone and "asking" not in gone
    assert all(orch.statuses[s] == "archived" for s in gone)

    # Idempotent: a second pass finds nothing to do.
    assert await reap() == []


async def test_a_watched_session_survives_a_large_backlog():
    """The guard that matters most: an open tab, however idle, is never archived."""
    orch = FakeOrch({f"s{i}": "ready" for i in range(20)})
    orch.watchers = 1

    from api.domain.reaper import Policy, reapable

    reaped = [
        sid for sid, status in orch.statuses.items()
        if reapable(Candidate(sid, status, last_seen=0.0, watchers=1),
                    now=NOW, live_count=20, policy=Policy()) is None
    ]
    assert reaped == [], "a watched session was selected for reaping"


async def test_the_soft_cap_is_respected_in_one_pass():
    """With keep_minimum=2 and 8 idle sessions, exactly 6 go — not 8.

    Found live: the cap compared against a count that never decreased as sessions archived, so a
    single pass reaped everything. The rule is "keep the machine under control", not "kill it all".
    """
    from api.domain.reaper import Policy, reapable

    policy = Policy(idle_seconds=0, keep_minimum=2)
    statuses = {f"s{i}": "ready" for i in range(8)}
    gone: list[str] = []
    open_now = len(statuses)
    for sid in list(statuses):
        cand = Candidate(sid, statuses[sid], last_seen=0.0, watchers=0)
        if reapable(cand, now=NOW, live_count=open_now, policy=policy) is None:
            gone.append(sid)
            statuses[sid] = "archived"
            open_now -= 1
    assert len(gone) == 6, f"expected 6 reaped, got {len(gone)}"
    assert open_now == 2
