# E2E screenshots — what was proved, and what each picture shows

Five scenes, run against the app with the reference agent (`APP_AGENT_MODE=fake`) on
`127.0.0.1:8071`. **Every picture here was opened and looked at**, and each one is named with the
assertion that ran before it.

The rule this folder follows comes from spec 014: *a screenshot whose picture contradicts its assertion
is a failure even when the assertion passed.* That rule earned its place again here — S1's first picture
showed a contradiction the assertion could not see, and it is now both fixed and asserted (§"What the
pictures found").

```bash
# reproduce
cd apps/coding-agent
APP_AGENT_MODE=fake APP_TOOL_MODE=none .venv/bin/python -m uvicorn api.main:app --port 8071 &
cd web && npx vite build            # the server serves web/dist, so a build is required
APP_URL=http://127.0.0.1:8071 node scripts/assessment-e2e.mjs
```

---

## The nine scenes

| File | What it shows | Asserted before the picture |
|---|---|---|
| `s1-tool-card-page.png` | a mission whose tool cards rendered, after asking *"List the tables in samples.nyctaxi"* | a turn ran; 7 tool cards rendered; no page errors |
| `s2-shell.png` | the home screen after a fence probe on `/Shared/not-mine/x.py` | `/api/me` answers; the fence route returns `ask` with `reason: "no session is open, so there is no working folder to save into"` |
| `s3-turn-completed.png` | a finished notebook turn: **Achieved**, `3 of 3 verified`, `3 of 3 complete` | the turn is not reported blocked; a blocked turn that also says "all verified" must explain what is missing |
| `s4-narrow-820.png` | the same shell at 820 px | no horizontal overflow (0 px); the centre keeps its 480 px minimum |
| `s5-dark-1440.png` | the shell in dark mode | no page errors |
| `s6-read-only-session.png` | a **read-only** conversation, with the mode badge in the top bar | the session reports `writeMode: read-only`; the server publishes three modes; only `read-only` cannot mutate; the chip is on screen; **no** budget meter without a ceiling |
| `s7-unlimited-budget.png` | a session with no ceiling | verdict `unlimited`, `limit: 0`, an empty sentence, and **no meter drawn** |
| `s8-compaction-none.png` | `POST /compact` on a short conversation | `changed: false` with a reason, not a silent success |
| `s9-narrow-phase2.png` | 820 px with a read-only session | no horizontal overflow; the badge still fits |

---

## What the pictures found

### 1 · A blocked turn that also said "all verified" — fixed, and now asserted

The first run of S1 photographed this, and it is a genuine UI defect:

```
⚠ Blocked · requirements without verified evidence     ← the headline
Evidence                              3 of 3 verified   ← the panel, immediately below
```

Both statements are true, of **different things**: three requirements were proven, and a fourth was not.
A reader has no way to tell that apart, and the two halves contradict each other on the same screen.

**The fix.** `missionView` now exposes `missing` — the list the header already used to decide "blocked"
(`web/src/domain/mission.ts`). The evidence panel renders it beside the verified rows
(`mission-evidence-gap`), quoting the agent's own reason. So the panel says *"Not proven: list the
tables; prove the count"* under the rows it did verify.

**The assertion, so it cannot come back.** S3 now fails if a page shows "requirements without verified
evidence" **and** "N of N verified" without `.mission-evidence-gap` between them. That is the scene
catching its own first picture.

### 2 · S3 confirms `[R-31]` end to end

The same scene is the proof that `[F-17]` is gone. The notebook scenario answers in prose and carries no
EVIDENCE table; before the fix that turn ended **blocked** after two audit passes. The picture now reads
**Achieved**, with `3 of 3 verified` and `3 of 3 complete` — the derived rows from `evidence_map` filled
the gap the agent forgot to tabulate.

### 3 · The write-mode chip was invisible — fixed, and now asserted

`[S-6]` asserted that the inspector showed a write-mode chip, and the first run **photographed a screen
where the chip was not there**: the chip lived in the inspector, and the inspector is **closed by
default**. So the one mode where a plausible request gets refused was the one mode that never said so.

The fix moved the chip to the **top bar**, which is always on screen, and removed the duplicate from the
inspector — one chip, one place. The scene then passed, and the screenshot above shows "Read only" beside
the model chip at both 1440 px and 820 px.

That is the second time in this assessment that a picture caught what an assertion could not, and it is
the argument for the rule at the top of this file.

### 4 · What the pictures did *not* find

Worth stating, because a review that only lists defects is not a review:

* **820 px** is clean: no horizontal overflow, the composer fits, the model chip is reachable.
* **Dark mode** is consistent: no unthemed panel, no invisible border.
* **The fence sentence is the tool server's own**, not a paraphrase: *"no session is open, so there is no
  working folder to save into"* is what `/api/workspace/fence` returns, and it names the dimension.
* **No page errors** in any scene, which is the cheapest regression signal the harness has.

---

## Why there is no scene for the other four requirements

`[R-4]`, `[R-8]`, `[R-26]`, `[R-27]`, `[R-29]`, `[R-30]` are unit-only **on purpose**
([15 §3.1](../15-e2e-plan.md) says so for each). An 8×5 terminal matrix, a reachability walk over
`(status, online)`, and a reason string are things a test proves exactly and a screenshot cannot: a
picture of "a cancelled turn cannot become completed" would be a picture of nothing.

The scenes exist where a **person reads the result** — a page count, a refusal sentence, a blocked
header — because that is the only place a picture adds evidence to a passing assertion.
