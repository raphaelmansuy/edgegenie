"""Tests for `site/claims.py`. Standard library only, so the site needs no dev dependency.

    python3 site/tests/test_claims.py

The most important test here is `test_matches_make_tables`: it imports the repository's own table
builder and asserts that the site and the docs compute the *same* number from the same files. That is
the only mechanism that keeps the mirror honest; without it, "the docs are the source of truth" is a
claim rather than a property.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "site"))

import claims as C  # noqa: E402


CASES: list[tuple[str, object]] = []


def case(fn):
    CASES.append((fn.__name__, fn))
    return fn


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------------------------------ the tests
@case
def test_every_claim_has_a_source_that_exists():
    claims, _ = C.compute()
    for c in claims:
        assert c.sources, f"{c.id} has no source"
        absent = C.missing(c)
        assert not absent, f"{c.id} cites paths that do not exist: {absent}"


@case
def test_the_headline_numbers_match_the_repository():
    claims = C.by_id(C.compute()[0])
    assert claims["CL-3"].extra["weak"] == 39, claims["CL-3"].extra
    assert claims["CL-3"].extra["strong"] == 86, claims["CL-3"].extra
    assert claims["CL-3"].extra["gap"] == 47, claims["CL-3"].extra
    assert claims["CL-4"].value == 94 and claims["CL-4"].extra["from"] == 19, claims["CL-4"].extra
    assert claims["CL-1"].value == 100 and claims["CL-1"].denominator == 37


@case
def test_matches_make_tables():
    """The site and `docs/06` must not disagree."""
    try:
        mt = load_module("make_tables_for_test", ROOT / "exams" / "make_tables.py")
    except Exception:
        print("        (skipped: exams/make_tables.py is not importable in this checkout)")
        return
    blocks = mt.blocks()
    ours = C.by_id(C.compute()[0])

    rows = mt.load()
    oc = [d for d in rows if d.get("agent", "opencode") == "opencode"]
    ft = mt.full_totals(oc)
    for variant, model, want in (("V5", "gpt-oss-120b", 39), ("V5", "gemini-3.8-flash", 86),
                                 ("V4", "gpt-oss-120b", 94), ("V0", "gpt-oss-120b", 19)):
        picked = [d for d in oc if d["variant"] == variant and d["model"] == model and d["mission"] in mt.DEV]
        earned = sum(min(d["score"], ft[d["mission"]]) for d in picked)
        total = sum(ft[d["mission"]] for d in picked)
        got = round(100 * earned / total)
        assert got == want, f"{variant}/{model}: make_tables says {got}, expected {want}"

    assert ours["CL-3"].extra["weak"] == 39
    assert ours["CL-3"].extra["strong"] == 86
    assert ours["CL-4"].value == 94
    assert ours["CL-4"].extra["from"] == 19
    assert blocks.get("summary_dev")


@case
def test_rejected_batches_are_excluded():
    runs, excluded = C.load()
    counted = {r.batch for r in runs}
    for bad in ("_copilot_before_shim_dev", "_old_v1_pre_port_fix", "accidental_dbsql_only",
                "smoke_v5", "v4_gptoss_t2", "v4_gptoss_t3"):
        assert bad not in counted, f"{bad} should not be counted"
        assert any(bad in e for e in excluded), f"{bad} should be named in the exclusion list"


@case
def test_a_repeat_trial_is_not_extra_evidence():
    runs, _ = C.load()
    assert not [r for r in runs if r.trial != "t1"]


@case
def test_repeatability_reads_the_repeats_it_is_about():
    cl = C.by_id(C.compute()[0])["CL-6"]
    assert cl.extra["trials"] == 3, cl.extra
    assert 90 <= cl.extra["low"] <= 100, cl.extra
    assert 0 <= cl.extra["spread"] <= 5, cl.extra


@case
def test_an_empty_results_directory_reports_zero_rather_than_crashing():
    with tempfile.TemporaryDirectory() as tmp:
        claims, _ = C.compute(Path(tmp))
        assert claims
        assert all(c.numerator == 0 for c in claims)


@case
def test_a_rejected_only_directory_yields_no_accepted_runs():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "_old_batch"
        d.mkdir()
        (d / "M1__V4__gpt-oss-120b.json").write_text(json.dumps({
            "mission": "M1", "variant": "V4", "model": "gpt-oss-120b",
            "score": 10, "total": 10, "tokens": 1, "tool_calls": 1,
        }))
        runs, excluded = C.load(Path(tmp))
        assert runs == [], runs
        assert any("_old_batch" in e for e in excluded)


@case
def test_an_unreadable_result_is_counted_not_dropped():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "ok_batch"
        d.mkdir()
        (d / "M1__V4__gpt-oss-120b.json").write_text('{"mission": "M1", "variant": "V4", "model"')
        runs, excluded = C.load(Path(tmp))
        assert runs == []
        assert any("unreadable" in e for e in excluded), excluded


@case
def test_the_denominator_is_the_perfect_run_not_the_failed_one():
    failed = C.Run(batch="b", trial="t1", mission="M9", variant="V9", model="m", agent="opencode",
                   score=3, total=4, tokens=0, tool_calls=0, seconds=0)
    perfect = C.Run(batch="b", trial="t1", mission="M9", variant="V9", model="m", agent="opencode",
                    score=10, total=10, tokens=0, tool_calls=0, seconds=0)
    assert C.denominators([failed, perfect])["M9"] == 10


@case
def test_rounding_happens_once():
    assert C.pct(143, 152) == 94
    assert C.pct(130, 152) == 86
    assert C.pct(60, 152) == 39
    assert C.pct(0, 0) == 0


@case
def test_every_claim_has_a_non_empty_caveat():
    for c in C.compute()[0]:
        assert len(c.caveat) > 20, f"{c.id} has no real caveat: {c.caveat!r}"


@case
def test_a_count_is_not_rendered_as_a_percentage():
    cl = C.by_id(C.compute()[0])["CL-8"]
    assert cl.kind is C.Kind.COUNT
    assert "%" not in cl.display, cl.display


@case
def test_tokens_are_never_a_percentage():
    cl = C.by_id(C.compute()[0])["CL-7"]
    assert cl.kind is C.Kind.TOKENS
    assert "%" not in cl.display, cl.display
    assert "token" in cl.caveat.lower()


def main() -> int:
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  ok    {name}")
        except Exception:
            failed += 1
            print(f"  FAIL  {name}")
            traceback.print_exc(limit=3)
    print(f"\n{len(CASES)} tests, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
