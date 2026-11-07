# 06 · Edge cases and testing

[Index](README.md) · prev: [05 Implementation plan](05-implementation-plan.md) · next: [07 Decisions and risks](07-decisions-risks.md)

Every edge case has three things: **what happens**, **the mitigation**, and **the test that fails if
the mitigation is removed**. A case without a test is a wish.

Groups: **A** write path and fence · **B** the notebook surface · **C** concurrency, conflict and
loss · **D** workspace and platform · **E** editor and input · **F** accessibility and rendering.

---

## A · The write path and the fence

| # | Case | Mitigation | Test |
|---|---|---|---|
| A1 | Save a path **outside** the working folder | `check_path` → `ASK` → approval sheet naming the path and reason | post without approval → `403`; with approval → `200` |
| A2 | A client lies: posts an out-of-fence path with `approval_id` for a *different* path | the approval is bound to the path server-side; mismatch → `403` | approval for `/a` used on `/b` → refused |
| A3 | Notebook cell contains the **separator string** inside a string literal | the parser is quote-aware; a separator inside `"""…"""` does not split | fixture notebook with `# COMMAND ----------` inside a docstring round-trips unchanged |
| A4 | Save a notebook with **zero cells** | allowed; serializes to header only | round trip: empty → header → empty |
| A5 | The workspace `import` API rejects `format=SOURCE` for a language change | fallback: `create` at a temp path, then swap | integration test with a fake returning 400, asserting the fallback runs |
| A6 | Save a **folder** path | `IsADirectoryError` → `400` with a clear message | `POST` a directory path → `400`, no partial state |
| A7 | Save a path with `..` in it | `_inside` refuses traversal; `ASK` not `ALLOW` | `/agent_scratch/../etc/x` → `ASK`/deny, never silent allow |
| A8 | Save with a trailing slash, or doubled slashes | `_norm` collapses; the same object is targeted | `//a//b/` and `/a/b` produce the same verdict |
| A9 | Two saves in flight from the same tab (double `⌘S`) | save is serialised per document; the second waits | rapid double-save → one import, one event |
| A10 | Save fails mid-import (network drop) | object unchanged; UI shows error; draft kept | fault-inject the import → `500`, object byte-identical, draft present |
| A11 | Very large text on save (> 4 MB) | rejected client-side with an explanation before the request | 5 MB body → refused before network |
| A12 | Unicode: emoji, RTL, combining marks, NUL | text is UTF-8 end to end; no byte slicing on save | round trip a corpus of pathological strings |
| A13 | CRLF vs LF | normalise to LF on save **only** if the original was LF; otherwise preserve | CRLF file saved unchanged keeps CRLF |
| A14 | Trailing newline at EOF | preserved exactly; never added or stripped | property test over generated endings |

---

## B · The notebook surface

| # | Case | Mitigation | Test |
|---|---|---|---|
| B1 | Move a cell: ids stay stable, diff says "moved" | id preserved through the move operation | move 5→1: id order changes, ids identical |
| B2 | Delete the last remaining cell | allowed; the notebook becomes empty (A4) | delete all → save → empty notebook |
| B3 | Convert a markdown cell with rendered HTML-looking text to code | conversion is a `kind` change only; source untouched | convert twice → byte-identical source |
| B4 | `⌥↑` at a cell's **first** line | moves the whole cell up, not the line | caret at line 0, `⌥↑` → cell order changes |
| B5 | A markdown cell being edited when the tab closes | draft keeps the **editing** state, not the rendered one | close mid-edit → reopen → still editing, text intact |
| B6 | A cell whose language differs from the notebook's (`%sql` in a python notebook) | per-cell language is preserved and used for highlighting | save → reopen → still `%sql`, still highlighted as SQL |
| B7 | Magic cell (`%md`, `%sh`, `%pip`) edited then saved | magic prefix is re-emitted exactly once | round trip fixture with all magics |
| B8 | A `%md` cell whose content contains `%sql` on a line | it is markdown content, not a magic switch | fixture, round-trip exact |
| B9 | 400 cells (the parser's cap) | allowed at the cap; the 401st is refused with an explanation | 401 cells → save refused, message names the limit |
| B10 | Cell source exceeding `MAX_CELL_CHARS` (20 000) | refused on save with a pointer to the offending cell | oversized cell → `400` naming the index |
| B11 | Reordering while the agent proposes a change | the proposal is against a version; the reorder makes it stale → diff, not silent apply | propose, reorder, accept → conflict path |
| B12 | Notebook language is `R` / `Scala`: separators use `#` / `//` | `PREFIX` map drives the serializer | round trip for each of the 4 prefixes |

---

## C · Concurrency, conflict and loss

| # | Case | Mitigation | Test |
|---|---|---|---|
| C1 | Two tabs edit the same file | version token; loser gets 409 + its own text back | two-page e2e |
| C2 | The agent writes while the user is dirty | the write becomes a proposal, not an apply | agent write to an open dirty doc → diff, buffer unchanged |
| C3 | A save lands between the version check and the import | undetectable (no conditional write) → **draft is the guarantee** | force the interleave; assert draft restorable |
| C4 | Two simultaneous saves from two tabs | per-object serialisation server-side; one wins, one 409 | parallel saves → exactly one 200 |
| C5 | The user discards a conflict by choosing "take theirs" | their text is kept in the draft store for 30 days | discard → draft still recoverable |
| C6 | A reload during a save | draft is written **before** the request, so the reload loses nothing | reload mid-save → draft present |
| C7 | Browser crash with a dirty buffer | debounced draft (≤ 150 ms of loss) | simulated by writing then killing the page |
| C8 | Draft store quota exceeded | oldest drafts evicted; a visible note | fill `localStorage` → graceful eviction, no throw |
| C9 | Clock skew between client and server | version token does not use time; it uses `object_id` + `size` | token stable under a skewed clock |
| C10 | The object was **deleted** in the workspace while open | save returns `404`; UI offers "save as new" | delete then save → `404` + recovery affordance |

---

## D · Workspace and platform

| # | Case | Mitigation | Test |
|---|---|---|---|
| D1 | Permission denied on read | existing behaviour: the tree row says so | `403` from the API → row shows the reason |
| D2 | Permission denied on **write** (read-only share) | fence says ALLOW but the API refuses → surfaced as `403`, not a crash | mock a read-only share |
| D3 | The path is inside a **Git folder** | editable; the commit flow is explicitly **not** offered, with a note | edit + save inside a repo path works; no commit UI |
| D4 | The object is a **dashboard / query / job**, not a file | not a `Doc`; never reaches the editor | opening such an object has no editor affordance |
| D5 | The path contains spaces, `#`, `?`, emoji | URL-encoded correctly on every call | fixture paths with each character |
| D6 | The workspace is on a **different region/host** | `host` comes from config, never hard-coded | existing tests cover host injection |
| D7 | The token expires mid-session | `401` surfaced as "sign in again"; draft kept | expire the token, save → `401` + draft |
| D8 | The file is a **binary** (`.parquet`, `.png`) | never opened in the editor; viewer says "binary" | binary path → no editor, explanation |
| D9 | A file > 400 KB | read-only with a banner; no Save (ED-6) | 500 KB file → banner, no Save |
| D10 | A notebook with a cell the parser marks `truncated` | read-only for that document, because saving would drop the tail | truncated fixture → read-only banner |

> D10 deserves emphasis: saving a truncated document would **destroy data**. The editor must refuse
> to save anything the reader truncated, and say why.

---

## E · Editor and input

| # | Case | Mitigation | Test |
|---|---|---|---|
| E1 | IME composition (Chinese, Japanese, Korean) | CodeMirror handles composition; no save on composition end | type via composition events → text correct, no spurious save |
| E2 | Dead keys and accent composition | not intercepted by the keymap | `⌥e` then `e` → `é` |
| E3 | A very long single line (minified JS) | horizontal scroll, no wrapping; no layout blowup | 100 KB single line renders and scrolls |
| E4 | Tab vs spaces, mixed indentation | preserved exactly; auto-indent only on Enter | round trip preserves mixed indentation |
| E5 | Undo across a tab switch | undo stack is per document and survives | type, switch, switch back, undo → works |
| E6 | Paste rich text / HTML | paste as plain text | paste HTML → plain text only |
| E7 | Paste 1 MB | accepted, with a brief "large paste" note | paste 1 MB → no freeze > 200 ms |
| E8 | `⌘S` while focus is in the composer | saves the active document, does not submit the composer | focus composer, `⌘S` → save, no send |
| E9 | The browser's own find (`⌘F`) vs ours | ours takes `⌘F` only when the editor has focus | `⌘F` outside the editor → browser find |
| E10 | Drag to select across cells | selection is per cell in notebook mode, documented | drag across a boundary → selects within the cell |
| E11 | Two editors mounted (split not supported, but) | only one editor instance exists at a time | DOM assertion: ≤ 1 `.cm-editor` |

---

## F · Accessibility and rendering

| # | Case | Mitigation | Test |
|---|---|---|---|
| F1 | Screen reader in the editor | CodeMirror's `contenteditable` has an accessible name; the bar names the document | `audit:a11y` at 0 |
| F2 | 200 % zoom | editor scales; no clipped gutter | existing zoom check extended to the editor |
| F3 | Forced colours (Windows HC) | fence chip and cell attribution remain legible | forced-colours screenshot |
| F4 | `prefers-reduced-motion` | no animated diff transitions | existing motion rule covers it |
| F5 | Dark mode contrast of syntax colours | colours come from theme tokens | `audit:a11y` in dark |
| F6 | Editor mount adds CLS | pane reserved before mount | `audit:cls` = 0.0000 |
| F7 | Focus trap: tabbing out of the editor into the bar | focus order is document → bar → next zone | tab-order test |

---

## The test map

Which harness owns which group, and what "green" means.

| Group | Harness | Location | Gate |
|---|---|---|---|
| A1–A14 (fence, serialize) | `pytest` | `apps/coding-agent/tests/` | all pass; `check_path` mutation test passes |
| B1–B12 (cells) | `pytest` + `vitest` (shared corpus) | both | round-trip property holds on the corpus |
| C1–C10 (concurrency) | Playwright (two pages) + `pytest` | `web/scripts/` | the 409 path is exercised, not mocked |
| D1–D10 (platform) | `pytest` with fakes + e2e | `apps/coding-agent/tests/` | D9/D10 refuse to save |
| E1–E11 (input) | Playwright | `web/scripts/editor-e2e.mjs` | all pass in one run |
| F1–F7 (a11y) | existing audits | `web/scripts/a11y-audit.mjs`, `cls-audit.mjs` | 0 findings, 0.0000 CLS |

### The property tests, stated as properties

```
P1  serialize(parse(t)) ≡ t                    for t in real notebooks (200)
P2  parse(serialize(c)) ≡ c  (ids regenerated) for c in generated cell lists (5000)
P3  applyAll(diff(base, prop)) ≡ prop          for (base, prop) in generated pairs (200)
P4  applyNone(diff(base, prop)) ≡ base
P5  concat(highlight(x, lang)) ≡ x             for x in generated strings (10 000), 8 languages
P6  check_path agrees: TS mirror ≡ Python      for a corpus of 500 paths
```

P6 is the one that keeps the fence honest across two languages. It is a *test*, not a runtime check,
because a runtime disagreement would be a production defect; a test failure is a build defect.

---

## How each case was chosen

Not by brainstorming. Each group comes from a specific failure the architecture makes possible:

- **A** exists because the plan adds a second write path. Every case is a way that path could write
  something it should not, or fail to write something it should.
- **B** exists because a notebook is not a text file. Each case is a way the round trip could lose
  structure.
- **C** exists because the workspace API has no conditional write ([01](01-current-state-audit.md#what-the-databricks-workspace-api-gives-us)).
  Each case is a way two writers could collide.
- **D** exists because the workspace is a real, permissioned, multi-tenant system with objects that
  are not files.
- **E** exists because a text editor is an input device and input is locale-dependent.
- **F** exists because [001-perfect-shell](../001-perfect-shell/README.md) set a bar of 0 findings and
  0.0000 CLS, and a new surface must not lower it.

[Next: decisions and risks →](07-decisions-risks.md)
