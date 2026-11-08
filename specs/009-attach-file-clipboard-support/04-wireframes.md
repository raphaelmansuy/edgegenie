# 04. Wireframes (ASCII)

**Every screen and every state this feature introduces, drawn to the column.**

Wireframes are ASCII on purpose: they are diffable, they survive a review, and they cannot hide a
spacing bug behind a pretty picture. The monospace box *is* the spec — a control that has no box here does
not exist, and the sizes are the sizes the CSS must produce.

Spec [009](./README.md) · requirements [03](./03-requirements.md) · diagrams [05](./05-diagrams.md)

---

## 1. The composer at rest, text-only model

The state most users see first. Note what is **absent**: no image affordance, because
[CAP-3](./03-requirements.md) says a control that cannot work must not be present.

```
┌─ Dock · 380 px ─────────────────────────────────────────────────────┐
│                                                                     │
│  ● READY            in context: report.md                           │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─ composer ─────────────────────────────────────────────────────┐  │
│  │  ┌ ctx-row ─────────────────────────────────────────────────┐  │  │
│  │  │  ❐ report.md ×                                          │  │  │
│  │  └──────────────────────────────────────────────────────────┘  │  │
│  │                                                                │  │
│  │  Ask for a notebook, a job, a fix, an investigation…           │  │
│  │                                                                │  │
│  │  +  ＠  /   model llama-4-maverick        ⏎ send  ┌────────┐  │  │
│  │  │                                                  │  Send  │  │  │
│  │  └─ 24×24, tooltip:                              └────────┘  │  │
│  │     "Attach a file (⌘⇧A)"                                     │  │
│  └────────────────────────────────────────────────────────────────┘  │
│  Only use the agent with code and data you trust                    │
└─────────────────────────────────────────────────────────────────────┘
```

The `+` is new. `＠` and `/` already exist. **Nothing moves** when `+` is added: it takes the slot the row
already had on the left, and the row is `flex` with the hint and Send pinned right.

---

## 2. The `+` menu, open

Reported screen: the menu exists but offers only *Attach files / Add context / Connectors*, and *Attach
files* does nothing. Here it does something.

```
                         ┌─ attach menu · 220 px ─────────────┐
                         │  📎  Attach files…            ⌘⇧A  │  ← focused
                         │  ＠  Add context…             ⌘⇧A  │
                         │  🔌  Connectors                 ▸  │  ← placeholder
                         └────────────────────────────────────┘
  ┌─ composer ─────────────────────────────────────────────────────┐
  │  Ask for a notebook, a job, a fix, an investigation…           │
  │  +  ＠  /   model llama-4-maverick        ⏎ send  ┌────────┐   │
  └────────────────────────────────────────────────────────────────┘
```

Rules the drawing encodes:

| Rule | Why |
|---|---|
| Menu opens **above** the field, left-aligned to `+` | It would cover the textarea otherwise; every chat app does this |
| Three rows, 32 px each, one focus ring | [AFC-19](./03-requirements.md) keyboard reachable |
| `Connectors ▸` is present but disabled-with-reason | The report shows it; removing it would be a regression |
| `⌘⇧A` shown once, on the first row | Two chords for one action is a bug, not a feature |

---

## 3. Dragging files over the composer

```
┌─ Dock · 380 px ─────────────────────────────────────────────────────┐
│  ┌─ composer ── ╭──────────────────────────────────────────────╮ ─┐ │
│  │             │                                              │  │ │
│  │             │          ┌────────────────────────┐          │  │ │
│  │             │          │   ⬇                    │          │  │ │
│  │             │          │   Drop to attach       │          │  │ │
│  │             │          │   PNG, JPG, CSV, TXT…  │          │  │ │
│  │             │          └────────────────────────┘          │  │ │
│  │             │                                              │  │ │
│  │             ╰──────────────────────────────────────────────╯  │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

- Dashed inset border, 2 px, `--blue-300`, on the composer's own box — no new element in the flow, so
  dropping does not shift the layout.
- The live region behind `aria-describedby` reads "drop to attach" ([AFC-20](./03-requirements.md)).
- The accepted-types line is generated from the capability matrix, so it can never disagree with what the
  server accepts.

---

## 4. Paste: the fastest path, and the one that was missing

```
  user presses ⌘V with a screenshot on the clipboard
        │
        ▼
┌─ composer ─────────────────────────────────────────────────────────┐
│  ┌ ctx-row ──────────────────────────────────────────────────────┐ │
│  │ ┌──────────────┐  ┌────────────────┐                          │ │
│  │ │ ▨ pasted-…png│  │ ❐ data.csv   × │                          │ │
│  │ │   ⣾ 42%      │  └────────────────┘                          │ │
│  │ └──────────────┘                                              │ │
│  └───────────────────────────────────────────────────────────────┘ │
│  Describe what this chart shows…                                   │
│  +  ＠  /   model llama-4-maverick            ⏎ send  ┌────────┐  │
└───────────────────────────────────────────────────────────────────┘
```

**The interaction contract, in order:**

1. `paste` fires. The handler calls `preventDefault()` **only if** `clipboardData.files.length > 0`.
   Text paste is untouched ([AFC-1](./03-requirements.md)).
2. A chip appears **synchronously**, in `pending` state, with the local `File` already in memory. No
   await before the chip exists ([P8](./01-five-whys.md)).
3. The upload runs behind it. The chip's progress is the only thing that changes.
4. On success the chip becomes `ready` with a thumbnail. On failure the chip becomes `failed` with the
   server's sentence and a retry control ([AFC-6](./03-requirements.md)).

---

## 5. The chip, all four states

```
 pending          ready                failed                attached (in transcript)
┌─────────────┐  ┌─────────────┐      ┌─────────────┐       ┌─────────────┐
│ ▨ shot.png  │  │ ▨ shot.png  │      │ ▨ shot.png  │       │ ▨ shot.png  │
│   ⣾         │  │          ×  │      │ failed   ↻ ×│       │             │
└─────────────┘  └─────────────┘      └─────────────┘       └─────────────┘
  no ×, because    × removes the       the word is there     no ×, history
  a pending chip   blob if unused      so colour is not      is immutable
  must be able                           the only signal
  to finish
```

| Property | Value | Source |
|---|---|---|
| Height | 28 px (chip) + 4 px gap | matches `.ctx-chip` today |
| Thumbnail | 20×20, `object-fit: cover`, 4 px radius | images only |
| Max width | 260 px, name ellipsised | `.ctx-chip` today |
| Icon fallback | `KIND_ICON[kind]`, 13 px | existing |
| Remove target | 18×18 visual, **24×24 hit area** | [AFC-22](./03-requirements.md) |

---

## 6. The transcript, after send

```
┌─ transcript ────────────────────────────────────────────────────────┐
│  YOU                                                                │
│  ┌──────────────┐ ┌──────────────┐                                  │
│  │ ▨ shot.png   │ │ ❐ data.csv   │   ← chips are part of the turn  │
│  └──────────────┘ └──────────────┘                                  │
│  Why does the spike at 18:00 not match the table?                   │
│                                                                     │
│  ┌─ Evidence ─────────────────────────────── all 3 proven ──────┐  │
│  │  ✓  read the attached image            describe_image        │  │
│  │  ✓  read the attached csv              read_blob             │  │
│  │  ✓  compared hour 18 to the table       dbx_run_sql          │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  The spike is a timezone artefact: …                                │
└─────────────────────────────────────────────────────────────────────┘
```

The evidence block is the requirement, not decoration: [AFC-15](./03-requirements.md) says an attachment
the agent could not read must be visible here rather than silently missed.

---

## 7. Refusals, drawn at the size they appear

```
┌─ composer ─────────────────────────────────────────────────────────┐
│  ⚠ report.pdf is 12.4 MB; the limit is 8 MB                        │
│  Ask for a notebook, a job, a fix, an investigation…               │
└────────────────────────────────────────────────────────────────────┘
```

```
┌─ composer ─────────────────────────────────────────────────────────┐
│  ⚠ Images need a model that can see them. llama-4-maverick         │
│    cannot; choose a vision model in the model control.  [Change ▸] │
│  Ask for a notebook, a job, a fix, an investigation…               │
└────────────────────────────────────────────────────────────────────┘
```

Both are `role="alert"`, both clear on the next edit, both are one sentence plus at most one action. The
copy register is enumerated in [09](./09-edge-cases.md#the-copy-register) and asserted as a table.

---

## 8. Narrow: 900 px, the dock is a drawer

```
┌─ App · 900 px ──────────────────────────────────────────────────────┐
│ ┌─ rail 276 ─┐ ┌─ main 480 ───────────────────────┐ ┌ edge handle ┐ │
│ │            │ │                                  │ │  ┌────────┐ │ │
│ │  Files     │ │   notebook cells                 │ │  │ Chat ▸ │ │ │
│ │            │ │                                  │ │  └────────┘ │ │
│ └────────────┘ └──────────────────────────────────┘ └─────────────┘ │
└─────────────────────────────────────────────────────────────────────┘

        (the conversation drawer opens over the work; chips wrap, not truncate)

┌─ drawer 380 ──────────────────────────────────────┐
│  ┌──────────────┐ ┌──────────────┐                │
│  │ ▨ shot.png   │ │ ❐ data.csv   │    ← 2 per row │
│  └──────────────┘ └──────────────┘                │
│  +  ＠  /   model…              ⏎ send  ┌──────┐ │
└───────────────────────────────────────────────────┘
```

The chip row is `flex-wrap: wrap`; it must never be `nowrap` with an overflow scroll, because a horizontal
scroll inside a message box is a bug the 007 audit already named. Verified at 900 and 760.

---

## 9. What changes on the page, and what must not

```
                    BEFORE                              AFTER
  ┌──────────────────────────────┐    ┌──────────────────────────────┐
  │  +  ＠  /   model…   Send    │    │  +  ＠  /   model…   Send    │
  └──────────────────────────────┘    └──────────────────────────────┘
        ▲                                   ▲
        │                                   │
     does not exist                    same slot, same height
                                       (24 px, no reflow)
```

The invariant: **the composer's height at rest is unchanged.** [CLS](./10-e2e-plan.md) is measured before
and after; a chip row appearing on paste *is* a shift, and it is excluded from CLS because it follows a
user input — but the resting layout must not move at all.
