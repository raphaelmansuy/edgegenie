# Screenshots

Produced by `node scripts/ux-scenes.mjs http://127.0.0.1:8062` from the app running on this machine.
Each scene asserts its own pass criteria before the picture is taken, so a scene cannot save a pretty
image of the wrong state.

Each file below is **inspected**, with what it showed and what it changed. That column is the point:
five defects in this spec were found by looking at these, not by reading code.

| File | Scene | What the picture shows | What inspection changed |
|---|---|---|---|
| `s1-shell-1480-light.png` | [S1](../10-e2e-plan.md#s1--the-healthy-shell) | rail 276 · main 822 · dock 380, no page scroll, composer writable | nothing — the geometry baseline |
| `s2-connecting-1480.png` | [S2](../10-e2e-plan.md#s2--type-during-connecting) | the words "chart the trips" **in the composer**, focus ring visible, while the topbar still says `starting` | this is the fix, photographed: before it, that sentence was discarded |
| `s4-reconnecting-1480.png` | [S4](../10-e2e-plan.md#s4--reconnecting) | yellow "reconnecting… [Retry]" with the explanation under it, composer fully available below | moved the notice out of the header (the header could not fit it) |
| `s5-closed-1480.png` | [S5](../10-e2e-plan.md#s5--closed) | pink "session closed" with **Retry** and **New conversation**, composer still writable | 4 iterations: duplicated reason, quadruplicated fact, notice overflowing a 40 px header, truncated state word |
| `s6-escape-820.png` | [S6](../10-e2e-plan.md#s6--escape-at-820-px) | at 820 px the rail drawer is closed and the dock takes the column | confirmed Escape works from the work area |
| `s7-deeplink-settings.png` | [S7](../10-e2e-plan.md#s7--hard-refresh-and-a-cell-deeplink) | `#/settings/providers` opened on a cold load | nothing — it was already correct |
| `s8-scroll-handoff.png` | [S8](../10-e2e-plan.md#s8--wheel-hand-off) | the page after a wheel at a contained scroller's bottom edge | nothing — the arithmetic and the hook agree |

## How to reproduce

```bash
cd apps/coding-agent
APP_AGENT_MODE=fake APP_DEV_USER=you@example.com \
  .venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8062

cd web
node scripts/ux-scenes.mjs http://127.0.0.1:8062
```

The scenes need a session to exist, so they create one through the app's own API. `S3` (the "before"
picture) is not regenerated: it records a state the app can no longer produce, and is described in
[10](../10-e2e-plan.md#s3--the-reported-bug-before) instead of shipped as a file that would go stale.
