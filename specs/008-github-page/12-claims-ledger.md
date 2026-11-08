# 12. The claims ledger

[Index](README.md) · prev: [11 Outcome](11-outcome.md)

Every number the site publishes, what produced it, and how to check it. This document is the **definition**
of each claim; the site renders the values from [`site/claims.py`](../../site/claims.py), and neither the
site nor this table is typed by hand.

> **How this table was produced:** `python3 site/claims.py --json`. The values below are that command's
> output on 8 November 2026, from commit `39eeb2f`. If you are reading a version of this file whose numbers
> disagree with the site, the site is right and this file is stale — which is the failure mode the whole
> design exists to prevent, and the reason [PG-9](03-requirements.md) makes a hand-typed percentage a build
> error.

| id | Value | Fraction | Runs | Kind | What it says |
|---|---|---|---|---|---|
| `CL-1` | **100%** | 37/37 | 3 | percent | On tasks never used while tuning, the strongest measured setup answers every one |
| `CL-2` | **86%** | 32/37 | 3 | percent | With the model most workspaces can actually reach, the same setup still passes most of it |
| `CL-3` | **86%** | 130/152 | 16 | percent | Same agent, same stock tools, same rules: only the model changed |
| `CL-4` | **94%** | 143/152 | 8 | percent | Scoped tools, a supervisor loop and written rules lifted that model from a bare shell |
| `CL-5` | **100%** | 37/37 | 3 | percent | With a strong model the very first setup scored the same, so the machinery was not what did it |
| `CL-6` | **95%** | 95/100 | 3 | percent | Running the same setup again moves the total by a couple of points, not tens |
| `CL-7` | **671 k** | 671 / 311 | 8 | tokens | The stronger model reads and writes about twice the tokens for the same eight tasks |
| `CL-8` | **11** | — | 123 | count | Every graded task was seeded in a live workspace and scored against it |

---

## How each one is derived

### `CL-1` and `CL-5`, held-out, strong model

| | |
|---|---|
| Batches | `heldout_v4_gemini`, `heldout_v1_gemini` |
| Missions | `X1`, `X2`, `X3` |
| Denominator | 37 points: the total of a perfect run across the three held-out missions |
| Caveat | Three tasks, one run each. It says the setup generalises; it does not say it is complete. |

`CL-1` and `CL-5` landing on the same number is the finding, not a copy: the most engineered setup and the
very first one both scored 37/37 on tasks neither was tuned on. With a strong model, the machinery made no
measurable difference on this set.

### `CL-2`, held-out, reachable model

| | |
|---|---|
| Batch | `heldout_v4_gptoss` |
| Missions | `X1`, `X2`, `X3` |
| Denominator | 37 |
| Caveat | One run each. X2 lost three points because the fixed job was never re-run. |

The five-point gap from `CL-1` is inside the noise measured in `CL-6`, so the honest reading is *"both
generalise"*, not *"Gemini is five points better on unseen work"*.

### `CL-3`, the differentiator

| | |
|---|---|
| Batches | `v5_gptoss`, `v5_gemini` |
| Missions | `M1`…`M8` |
| Pairs | 60/152 (39%) and 130/152 (86%) — a **47-point** gap |
| Caveat | One run each, and `M2` has the widest natural spread of the eight. |

This is the claim the whole page is built on, so it is the one with the most scrutiny. What it holds: the
same agent, the same stock Databricks CLI plus the official skills, the same rules file, two models, a gap
of 47 points — roughly eighteen times the measured noise. What it does not hold: that any particular
cheaper model is this bad, or that Gemini is this good on your tasks.

### `CL-4`, engineering rescues a weak model

| | |
|---|---|
| Batches | `baseline` (V0), `v4_gptoss` (V4) |
| Missions | `M1`…`M8` |
| Pair | 29/152 (19%) and 143/152 (94%) — a **75-point** lift |
| Caveat | The ladder was tuned on these tasks, so this is a ceiling for the method, not an unbiased score. |

The held-out check for this claim is `CL-2`: the same engineered setup on tasks it was never tuned on still
scored 32/37.

### `CL-6`, repeatability

| | |
|---|---|
| Batches | `v4_gptoss`, `v4_gptoss_t2`, `v4_gptoss_t3` |
| Trials | 3 complete runs: 94.1%, 96.7%, 94.7% → mean **95%**, spread **2.6 points** (the claim stores the rounded range, 94–97%) |
| Caveat | One setup only. Every other setup was run once, so no other spread is known. |

This is the only claim that reads repeat trials. Every other claim uses first trials only, so a repeat
cannot inflate a total — see `test_a_repeat_trial_is_not_extra_evidence`.

The practical use: **a one- or two-point gap between two setups is not a difference.** It is why `CL-2`
says "both generalise" rather than "five points better".

### `CL-7`, cost, as a shape

| | |
|---|---|
| Batches | `v4_gptoss`, `v4_gemini` |
| Measure | Thousands of tokens per task, averaged over `M1`…`M8` |
| Values | **671 k** tokens per task (Gemini) against **311 k** (gpt-oss) — about 2.2× |
| Caveat | Tokens, never money: no Genie Code usage history exists, so no saving can be quoted. |

Rendered as a `tokens` kind, not a percentage. The first draft of `claims.py` formatted it as a percentage
and the page read `671%`, which is the kind of defect that survives a review and dies in a screenshot.

### `CL-8`, the surface

| | |
|---|---|
| Source | `exams/missions/`, and the 123 accepted run files |
| Count | **11** missions: 8 development (`M1`…`M8`) and 3 held-out (`X1`…`X3`) |
| Caveat | The tasks are small, clean and well specified: our exams name the tables. |

---

## What is excluded, and why

`python3 site/claims.py` prints the exclusion list. On this commit it is eight batches:

| Batch | Why |
|---|---|
| `_copilot_before_shim_dev`, `_copilot_before_shim_held`, `_copilot_before_shim_smoke` | GitHub Copilot CLI adds a private field the Databricks gateway rejects; these runs measured the adapter, not the agent |
| `_old_v1_pre_port_fix` | A port collision in the harness, fixed afterwards |
| `accidental_dbsql_only` | A runner misconfiguration: the agent received SQL tools only |
| `smoke_v5` | A smoke test, not a graded run |
| `v4_gptoss_t2`, `v4_gptoss_t3` | Repeat trials. Counted in `CL-6`, which is their subject, and nowhere else |

The predicate is copied from `exams/make_tables.py`: anything `_`-prefixed, plus three names. If the site
used a different rule from the docs, they would disagree within one edit.

---

## The four rules that keep this honest

1. **One computation.** `site/claims.py` is the only place a percentage is calculated. It rounds once, at
   render (`pct()`). A template that formats a float produces `94.0%` beside a table's `94%`.
2. **The denominator is the perfect run, per mission.** A failed run's grader returns early, so its own
   total is smaller; comparing `143/152` with `60/63` would compare two different exams.
3. **A missing source fails the build.** `[CPT-4]`: a claim whose batch has disappeared does not vanish
   quietly, it stops the page.
4. **A hand-typed percentage fails the build.** `[PG-9]`: prose may contain `{{CL-n}}`, never `94%`. The
   checker allows a percentage only if a claim produced that value.

The first version of this system got two of those wrong — `CL-6` counted a Copilot batch as a repeat of
the same setup (82% instead of 95%), and `CL-7` was rendered as a percentage (671%). Both were found by
looking at the output rather than by a test, and both now have a test.
