"""Phase 2: write mode, resume, compaction, budget, instructions. `[R-9]` `[R-10]` `[R-11]` `[R-17]` `[R-24]`.

Each module was built because a requirement named it, and each is tested from the **failure it prevents**
rather than from its implementation. The negatives carry most of the weight: the cheap version of every one
of these features is a permissive default, and each test below fails that version.
"""

from __future__ import annotations

import pytest

from api.domain.budget import Decision, Usage, decide, sentence
from api.domain.budget import Verdict as BudgetVerdict
from api.domain.compaction import Turn as CTurn
from api.domain.compaction import cap, plan as compact_plan
from api.domain.instructions import Missing, Source, clip, merge
from api.domain.resume import Disposition, Snapshot, apply as apply_resume, disposition
from api.domain.write_mode import WriteMode, parse, permits

# ============================================================== [R-9] write mode
GRID = [
    (WriteMode.READ_ONLY, True, "refuse"),
    (WriteMode.READ_ONLY, False, "refuse"),
    (WriteMode.FENCED, True, "allow"),
    (WriteMode.FENCED, False, "ask"),
    (WriteMode.ASK, True, "ask"),
    (WriteMode.ASK, False, "ask"),
]


@pytest.mark.parametrize("mode,inside,outcome", GRID)
def test_the_write_mode_grid(mode, inside, outcome):
    """The 3 x 2 product, walked. `read-only` refuses BOTH placements — a read-only session must not
    even distinguish inside from outside, because the reason is the mode, not the target."""
    p = permits(mode, inside=inside, target="main.s.t")
    assert p.outcome == outcome
    if outcome != "allow":
        assert p.reason, "a refusal or a prompt with no sentence is unusable"


def test_read_only_says_it_is_the_mode_that_refused():
    p = permits(WriteMode.READ_ONLY, inside=True, target="main.s.t")
    assert "read-only" in p.reason
    assert "main.s.t" in p.reason


def test_fenced_names_the_fence_when_the_target_is_outside():
    p = permits(WriteMode.FENCED, inside=False, target="/Shared/x")
    assert "outside" in p.reason and "fence" in p.reason


@pytest.mark.parametrize("text,expected", [
    ("read-only", WriteMode.READ_ONLY), ("read_only", WriteMode.READ_ONLY),
    ("READONLY", WriteMode.READ_ONLY), ("ro", WriteMode.READ_ONLY),
    ("fenced", WriteMode.FENCED), ("", WriteMode.FENCED), (None, WriteMode.FENCED),
    ("ask", WriteMode.ASK), ("approve", WriteMode.ASK),
])
def test_parsing_a_mode(text, expected):
    assert parse(text) is expected


@pytest.mark.parametrize("junk", ["nonsense", "READ WRITE", "admin", "true", "1"])
def test_an_unknown_mode_falls_back_to_the_DEFAULT_not_to_a_wider_one(junk):
    """A typo must never grant writes. The default is `fenced`, which is the narrowest mode that still
    lets a user work — and never `read-only`'s opposite or an unrestricted pass-through."""
    assert parse(junk) is WriteMode.FENCED


def test_every_mode_has_a_label_and_a_sentence():
    for m in WriteMode:
        assert m.label and m.sentence
        assert m.sentence.endswith(".")


def test_only_read_only_refuses_to_mutate():
    assert not WriteMode.READ_ONLY.mutates
    assert WriteMode.FENCED.mutates and WriteMode.ASK.mutates


# ============================================================== [R-10] restart disposition
@pytest.mark.parametrize("status,turns,expected", [
    # A turn was in flight: the only case that needs a human.
    ("ready", ("running",), Disposition.WAS_BUSY),
    ("streaming", ("auditing",), Disposition.WAS_BUSY),
    ("ready", ("queued",), Disposition.WAS_BUSY),
    ("ready", ("completed", "completed"), Disposition.WAS_IDLE),
    ("ready", (), Disposition.WAS_IDLE),
    ("blocked", ("completed",), Disposition.WAS_IDLE),
    ("archived", ("running",), Disposition.WAS_ARCHIVED),
    ("failed", (), Disposition.WAS_FAILED),
])
def test_the_restart_matrix(status, turns, expected):
    """Eight rows, including the two that used to be wrong: an IDLE conversation is `ready`, and an
    archived one is untouched — neither asks for a Restore."""
    assert disposition(Snapshot(status=status, turn_statuses=turns)) is expected


def test_only_a_busy_session_requires_a_resume():
    for d in Disposition:
        assert d.requires_resume is (d is Disposition.WAS_BUSY)


def test_an_idle_session_restores_ready_and_not_blocked():
    """`[F-9]`: every non-archived session used to become `blocked + requiresResume`, so an app redeploy
    turned every idle conversation into a "needs attention" banner."""
    out = apply_resume(Snapshot(status="ready", turn_statuses=("completed",)))
    assert out["status"] == "ready"
    assert out["requires_resume"] is False
    assert out["resume_reason"] == ""


def test_a_busy_session_records_why():
    out = apply_resume(Snapshot(status="streaming", turn_statuses=("running",)))
    assert out["status"] == "blocked" and out["requires_resume"] is True
    assert out["resume_reason"] == "mid_turn"
    assert "restarted" in out["detail"]


def test_archived_stays_archived_whatever_its_turns_say():
    out = apply_resume(Snapshot(status="archived", turn_statuses=("running",)))
    assert out["status"] == "archived"


# ============================================================== [R-11] compaction
def _turns(n: int, tokens: int = 1000) -> list[CTurn]:
    return [CTurn(f"t{i}", i, tokens) for i in range(1, n + 1)]


def test_nothing_is_shed_when_the_conversation_fits():
    assert compact_plan(_turns(5), budget=100_000) is None


def test_the_first_turn_and_the_live_work_survive():
    """The keep-policy: turn 1 holds the objective, the last four are live work, the middle is a summary."""
    p = compact_plan(_turns(12), budget=8000, reserved=1000)
    assert p is not None
    assert p.keep[0] == "t1", "the objective was summarised away"
    assert p.keep[-4:] == ("t9", "t10", "t11", "t12"), "the live work was shed"
    assert p.summarise == ("t2", "t3", "t4", "t5", "t6", "t7", "t8")


def test_a_summary_actually_reduces_the_total():
    p = compact_plan(_turns(12), budget=8000, reserved=1000)
    assert p.after < p.before, "compaction that does not reduce anything is theatre"


def test_too_little_to_summarise_is_None_rather_than_a_partial_plan():
    """Summarising two turns costs more than it saves, so the answer is "no plan", not a token gesture."""
    assert compact_plan(_turns(5), budget=1000) is None


def test_an_empty_conversation_needs_no_compaction():
    assert compact_plan([], budget=1) is None


def test_the_event_payload_records_what_replaced_what():
    """`[F-10]`: `session.compacted` was declared and emitted by nobody. A compaction nobody can audit is
    indistinguishable from lost history, so the payload must carry both lists and both counts."""
    p = compact_plan(_turns(12), budget=8000, reserved=1000)
    ev = p.to_event()
    assert set(ev) == {"kept", "summarised", "reason", "tokensBefore", "tokensAfter"}
    assert ev["tokensBefore"] > ev["tokensAfter"]
    assert "budget" in ev["reason"]


def test_the_turn_limit_is_a_setting_not_a_constant():
    """`[F-10]`: `settings.max_turns_per_session` had no reader at all."""
    assert cap(_turns(12), 200) == 188
    assert cap(_turns(200), 200) == 0
    assert cap([], 0) == 0


# ============================================================== [R-24] budget
def test_no_limit_means_unlimited_and_is_not_a_refusal():
    d = decide(Usage(input=10**9), limit=0)
    assert d.verdict is BudgetVerdict.UNLIMITED and d.allowed
    assert sentence(d) == "", "an unlimited session needs no line about a ceiling"


def test_a_turn_that_would_cross_the_ceiling_is_blocked_before_it_spends():
    d = decide(Usage(input=900, output=90), limit=1000, reserve=50)
    assert d.verdict is BudgetVerdict.BLOCKED
    assert not d.allowed
    assert "990" in d.message and "1,000" in d.message


def test_a_turn_that_fits_is_allowed():
    d = decide(Usage(input=100, output=50), limit=1000, reserve=50)
    assert d.verdict is BudgetVerdict.ALLOW and d.allowed


def test_cached_tokens_are_reported_but_not_double_counted():
    """`cached` is a subset of input. Adding it would make a cached conversation look MORE expensive than
    an uncached one, which is the opposite of what caching does."""
    u = Usage(input=100, output=10, cached=80)
    assert u.total == 110


def test_the_fraction_is_clamped_for_a_progress_bar():
    assert decide(Usage(input=50), limit=100).fraction == 0.5
    assert decide(Usage(input=500), limit=100).fraction == 1.0
    assert decide(Usage(input=50), limit=0).fraction == 0.0


def test_the_sentence_states_both_numbers():
    s = sentence(decide(Usage(input=250), limit=1000))
    assert "250" in s and "1,000" in s and "25%" in s


# ============================================================== [R-17] instructions
def test_the_scope_block_is_always_last():
    """An instruction is text a person wrote; the fence is a decision the app made. The fence wins, and
    an agent must have been told so or it will try and be refused for a reason it thinks it was allowed."""
    m = merge([Source("personal", "I prefer SQL."), Source("workspace", "Qualify tables.")],
              scope="- Working folder: /Users/me/x/")
    assert m.text.index("scope") > m.text.index("Qualify tables.")
    assert m.text.rstrip().endswith("- Working folder: /Users/me/x/")


def test_the_order_is_workspace_then_personal_then_agents_md():
    m = merge([Source("agents_md", "C"), Source("personal", "B"), Source("workspace", "A")], scope="S")
    assert [s.kind for s in m.used] == ["workspace", "personal", "agents_md"]


def test_a_long_source_is_cut_and_says_so():
    """A silent cut is the defect `[R-3]` fixed for tool results, applied to a person's own words."""
    body, cut = clip("x" * 9000)
    assert cut and "longer" in body
    assert len(body) < 9000


def test_a_source_that_could_not_be_read_is_reported_not_dropped():
    """An agent that did not see the team's rules must not answer as if it had."""
    m = merge([], scope="S", missing=[Missing("workspace", "/w/i.md", "permission denied")])
    assert m.missing and m.missing[0].reason == "permission denied"
    assert "scope" in m.text


def test_an_empty_source_is_skipped_without_leaving_a_heading():
    m = merge([Source("personal", "   ")], scope="S")
    assert "your instructions" not in m.text


def test_the_total_budget_stops_rather_than_truncating_twice():
    m = merge([Source("personal", "a" * 4000), Source("workspace", "b" * 4000)], scope="S", budget=4100)
    assert len(m.used) == 1, "the second block should not have been squeezed in"
    assert "scope" in m.text


def test_every_kind_has_a_label_a_reader_can_understand():
    for kind in ("workspace", "personal", "agents_md"):
        assert Source(kind, "x").label
