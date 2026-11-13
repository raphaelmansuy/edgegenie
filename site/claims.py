"""Every published number, derived from the repository. Nothing here formats HTML.

The site's strongest claim is that a suspicious reader can check it. That is only true if the numbers
come from the same files the documentation comes from, and if the rules that select and aggregate them
are the *same* rules — otherwise the page and `docs/06` would disagree within one edit.

So this module is a deliberate mirror of `exams/make_tables.py`:

  * the same skip predicate (`SKIP` plus any `_`-prefixed batch);
  * the same first-trial rule for the headline tables (`_t2`, `_t3` are repeats, not extra evidence),
    while the repeatability claim is the one place that reads every trial, because that is its subject;
  * the same denominator rule: a mission's total is the total of a *perfect* run on that mission, not
    the failed run's own total. A grader that returns early reports fewer checks, so comparing a failed
    run's total with a perfect run's would compare two different exams.

**A claim is not always a percentage.** Three kinds exist, and the kind is part of the model rather than
inferred at render, because `671/311` formatted as a percentage is a real defect this code produced in
its first draft:

    PERCENT   earned / achievable, from graded missions
    TOKENS    a measured count, per task, in thousands
    COUNT     a cardinality, like the number of graded missions

`site/tests/test_claims.py` asserts that this module and `make_tables.py` agree, which is the only thing
that keeps the mirror honest.

    python3 site/claims.py            # print the ledger
    python3 site/claims.py --json     # the same, as data
"""

from __future__ import annotations

import glob
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "exams" / "results"

# The batches `make_tables.py` refuses to count, by name. `_`-prefixed batches are the rejected ones:
# the Copilot adapter failure, the port collision, the pre-fix V1. Kept identical on purpose.
SKIP = {"_invalid_port_collision", "_old_v1_pre_port_fix", "accidental_dbsql_only", "smoke_v5"}

DEV = [f"M{i}" for i in range(1, 9)]
HELD = ["X1", "X2", "X3"]


class Kind(str, Enum):
    PERCENT = "percent"
    TOKENS = "tokens"
    COUNT = "count"


# ===================================================================================== the data model
@dataclass(frozen=True)
class Run:
    """One graded task, from one file. The grain: one mission in one batch."""

    batch: str
    trial: str
    mission: str
    variant: str
    model: str
    agent: str
    score: int
    total: int
    tokens: int
    tool_calls: int
    seconds: float
    via: str = "kit"


@dataclass(frozen=True)
class Claim:
    """One published number, with everything a reader needs to disbelieve it properly."""

    id: str
    statement: str
    kind: Kind
    value: int
    unit: str  # "" for a percentage, "k tokens/task", "missions"
    numerator: int
    denominator: int
    runs: int
    tasks: str
    caveat: str
    sources: list[str] = field(default_factory=list)
    extra: dict[str, int] = field(default_factory=dict)

    @property
    def fraction(self) -> str:
        """The denominator, printed beside the value. Empty for a count, which needs no fraction."""
        if self.kind is Kind.COUNT:
            return f"{self.value}"
        return f"{self.numerator}/{self.denominator}"

    @property
    def display(self) -> str:
        if self.kind is Kind.PERCENT:
            return f"{self.value}%"
        if self.kind is Kind.COUNT:
            return f"{self.value} {self.unit}"
        return f"{self.value} {self.unit}"


def trial_of(batch: str) -> str:
    """`v4_gptoss_t2` is trial 2 of the same setup, not a new one."""
    m = re.search(r"_(t\d+)$", batch)
    return m.group(1) if m else "t1"


def load(results_dir: Path = RESULTS, *, every_trial: bool = False, via: str = "kit") -> tuple[list[Run], list[str]]:
    """Accepted runs, plus the batches that were excluded and why.

    `every_trial=False` keeps the headline rule: only `t1` counts, so a repeat cannot inflate a table.
    `every_trial=True` is for the repeatability claim, whose whole subject is the repeats.

    A truncated file is skipped and *counted*, never silently dropped: a page that quietly loses 10% of
    its evidence is worse than one that admits it ([E-3](../specs/008-github-page/09-edge-cases.md)).
    """
    runs: list[Run] = []
    excluded: list[str] = []
    for path in sorted(glob.glob(str(results_dir / "*" / "*.json"))):
        if path.endswith(".events.jsonl"):
            continue
        batch = Path(path).parent.name
        if batch in SKIP or batch.startswith("_"):
            if batch not in excluded:
                excluded.append(batch)
            continue
        trial = trial_of(batch)
        if trial != "t1" and not every_trial:
            if batch not in excluded:
                excluded.append(batch)
            continue
        try:
            d = json.load(open(path, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            excluded.append(f"{batch} (unreadable: {Path(path).name})")
            continue
        if d.get("via", "kit") != via:
            continue
        if d.get("valid") is False:
            excluded.append(f"{batch} (invalid qualification: {Path(path).name})")
            continue
        runs.append(
            Run(
                batch=batch,
                via=d.get("via", "kit"),
                trial=trial,
                mission=d["mission"],
                variant=d["variant"],
                model=d["model"],
                agent=d.get("agent", "opencode"),
                score=int(d["score"]),
                total=int(d["total"]),
                tokens=int(d.get("tokens") or 0),
                tool_calls=int(d.get("tool_calls") or 0),
                seconds=float(d.get("wall_seconds") or 0),
            )
        )
    return runs, excluded


def denominators(runs: list[Run]) -> dict[str, int]:
    """Per mission, the total of a perfect run — fall back to the largest total seen."""
    perfect: dict[str, int] = {}
    biggest: dict[str, int] = {}
    for r in runs:
        biggest[r.mission] = max(biggest.get(r.mission, 0), r.total)
        if r.score == r.total:
            perfect[r.mission] = min(perfect.get(r.mission, 10**9), r.total)
    return {m: perfect.get(m, biggest[m]) for m in biggest}


def select(runs: list[Run], *, variant: str, model: str, agent: str = "opencode") -> list[Run]:
    return [r for r in runs if r.variant == variant and r.model == model and r.agent == agent]


def pct(earned: int, of: int) -> int:
    """Rounded exactly once, here. Nowhere else may a percentage be computed."""
    return round(100 * earned / of) if of else 0


def score_of(runs: list[Run], missions: list[str], den: dict[str, int]) -> tuple[int, int, int]:
    """(earned, achievable, mission count) for a set of runs, restricted to `missions`."""
    picked = [r for r in runs if r.mission in missions and r.mission in den]
    earned = sum(min(r.score, den[r.mission]) for r in picked)
    achievable = sum(den[r.mission] for r in picked)
    return earned, achievable, len({r.mission for r in picked})


# ========================================================================================= the claims
def compute(results_dir: Path = RESULTS) -> tuple[list[Claim], list[str]]:
    """The eight claims the site publishes, and the batches it excluded.

    Every number below is derived. If a source batch disappears the claim is still returned, with the
    value at 0 and `missing(claim)` naming the batch — the build fails on that rather than shipping a
    hole ([CPT-4]).
    """
    runs, excluded = load(results_dir)
    all_runs, _ = load(results_dir, every_trial=True)
    den = denominators(runs)

    def percent(id_: str, statement: str, missions: list[str], variant: str, model: str,
                tasks: str, caveat: str, batches: list[str], agent: str = "opencode",
                extra: dict[str, int] | None = None) -> Claim:
        picked = select(runs, variant=variant, model=model, agent=agent)
        earned, achievable, n_missions = score_of(picked, missions, den)
        return Claim(
            id=id_,
            statement=statement,
            kind=Kind.PERCENT,
            value=pct(earned, achievable),
            unit="",
            numerator=earned,
            denominator=achievable,
            runs=len([r for r in picked if r.mission in missions]),
            tasks=tasks,
            caveat=caveat,
            sources=[f"exams/results/{b}" for b in batches],
            extra=extra or {},
        )

    claims: list[Claim] = []

    # CL-1 · the headline: the most complete setup, on the tasks never used while tuning.
    claims.append(percent(
        "CL-1",
        "On tasks never used while tuning, the strongest measured setup answers every one",
        HELD, "V4", "gemini-3.8-flash",
        "3 held-out tasks (X1-X3), never used for tuning",
        "Three tasks only, one run each. It says the setup generalises; it does not say it is complete.",
        ["heldout_v4_gemini"],
    ))

    # CL-2 · the same setup with the weaker, gateway-reachable model.
    claims.append(percent(
        "CL-2",
        "With the model most workspaces can actually reach, the same setup still passes most of it",
        HELD, "V4", "gpt-oss-120b",
        "3 held-out tasks (X1-X3), never used for tuning",
        "One run each. X2 lost three points because the fixed job was never re-run.",
        ["heldout_v4_gptoss"],
    ))

    # CL-3 · the differentiator: same agent, same stock tools, two models.
    weak = percent("CL-3a", "weak", DEV, "V5", "gpt-oss-120b", "", "", ["v5_gptoss"])
    strong = percent("CL-3b", "strong", DEV, "V5", "gemini-3.8-flash", "", "", ["v5_gemini"])
    claims.append(Claim(
        id="CL-3",
        statement="Same agent, same stock tools, same rules: only the model changed",
        kind=Kind.PERCENT,
        value=strong.value,
        unit="",
        numerator=strong.numerator,
        denominator=strong.denominator,
        runs=strong.runs + weak.runs,
        tasks="8 development tasks (M1-M8), one run per model",
        caveat="One run each, and M2 has the widest natural spread of the eight tasks.",
        sources=["exams/results/v5_gptoss", "exams/results/v5_gemini"],
        extra={"weak": weak.value, "weak_n": weak.numerator, "weak_of": weak.denominator,
               "strong": strong.value, "strong_n": strong.numerator, "strong_of": strong.denominator,
               "gap": strong.value - weak.value},
    ))

    # CL-4 · engineering rescues a weak model. The "from" is the bare baseline, measured.
    bare = percent("CL-4a", "bare", DEV, "V0", "gpt-oss-120b", "", "", ["baseline"])
    claims.append(percent(
        "CL-4",
        "Scoped tools, a supervisor loop and written rules lifted that model from a bare shell",
        DEV, "V4", "gpt-oss-120b",
        "8 development tasks (M1-M8), one run per setup",
        "The ladder was tuned on these tasks, so this is a ceiling for the method, not an unbiased score.",
        ["v4_gptoss"],
        extra={"from": bare.value, "from_n": bare.numerator, "from_of": bare.denominator},
    ))

    # CL-5 · with a strong model, the very first setup already worked: the machinery was not the cause.
    claims.append(percent(
        "CL-5",
        "With a strong model the very first setup scored the same, so the machinery was not what did it",
        HELD, "V1", "gemini-3.8-flash",
        "3 held-out tasks (X1-X3), never used for tuning",
        "Three tasks. It shows the machinery was unnecessary there, not that it is useless.",
        ["heldout_v1_gemini"],
    ))

    # CL-6 · repeatability: the one setup run three times. Reads every trial, by design, and only the
    # batches that are repeats of *this* setup — a Copilot run of the same variant and model is a
    # different agent, and counting it silently changed this claim from 94% to 82% in the first draft.
    repeat_batches = ["v4_gptoss", "v4_gptoss_t2", "v4_gptoss_t3"]
    repeat_den = denominators(all_runs)
    per_trial: dict[str, list[Run]] = {}
    for r in all_runs:
        if r.batch in repeat_batches and r.mission in DEV:
            per_trial.setdefault(r.trial, []).append(r)
    trial_scores = []
    for trial, rs in sorted(per_trial.items()):
        earned, achievable, n = score_of(rs, DEV, repeat_den)
        if n == len(DEV):  # only a trial with all eight tasks is a complete total
            trial_scores.append(pct(earned, achievable))
    claims.append(Claim(
        id="CL-6",
        statement="Running the same setup again moves the total by a couple of points, not tens",
        kind=Kind.PERCENT,
        value=round(mean(trial_scores)) if trial_scores else 0,
        unit="",
        numerator=round(mean(trial_scores)) if trial_scores else 0,
        denominator=100,
        runs=len(trial_scores),
        tasks="8 development tasks (M1-M8), repeated complete runs of one setup",
        caveat="One setup only. Every other setup was run once, so no other spread is known.",
        sources=["exams/results/v4_gptoss", "exams/results/v4_gptoss_t2", "exams/results/v4_gptoss_t3"],
        extra={
            "spread": (max(trial_scores) - min(trial_scores)) if len(trial_scores) > 1 else 0,
            "low": min(trial_scores) if trial_scores else 0,
            "high": max(trial_scores) if trial_scores else 0,
            "trials": len(trial_scores),
        },
    ))

    # CL-7 · cost, as a shape and never a price.
    def per_task_k(rs: list[Run]) -> int:
        dev = [r for r in rs if r.mission in DEV]
        return round(sum(r.tokens for r in dev) / len(dev) / 1000) if dev else 0

    weak_k = per_task_k(select(runs, variant="V4", model="gpt-oss-120b"))
    strong_k = per_task_k(select(runs, variant="V4", model="gemini-3.8-flash"))
    claims.append(Claim(
        id="CL-7",
        statement="The stronger model reads and writes about twice the tokens for the same eight tasks",
        kind=Kind.TOKENS,
        value=strong_k,
        unit="k tokens/task",
        numerator=strong_k,
        denominator=weak_k,
        runs=len([r for r in select(runs, variant="V4", model="gemini-3.8-flash") if r.mission in DEV]),
        tasks="8 development tasks (M1-M8), thousands of tokens per task",
        caveat="Tokens, never money: no Genie Code usage history exists, so no saving can be quoted.",
        sources=["exams/results/v4_gptoss", "exams/results/v4_gemini"],
        extra={"strong_k": strong_k, "weak_k": weak_k,
               "ratio_x10": round(10 * strong_k / weak_k) if weak_k else 0},
    ))

    # CL-8 · the surface: how many graded tasks exist at all.
    missions = sorted({r.mission for r in runs})
    claims.append(Claim(
        id="CL-8",
        statement="Every graded task was seeded in a live workspace and scored against it, not judged by a model",
        kind=Kind.COUNT,
        value=len(missions),
        unit="missions",
        numerator=len(missions),
        denominator=len(missions),
        runs=len(runs),
        tasks="8 development (M1-M8) and 3 held-out (X1-X3) missions",
        caveat="The tasks are small, clean and well specified: our exams name the tables.",
        sources=["exams/missions"],
    ))

    return claims, excluded


def by_id(claims: list[Claim]) -> dict[str, Claim]:
    return {c.id: c for c in claims}


def missing(claim: Claim) -> list[str]:
    """Source paths that do not exist. The build fails on any non-empty result ([CPT-4])."""
    out = []
    for src in claim.sources:
        p = ROOT / src
        if not p.exists():
            out.append(src)
    return out


def main() -> int:
    import sys
    claims, excluded = compute()
    if "--json" in sys.argv:
        print(json.dumps(
            {"claims": [dict(c.__dict__, kind=c.kind.value) for c in claims], "excluded": excluded},
            indent=2,
        ))
        return 0
    print(f"{'id':<6}{'display':>18}  {'fraction':>10} {'runs':>5}  statement")
    for c in claims:
        print(f"{c.id:<6}{c.display:>18}  {c.fraction:>10} {c.runs:>5}  {c.statement[:72]}")
    bad = [(c.id, m) for c in claims for m in missing(c)]
    print(f"\n{len(excluded)} batch(es) excluded: {', '.join(excluded) or 'none'}")
    if bad:
        print(f"MISSING SOURCES: {bad}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
