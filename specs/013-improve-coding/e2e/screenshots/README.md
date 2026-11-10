# Screenshots

Produced by `node scripts/lakebase-e2e.mjs http://127.0.0.1:8062` from the app running on this
machine, against the recorded payloads in
[`web/scripts/fixtures/lakebase.json`](../../../apps/coding-agent/web/scripts/fixtures/lakebase.json).
Each scene asserts its own pass criteria before the picture is taken, so a scene cannot save a pretty
image of the wrong state.

Each file below is **inspected**, with what it showed and what inspection changed. That column is the
point: four defects in this spec were found by looking at these, not by reading code — and one of them
(S6) had passed every assertion while showing the wrong scenario entirely.

| File | Scene | What the picture shows | What inspection changed |
|---|---|---|---|
| `s1-shell-data-1480.png` | [S1](../11-e2e-plan.md#s1--the-shell-with-the-new-data-rail-tab) | four rail tabs, `Data` selected, `pg_tickets` ready / `pg_orders` starting, `tickets-app` running / `orders-api` stopped | the ⌘4 failure was a missing `railData` entry in the hotkey map — found by the scene, before the picture |
| `s2-project-1480.png` | [S2](../11-e2e-plan.md#s2--a-lakebase-project-page) | six blocks; the compute row reads `0.5 – 4 CU max − min = 3.5 ✓ (≤ 16)`; `production` tagged default; three tables | **the dock offered "Explain this notebook" over a Lakebase project.** Two looks: the copy was plausible and wrong about its subject. `suggestionsFor` now returns project questions |
| `s3-app-1480.png` | [S3](../11-e2e-plan.md#s3--a-databricks-app-page-running) | `running`, `Answered 200 in 412 ms`, the `/logz` link, `CAN_CONNECT_AND_CREATE` on the postgres resource | same defect on the app page; the dock now offers "Is tickets-app working?", "What does it read?", "Fix it" |
| `s4-app-cold-1480.png` | [S4](../11-e2e-plan.md#s4--cold-start-the-app-is-waking) | "Cold start: no answer in 15 s, which is normal after the app was idle"; no red; the rest of the page intact | nothing — the state was already right, which is why it is kept as the record that `starting` is not `down` |
| `s5-refused-1480.png` | [S5](../11-e2e-plan.md#s5--a-refusal-no-can-manage) | four blocks, each with the platform's sentence; composer accepts a keystroke | **"Try again" was offered for a `PERMISSION_DENIED`** — a dead end dressed as an action. `Block` now withholds retry on a permanent refusal |
| `s6-scaffold-running-1480.png` | [S6](../11-e2e-plan.md#s6--a-scaffold-mid-flight) | the mission screen: "7 of 7 complete", `pg_tickets` on `agent-4ff4405d`, `agent-4ff-tickets` answering HTTP 200 | **two looks.** First: the card built a *taxi notebook* — the demo's prompt picker had no Lakebase case, so the card fell through to `notebook`. Fixed in `fake/agent.py` and in the card's own `scenario` |
| `s7-mid-900.png` | [S7](../11-e2e-plan.md#s7--narrow-900-px) | the rail as a column, the dock collapsed to a `CHAT` edge tab, the centre above its minimum | the scene's first assertion was wrong, not the app: 900 px is `mid` (narrow is ≤ 820). The wireframe claimed "below 1180 px the rail is a drawer", which is not what `modeFor` says; the scene now asserts the rule the code implements |
| `s8-palette-1480.png` | [S8](../11-e2e-plan.md#s8--the-palette-finds-the-new-objects) | `⌘K` finds the `Data` panel by name | nothing |

## What inspection found, in order of seriousness

1. **S6 was showing the wrong scenario.** Every assertion passed because they accepted any
   infrastructure word. This is the exact failure mode [012] recorded: a scene proves a mechanism, and
   a loose assertion proves a looser one. The assertion now names the objects (`pg_tickets`,
   `agent-4ff4405d`, `agent-4ff-tickets`), the plan total, and the proof (`HTTP 200`).
2. **`suggestionsFor` was kind-blind.** A project and an app fell through to the notebook branch. Two
   screenshots, one root cause, and a user-facing consequence: the first three buttons a user sees over
   a database were about a notebook that does not exist.
3. **A refusal offered a retry.** `Block` renders "Try again" whenever `onRetry` is passed. A
   `PERMISSION_DENIED` does not change between two clicks, so the button is a lie about what can be
   granted. It is now withheld for a permanent refusal and kept for a transient one.
4. **The wireframe was wrong about 900 px.** `S7` asserted a drawer at 900 px; `modeFor` puts narrow at
   ≤ 820. The scene was corrected to the code's rule rather than the code to the drawing — and the
   wireframe's caption in [04](../04-wireframes.md) says "below 1180", which is a third number. The
   frames are illustrative; `layout.ts` is the authority.

## How to reproduce

```bash
cd apps/coding-agent
APP_AGENT_MODE=fake APP_DEMO_SCENARIO=lakebase APP_DEV_USER=you@example.com \
  APP_DEFAULT_MODEL=fake/model-a APP_ALLOWED_MODELS='["fake/model-a"]' \
  .venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8062

cd web && npm run build && node scripts/lakebase-e2e.mjs http://127.0.0.1:8062
```

`npm run build` is not optional: the server serves `web/dist`, so a scene run against a stale bundle
photographs the previous build. That cost one full run of eight scenes in this spec.

## The rule a picture has to pass

From [11](../11-e2e-plan.md#the-screenshots-and-the-rule-for-accepting-one): it shows the state it
claims, nothing is clipped, the state word is present, it is legible at 100 %, and it looks like the
rest of the app. Every file above was checked against all five.
