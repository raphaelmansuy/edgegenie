# 08 · Six lenses

[Index](README.md) · prev: [07 Model selection](07-model-selection.md) · next: [09 Implementation plan](09-implementation-plan.md)

The same change, looked at by six people who will each judge it by a different failure. Each lens ends
with the one thing it would refuse to ship without — a refusal, not a preference, because a lens that
only has preferences is a review comment.

---

## 1 · Product Owner

**The question I ask:** *what does the user stop doing because of this?*

They stop *navigating to read*. Today, reading an answer about a file costs two navigations
([04 §before and after](04-assistant-dock.md#the-interaction-before-and-after)); after, it costs zero.
That is the product claim, and it is the only one I will defend in a roadmap review.

**What I will pay for.** The dock, and the model control being visible. Not the files list — that is
parity, and parity does not win a user. I pay for the list only because it is cheap once
`WorkspaceTree` already has a menu and a search.

**What I will not pay for.** A rearrangable dock, a dock on the left, two docks, a dock that also
shows the git diff. Every one of those is a settings screen people will not use.

**How I judge it.** A five-minute test with someone who has never seen the app: open a notebook, ask
for a change, approve it, see the file update — without being told where to click. If they look for a
"Chat" tab, the dock has failed to announce itself.

**My metric.** Time from "I see the problem in the code" to "I have asked about it". Today that is
open-tab → find-tab → type. After, it is click-cell → ask → type. If the number of *panes opened* per
ask does not go from 1.4 to 0, the work failed.

**Refuse to ship without:** the dock naming its subject (`in context: <doc>`). A docked chat that
does not say what it is about is a chat box with a smaller window, and I would rather keep the tab.

---

## 2 · Full-Stack Developer

**The question I ask:** *where does this state live, and who owns it?*

Three states are at risk of being owned twice: the focus, the stream, and the dock's open/closed
state. If any is duplicated, the bug appears later as "the two views disagree", which is the most
expensive class of bug to find.

**What I insist on.**

| State | One owner | Everyone else |
|---|---|---|
| focus | `domain/focus.ts` + one `useState` in `App` | reads a prop |
| the session stream | `useSessionStream` (one `EventSource`) | renders `session` |
| dock visibility, width | `useLayout` → `layout.ts` | reads `layout` |
| model pin | the server (`/model` + `model-facts`) | reads |

**Where the code goes.** A decision goes in `domain/` and is tested with vitest and no DOM. An I/O
goes in `adapters/`. A composition goes in `components/` or `services/`. That is why `dockState()`,
`searchRoot()` and `bindingFor()` are pure functions with tests, and why `AssistantDock.tsx` contains
no decision at all — it renders what the functions say.

**DRY, concretely, in this change:**

| Duplicated today | Becomes |
|---|---|
| Two places that decide "what will this message attach" (`Composer`'s `auto` chip, `App`'s `message`) | one `bindingFor(focus)` |
| Two places that know the model trigger's DOM (the palette command queries `.topbar .model-trigger`) | one `ModelChip` with a ref, and the palette calls the ref |
| Two composers | one `Composer` with a `variant` |
| Two overlay mechanisms (rail drawer, inspector drawer) | one `drawer` slot with three occupants |

**SOLID, concretely:**

| Principle | Where it shows |
|---|---|
| **S** | `focus.ts` decides what is in context; `dock.ts` decides which state to render; `AssistantDock` renders. No file does two. |
| **O** | A fourth zone is an entry in the zone table; a fifth dock state would be a state in `dockState`, not a new branch in the component. |
| **L** | Every zone satisfies the same `ResizableZone` contract (`min`, `max`, `default`) already used by the separator. |
| **I** | `AssistantDock` receives `{focus, session, actions}` — not the whole `App` state. |
| **D** | Components depend on `Focus` and `dockState`, never on `window.innerWidth` or `localStorage`. |

**What will make me reject a PR:** a `getBoundingClientRect()` in a render path; a second
`EventSource`; a `localStorage` call outside its hook; a handler prop that is optional when the
feature requires it (that is exactly how the two inert controls happened); a hard-coded px width
outside `layout.ts`.

**Refuse to ship without:** `dockState()` unit-tested for every combination. The four-state promise is
either a tested function or a hope.

---

## 3 · Database Expert

**The question I ask:** *what happens at the 100th thousandth event, and what happens when the
connection dies mid-turn?*

**What I insist on.**

1. **`seq` is the contract.** Replay is `WHERE session_id = $1 AND seq > $2 ORDER BY seq`; the index
   `(session_id, seq)` exists because that query runs on every reconnect.
2. **Publish after commit.** An event in the queue that is not in the table is a conversation that
   loses its middle on reload. The order is: `INSERT … RETURNING seq` → commit → queue.
3. **Batching, with a stated policy.** 250 ms per turn for deltas, because 300 rows per turn naively
   is 300 round trips.
4. **No unbounded growth.** `app_event` is pruned by age (30 days default); `app_session` and
   `app_turn` are the user's history and are kept until the user deletes the session.
5. **Cascades, not orphans.** `ON DELETE CASCADE` from session → turn → event, so "delete my session"
   actually deletes it. The GDPR-ish answer must be one statement.
6. **Idempotent migrations, one runner.** Migration `002` lives beside `001` and uses the same
   `SchemaAhead` gate. A second runner is how two specs diverge.

**The number I will not let anyone hand-wave.** Write volume. 20 turns/hour × 300 deltas × 20 users is
120 000 rows an hour at the top end, if nobody coalesces. With 250 ms batching a 30-second turn is
120 rows, not 300. That is the difference between a toy and a table, and it is in [05](05-data-model-lakebase.md#write-volume-and-why-it-is-acceptable).

**What I will reject:** storing the model pin as a text column on `app_turn` (it cannot answer "which
endpoint"); a `jsonb` payload for the *turn*, because the session list would have to parse it; and any
query without an index that runs more than once per page load.

**Refuse to ship without:** the "DSN is broken" path tested. An app that cannot boot without Postgres
is an app that will one day fail to boot.

---

## 4 · UX and UI Designer

**The question I ask:** *what is the one thing on screen, and what is the second?*

The document is first. The conversation is second. Everything else — rail, tabs, bar, chips — is
support. The current shell has no second: opening a document deletes the conversation, so the eye has
one place to go and the app's most valuable surface is a place, not a pane.

**What I insist on.**

- **A hierarchy, not a balance.** The dock is quieter than the document: `--surface-2` header, no
  shadow, no card, no border on the inner side. It must not compete.
- **One accent.** The dock uses `--blue-600` for the current row and the primary action, exactly like
  the transcript. A new panel with a new tint is how an app starts looking assembled.
- **The chip is the contract.** `in context: display_unity_catalog_tables` is the single most
  important string in the new surface. It is small, grey, and always there.
- **Density.** 40 px header (the `doc-bar` height), 13 px body, 11.5 px tool rows. The dock is
  narrower, so it must not also be looser.
- **Motion that explains.** The drawer slides in 160 ms from the edge it lives on, and only that edge.
- **Nothing floats over code that is not asked for.** No toast in the centre, no auto-opened overlay.
- **Dark and light are the same design.** Tokens only; no hard-coded colour, no `rgba` except where it
  already exists, and reduced motion honoured.

**What I will reject:** a dock with its own scrollbar inside a page scrollbar; an empty state with
marketing copy ("Unlock smarter answers…") instead of three things to do; the model's name truncated
to `gem…` at 320 px (MC-7 is a design requirement, not a technical one).

**Refuse to ship without:** screenshots of all four dock states, both themes, at 1600 and 760. If any
of those eight is ugly or broken, the surface is not designed yet.

---

## 5 · Front-End Developer

**The question I ask:** *what re-renders when a token arrives, and how many times?*

The answer must be: the answer's text node, batched at 40 ms
([`useSessionStream.ts:14`](../../apps/coding-agent/web/src/hooks/useSessionStream.ts)). The dock adds
a second *view* of the same state, which is the risk: if both render a markdown tree per delta, the
tab will stutter on a long answer.

**What I insist on.**

| Risk | Mitigation | Test |
|---|---|---|
| Two views re-render per delta | both read one reducer; the batching is unchanged | render-count test on `AssistantDock` |
| The dock unmounts on `⌘J` and loses scroll | keep the scroll offset in a ref keyed by session, restore on mount | e2e: hide, show, the position is kept |
| Markdown re-parsed at 320 px width | memoise per `(text, width)` | profiler check in the e2e, recorded |
| Focus fights between two composers | one `inputRef` per placement; `⌘L` focuses the **visible** one | unit test on the focus resolver |
| The popover clipped by the dock's `overflow` | it is portalled to `document.body` (already) and placed above the composer | e2e at 760 px |
| A drawer that traps focus incompletely | reuse the existing drawer pattern, which already returns focus | a11y audit |
| `aria-live` per token | announce per completed turn | unit test on the announce policy |

**The type-level fix for the inert controls.** `onAskCell` becomes a required prop on the notebook
branch of a discriminated union, so forgetting it is a compile error rather than a silent `undefined`.
That is deliberately *not* a runtime check: a check that runs in production is a check that already
shipped.

**Refuse to ship without:** the dead-control e2e. It is the only mechanism that survives a
reorganisation of the components.

---

## 6 · Databricks Platform Expert

**The question I ask:** *what does this look like behind the Databricks proxy, with a user's scoped
token, on a workspace we do not control?*

**What I insist on.**

1. **Every workspace read stays on the user's token.** The dock sends an attachment; the server
   resolves it with `x-forwarded-access-token`, exactly as `/api/workspace/object` does today
   ([`api.py:421-425`](../../apps/coding-agent/api/routers/api.py)). The dock must never cause a call
   with the app's own identity, which would silently show a user data they cannot otherwise see.
2. **Scopes are a capability ceiling, not a grant.** The new UI must not imply that opening a file in
   the dock grants access. If a user lacks the scope, `ScopeMissing` says so
   ([`http.py:23-60`](../../apps/coding-agent/api/adapters/databricks/http.py)) and the pane shows it
   ([`PaneError`](../../apps/coding-agent/web/src/components/PaneError.tsx)).
3. **A restart is normal.** A Databricks App restarts on redeploy and scales to zero. That is why
   [PS-1](02-requirements.md#persistence-ps) is not optional, and why the client's replay cursor must
   work against a durable log.
4. **Lakebase is a workspace resource.** The DSN comes from the app's environment via a secret scope,
   never from the repo; the migration runs at boot from the app's own identity.
5. **The model catalogue is Databricks'.** Discovery is the source of truth; the picker's groups come
   from it. Nothing in this spec hard-codes a model name.
6. **No new scope is required.** The dock reads the same workspace and catalog endpoints the app
   already scopes (`files`, `sql`, `catalog.*:read`, `workspace.workspace`). If a future requirement
   needs one, `deploy.sh`'s `REQUIRED_SCOPES` is the single list to change, and the failure message
   already tells a user to sign in again.

**What I will reject:** any call to the workspace with the app's service principal on the dock's path;
storing a forwarded token anywhere; a cache keyed by user that outlives the request.

**Refuse to ship without:** the dock tested with a deliberately under-scoped token, showing the
actionable message rather than an empty pane.

---

## Where the lenses disagree

Recorded because a design with no disagreement is a design nobody examined.

| Disagreement | PO wants | Expert wants | Resolution |
|---|---|---|---|
| The approval sheet vs the inline approval | one pattern everywhere (fewer decisions) | inline, because a modal covers the code it is about | **inline in the dock**, sheet in the centre. Two renderings of one endpoint, documented in [04](04-assistant-dock.md) and accepted as a deliberate inconsistency. |
| Persisting the context text | store less, ship sooner | store it, or the audit cannot explain an answer | **store it**, because an audit trail that cannot explain a turn is not an audit trail. |
| The files list | parity, low value | cheap once the menu exists | **build it**, but last, and only the four columns. |

---

## The one thing every lens agrees on

> **The conversation must not disappear when the user looks at the thing they are talking about.**

That is the whole spec in one sentence, and every lens reached it from a different direction.
