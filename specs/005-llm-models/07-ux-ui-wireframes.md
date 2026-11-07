# 07 · UX, UI: wireframes, navigation, states

[Index](README.md) · prev: [06 Security](06-security-credentials.md) · next: [08 Lenses](08-lenses.md)

Two surfaces change: the **model picker** (a popover, replacing two `<select>` elements) and a new
**settings** surface for providers and keys. The inspector gains a model-facts block. The three
panes, the palette, the shortcut sheet and the theme are untouched.

> **The wireframes are generated, not drawn.** A box one character out of alignment reads as broken
> and the defect is invisible in a diff, so the diagrams below come from
> [`tools/wireframes.py`](tools/wireframes.py), which measures each box from its own content. Regenerate
> with `python3 tools/wireframes.py --write`; verify with `--check`, which is wired into
> [09 §Enforcement](09-implementation-plan.md#enforcement-not-convention).

---

## Design intent, in five lines

| Principle | What it looks like on screen |
|---|---|
| **The model is a fact, not a setting** | the chip shows the model for *this* session; a change says what happens next ("applies to your next message") |
| **Availability is stated, not implied** | every unselectable model says *why* and what to do; nothing is silently missing (FR-20) |
| **Limits and cost are visible before you spend** | context, output cap and the evidence behind the cap sit one keystroke away |
| **The fence does not move** | choosing a model never changes what the agent may write, and the inspector says so |
| **Degraded is a visible state, not an error** | when the database or a provider is down the picker still opens and names the part that is unavailable |

---

## Constraints this design inherits from the shipped shell

Read from [`web/src/styles.css`](../../apps/coding-agent/web/src/styles.css), not assumed:

| Constraint | Line | Consequence for the picker |
|---|---|---|
| `.topbar .meta` may compress; the chip is what gives way | 199-208 | the chip label truncates before the status pill does |
| at ≤ 1100 px `.topbar .meta .chip { display: none }` | 211-213 | the inspector must carry the model facts, and the picker needs a second entry point |
| a chip is `border-radius: 999px`, 12 px type | 500-503 | the trigger stays a chip; the picker cannot be a full-height sheet |
| reduced motion is honoured globally | 511-514 | the popover must not animate open when the user asked for less motion |

---

## Wireframes

<!-- BEGIN GENERATED WIREFRAMES -->

### Screen 1 · the topbar today

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ ◧ Databricks Coding Agents      model ▾ databricks-llama-4-maverick  ready   ⌘K   ▤   ◫      │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

One `<select>` per session, its options formatted by `id.split("/").pop()`: unsorted,
ungrouped, no state, and two naming conventions in one list — see
[01 E8](01-current-state.md#e8-the-picker-is-two-select-elements).

### Screen 2 · the picker, open

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ ◧ Databricks Coding Agents      model ▾ llama-4-maverick  ● ready            ⌘K   ▤   ◫      │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ┌─────────────────────────────────────────────────────────────────────────┐
                                  │  SEARCH                                      current: llama-4-maverick  │
                                  ├─────────────────────────────────────────────────────────────────────────┤
                                  │  ▾ DATABRICKS · AI GATEWAY                        5 of 5                │
                                  │  ✓ llama-4-maverick      128k ctx · 8k out · measured                   │
                                  │  ○ gpt-oss-120b          128k ctx · 24k out · measured                  │
                                  │  ○ qwen3-next-80b        128k ctx · 10k out · measured                  │
                                  │  ○ meta-llama-3-3-70b    128k ctx · 8k out · measured                   │
                                  │  ◌ claude-sonnet-4-5     not enabled · ask an admin                     │
                                  ├─────────────────────────────────────────────────────────────────────────┤
                                  │  ▾ YOUR PROVIDERS                                   2 of 3              │
                                  │  ○ gemini-3.8-flash       vertex · 1M ctx · key …7f3a                   │
                                  │  ⚠ gpt-4.1                openai · key expired 2h ago                   │
                                  │  ✕ claude-sonnet-4-5      anthropic · no key · add one                  │
                                  ├─────────────────────────────────────────────────────────────────────────┤
                                  │  ▸ NOT AVAILABLE HERE (1)                                               │
                                  ├─────────────────────────────────────────────────────────────────────────┤
                                  │  ↑↓ move  ⏎ select  ⌘⏎ keep open  esc close                             │
                                  │  source: workspace · keys: 2 · updated 12s ago                          │
                                  └─────────────────────────────────────────────────────────────────────────┘
```

The popover hangs from the chip. The glyph column carries state so colour is never the
only signal; the footer states the data source and how many providers are usable.

### Screen 3 · filtered, focus entering the second group

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ ◧ Databricks Coding Agents      model ▾ llama-4-maverick  ● ready            ⌘K   ▤   ◫      │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ┌───────────────────────────────────────────────────────────────┐
                                  │  gemin▏                                            3 matches  │
                                  ├───────────────────────────────────────────────────────────────┤
                                  │  ▾ YOUR PROVIDERS                                             │
                                  │  ▸○ gemini-3.8-flash      vertex · 1M ctx · key …7f3a         │
                                  │   ○ gemini-3.8-pro        vertex · 1M ctx · key …7f3a         │
                                  ├───────────────────────────────────────────────────────────────┤
                                  │  ▾ DATABRICKS · AI GATEWAY — 1 match                          │
                                  │   ○ gemma-3-12b           not served here                     │
                                  ├───────────────────────────────────────────────────────────────┤
                                  │  ↑↓ move  ⏎ select  ⌘⏎ keep open  esc close                   │
                                  │  gemini · matched name · 2 selectable · 1 unavailable         │
                                  └───────────────────────────────────────────────────────────────┘
```

`▸` marks the focused row. A group with no match collapses to a count line inside its
own group header, never disappearing — [U1](#screen-3-filtered-focus-entering-the-second-group).

### Screen 4 · the inspector (⌘I, and the only model facts surface below 1100 px)

```text
┌─────────────────────────────────────────────────────────────┐
│ INSPECTOR                                                ⌘I │
├─────────────────────────────────────────────────────────────┤
│  MODEL                                                      │
│    gemini-3.8-flash                            ○ available  │
│    google_vertex / google/gemini-3.8-flash                  │
│                                                             │
│    Provider     Google Vertex AI (your key)                 │
│    Wire         vertex_native                               │
│    Endpoint     …/locations/global/endpoints/openapi        │
│    Context      1,000,000        documented                 │
│    Max output      30,000        documented                 │
│    Tools        yes · signature round-trip required         │
│    Key          …7f3a · yours · project mobioos-506015      │
│                                                             │
│    THIS SESSION                                             │
│    4 turns · 2 on llama-4-maverick · 2 on gemini-3.8-flash  │
│    ▲ the switch was at turn 3. Earlier turns are not        │
│      retargeted.                                            │
│                                                             │
│    WHAT THIS DOES NOT CHANGE                                │
│    The agent still writes only to /Users/me/agent_scratch   │
│    and schema main.agent_ab12ef34.                          │
│                                                             │
│    [ Change model ]  [ Test connection ]  [ Manage keys ]   │
└─────────────────────────────────────────────────────────────┘
```

The per-turn breakdown is FR-10 made visible: a switch names the turn it took effect on,
and earlier turns are explicitly not retargeted.

### Screen 5 · providers and keys

```text
┌────────────────────────────────────────────────────────────────────────────────┐
│ Providers and keys                                                    ⌘,   esc │
├────────────────────────────────────────────────────────────────────────────────┤
│  Databricks AI Gateway                              workspace token · managed  │
├────────────────────────────────────────────────────────────────────────────────┤
│    Available here   5 models · claude-sonnet-4-5 not enabled                   │
│    Credential       your Databricks session (no key to manage)                 │
│    Last discovery   12 seconds ago             [ Refresh ]                     │
│                                                                                │
│  Google Vertex AI                                   ● connected                │
├────────────────────────────────────────────────────────────────────────────────┤
│    Key          service account · project mobioos-506015 · …7f3a               │
│    Added        2 November 2026 by raphael.mansuy@…                            │
│    Last used    3 minutes ago · 2 sessions                                     │
│    Models (3)   gemini-3.8-flash  gemini-3.8-pro  gemini-3.5-flash             │
│                                [ Test ] [ Rotate ] [ Revoke ]                  │
│                                                                                │
│  OpenAI                                             ⚠ key expired              │
├────────────────────────────────────────────────────────────────────────────────┤
│    Key          …9c41 · expired 2 hours ago (per the provider)                 │
│    Effect       gpt-4.1 and 2 other models unavailable to you                  │
│                                [ Test ] [ Replace key ]                        │
│                                                                                │
│  Anthropic                                          ✕ no key                   │
├────────────────────────────────────────────────────────────────────────────────┤
│    Nothing configured. 4 models would become available.                        │
│                                [ Add a key ]                                   │
│                                                                                │
├────────────────────────────────────────────────────────────────────────────────┤
│  source: database · keys encrypted with kek-2026-11 · 2 of 4 usable            │
└────────────────────────────────────────────────────────────────────────────────┘
```

The footer states the credential source. In degraded mode it reads
`source: seed only — keys cannot be saved` and every key action is disabled with that reason.

### Screen 6 · adding a service-account JSON key

```text
┌────────────────────────────────────────────────────────────────────────────────────┐
│ Add a key · Google Vertex AI                                                   esc │
├────────────────────────────────────────────────────────────────────────────────────┤
│  Paste the service-account JSON, or drop the .json file here.                      │
│  It is encrypted before it is stored, and never shown again.                       │
├────────────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │  {                                                                           │  │
│  │    "type": "service_account",                                                │  │
│  │    "project_id": "mobioos-506015",                                           │  │
│  │    "client_email": "vertex-express@mobioos-506015.iam.gserviceaccount.com",  │  │
│  │    "private_key": "-----BEGIN PRIVATE KEY-----\n••••••\n-----END …",         │  │
│  │    "token_uri": "https://oauth2.googleapis.com/token"                        │  │
│  │  }                                                                           │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
├────────────────────────────────────────────────────────────────────────────────────┤
│  ✓ type is service_account                                                         │
│  ✓ project_id mobioos-506015                                                       │
│  ✓ private_key parses as RSA                  [ masked ]                           │
│                                                                                    │
│  Which models should this key enable?                                              │
│  ☑ gemini-3.8-flash    ☑ gemini-3.8-pro    ☐ gemini-3.5-flash                      │
├────────────────────────────────────────────────────────────────────────────────────┤
│  Prompts and tool results leave your workspace: Google's                           │
│  terms apply, not Unity Catalog.                                                   │
├────────────────────────────────────────────────────────────────────────────────────┤
│                       [ Test connection ]   [ Save key ]                           │
└────────────────────────────────────────────────────────────────────────────────────┘
```

Validation runs per field on paste (K1), the private key is masked after validation (K2),
and Test connection must pass before Save unless the user skips it with the error shown (K3/K4).

### Screen 7a · degraded: no database, the picker still opens

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ ◧ Databricks Coding Agents      model ▾ llama-4-maverick  ● ready            ⌘K   ▤   ◫      │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ┌────────────────────────────────────────────────────────────────┐
                                  │ SEARCH                                                       ⚠ │
                                  ├────────────────────────────────────────────────────────────────┤
                                  │  ┌──────────────────────────────────────────────────────────┐  │
                                  │  │ Keys cannot be saved: the model database is unreachable. │  │
                                  │  │ Databricks models work. External models need a key.      │  │
                                  │  └──────────────────────────────────────────────────────────┘  │
                                  ├────────────────────────────────────────────────────────────────┤
                                  │  ▾ DATABRICKS · AI GATEWAY                   5 of 5            │
                                  │  ✓ llama-4-maverick    128k ctx · 8k out · measured            │
                                  │  ○ gpt-oss-120b        128k ctx · 24k out · measured           │
                                  ├────────────────────────────────────────────────────────────────┤
                                  │  ▸ EXTERNAL — unavailable without a key store                  │
                                  ├────────────────────────────────────────────────────────────────┤
                                  │  source: seed only · keys: not available                       │
                                  └────────────────────────────────────────────────────────────────┘
```

C-5: a degraded app is not a broken app. Databricks models keep working and the reason
external models are unavailable is stated, not implied.

### Screen 7b · a degraded model row, focused

```text
  ┌──────────────────────────────────────────────────────┐
  │ ▸⚠ gpt-4.1          openai · key expired 2 hours ago │
  │    └ 401 Unauthorized: Incorrect API key provided.   │
  │      [ Replace key ]   [ Use another model ]         │
  └──────────────────────────────────────────────────────┘
```

The provider's own sentence, redacted, plus two actions — never "internal error". This is
the failure mode [the ACP probe](../../docs/e2e/20_acp_config_probe.txt) §C recorded.

### Screen 7c · narrow (≤ 820 px): the picker becomes a sheet

```text
┌───────────────────────────────────┐
│ Model                     ● ready │
├───────────────────────────────────┤
│  Search                           │
├───────────────────────────────────┤
│  ▾ DATABRICKS · AI GATEWAY        │
│  ✓ llama-4-maverick               │
│      128k · 8k out · measured     │
│  ○ gpt-oss-120b                   │
│      128k · 24k out · measured    │
├───────────────────────────────────┤
│  ▾ YOUR PROVIDERS                 │
│  ○ gemini-3.8-flash               │
│      vertex · 1M ctx · key …7f3a  │
│  ⚠ gpt-4.1                        │
│      openai · key expired 2h ago  │
└───────────────────────────────────┘
```

Below 1100 px the chip is already hidden ([`styles.css:211-213`](../../apps/coding-agent/web/src/styles.css)),
so the sheet is opened from the inspector's **Change model** and the palette command,
both of which exist at every width.

<!-- END GENERATED WIREFRAMES -->

---

## Behaviour rules

Each rule is testable, and each names the test that fails if the behaviour is removed.

| # | Rule | Test |
|---|---|---|
| U1 | Typing filters all groups; a group with no match collapses to a count line inside its own header, and never disappears silently | E-11 |
| U2 | `↓` from the last row of a group moves into the next group, expanding it if collapsed | E-11 |
| U3 | The footer states *why* the match happened (`matched name`, `matched provider`) | E-11 |
| U4 | `⌘⏎` selects and keeps the popover open, for comparing facts between two models | E-11 |
| U5 | `esc` closes and returns focus to the trigger | E-11 |
| U6 | The popover is ≤ 460 px wide and ≤ 60 % of the viewport height, and scrolls inside | overflow audit |
| U7 | Selecting an unavailable model is impossible: the row has no action, only a remedy | E-9 |
| U8 | A switch that will restart the agent says so **before** it happens, not while it happens | E-6 |
| U9 | The popover opens with the current model scrolled into view and visible | E-11 |
| U10 | A stale catalogue (older than the discovery TTL) shows "updated Nm ago" and offers Refresh, rather than pretending to be current | E-8 |

---

## Navigation map

<!-- GEN:navigation -->

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ SCREEN                                               HOW YOU GET THERE                 │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Workspace · three panes · /                                                            │
│   └ Model picker (popover, or a sheet below 820)     chip · ⌘K model · inspector       │
│     └ Providers and keys · /settings/providers       "Manage keys" · ⌘,                │
│       └ Add a key · /settings/providers/{kind}/new   "Add a key" on a provider row     │
│       └ Test connection                              a form button, runs before save   │
│     └ Inspector pane · ⌘I                            the panel toggle                  │
│       └ Change model                                 the same picker, at every width   │
└────────────────────────────────────────────────────────────────────────────────────────┘

Three ways into one picker; one way into settings; a back path from every surface.
`esc` always leaves, and focus always returns to the element that opened it.
```

<!-- /GEN:navigation -->

Three entry points to one picker, one entry point to settings, and one back path from every surface.
No modal traps: `esc` always leaves, and focus always returns to the element that opened it.

---

## Grouping and order

Deterministic order matters: a list that reorders itself cannot be learned.

| Rank | Group | Condition |
|---|---|---|
| 1 | **Databricks · AI Gateway** | `provider.kind = databricks` |
| 2 | **Your providers** | a live credential with `scope_kind = user` exists |
| 3 | **Workspace providers** | a live `workspace` credential exists and the user holds a grant |
| 4 | **Not available here** (collapsed by default) | any state other than `available`, or no credential |

Within a group: current model first, then `available`, then `degraded`/`unauthorised`, then
unselectable; then by `display_name`, case-insensitively. The comparator is one function in
`domain/models.ts`, unit-tested against a fixture list — the order is a test, not an accident of
iteration.

A group is **never missing**: during a search every group appears with a count, even at zero
matches, so the user learns that a provider exists before discovering it has nothing to offer.

---

## Copy, in full

Every string is product copy, not a placeholder. A UI review quotes from this table.

| Situation | Copy | Never |
|---|---|---|
| switch, same protocol | `Switched to {name}. Applies to your next message.` | "Model updated" |
| switch, needs restart | `Switching provider restarts the agent. Your conversation is kept.` | "Please wait…" with no reason |
| refused, no grant | `You do not have access to {name}. Ask a workspace admin to grant it.` | "Forbidden" |
| refused, no key | `{Provider} needs a key before this model can run.` + `[ Add a key ]` | "Configuration error" |
| key expired | `{Provider} says: "{provider message}".` | "Authentication failed" |
| not enabled here | `Not enabled in this workspace. An account admin must enable {family} in the AI Gateway.` | hiding the entry |
| rate limited | `{Provider} is busy. Retrying once in {n}s.` | a silent retry |
| stalled | `The model stopped responding after {n}s. The provider's last words are in the detail.` | a spinner |
| no database | `Keys cannot be saved: the model database is unreachable. Databricks models work.` | "Database error" |
| unverified limits | `Limits unverified. Requests are capped conservatively at 64k / 4k.` | presenting a guess as a fact |
| external egress | `Prompts and tool results in these sessions leave your Databricks workspace.` | silence |

---

## Accessibility contract

Tested by `scripts/a11y-audit.mjs` plus a component test; WCAG 2.2 AA is the bar.

| Requirement | Implementation |
|---|---|
| The trigger announces itself | a button with `aria-haspopup="listbox"`, `aria-expanded`, and an accessible name that includes the current model |
| The popover is a combobox over a listbox | `role="combobox"` on the search input, `aria-controls`, `aria-activedescendant` pointing at the focused row |
| Groups are announced | `role="group"` with `aria-label` that includes the count |
| State is not colour-only | the glyph column plus `aria-describedby` pointing at the state text |
| Focus never escapes | focus is trapped while open; `esc` closes and restores focus to the trigger |
| Targets ≥ 24 × 24 px | row height 32 px; the glyph is decorative, the entire row is the target |
| 200 % zoom | the popover scrolls internally and the page never scrolls sideways (overflow audit) |
| Reduced motion | no open/close animation under `prefers-reduced-motion: reduce` |
| A switch is announced | polite `role="status"`: `Switched to {name}. Applies to your next message.` |
| The inspector's facts are a pair list | `<dl>` so "Context" and "1,000,000" are read as a pair |

---

## Picker states

Every state below is reachable, and each has copy in the table above. The glyph is the scanning aid;
the words are the accessible truth.

| State | Glyph | Selectable | What the row shows |
|---|---|---|---|
| current | `✓` | — | the model, its limits, and `current` in the footer |
| available | `○` | yes | limits and their evidence |
| degraded | `⚠` | yes | the provider's own sentence, redacted, plus `[ Retry ]` |
| unauthorised | `⚠` | yes | the provider's 401 text plus `[ Replace key ]` |
| unverified | `·` | yes | `limits unverified · capped at 64k / 4k` |
| no credential | `✕` | no | `no key · add one` with the action inline |
| not enabled here | `◌` | no | `not enabled · an admin must enable it` |
| not served here | `◌` | no | `not served in this workspace` |
| unknown | `?` | yes | `never probed` and when it was added |
| degraded source | `⚠` in the header | — | `source: seed only · keys unavailable` across the top |

---

## Empty and first-run states

| State | What the user sees | Why |
|---|---|---|
| No Databricks models available | `The AI Gateway is not reachable from this app. The workspace connection is the problem; ask your admin.` | the app never pretends a model is missing when the connection is |
| No external providers configured | the "Your providers" group is absent, and a single line in settings says `Nothing configured. 3 providers would add 9 models.` | the invitation lives in settings, not in the picker |
| A key saved but untested | the model appears as `unknown`, with `Limits unverified` in the inspector | honesty about what has been proven |
| A model removed from the workspace | `not served here` on the row, with `Resume with another model` on the session | FR-13: a session is never orphaned |
| Demo mode (`agent_mode="fake"`) | the picker shows `fake/model-a` and `fake/model-b` with no provider groups | the fake agent advertises its own list; the UI must not invent one |

---

## What this design refuses to do

| Refused | Why |
|---|---|
| A green dot for "ready" without a probe | an opinion is not a fact |
| Sort by a vendor's notion of quality | the measurements in this repository say quality is task-dependent; the user decides |
| Auto-select a model the user did not choose | [11 D6](11-decisions-risks.md): a silent substitution makes the transcript lie |
| Put the picker in the palette only | the palette is keyboard-first; a mouse user must have the chip |
| A modal for key entry | key entry is revisited and interrupted; a route survives a refresh and a tab close |
| Show `0 tokens` before the first turn | an unknown cost is not zero |
| Hide a model the user cannot use | FR-20: naming the gate hands them the action |
| A second "which model" indicator | one chip in the topbar, one facts block in the inspector, one list in the picker — three views of one value, never two sources |
