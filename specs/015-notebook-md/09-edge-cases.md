# 09 — Edge-case register

[Index](README.md) · Contracts: [03](03-requirements.md) · Guards: [06](06-statecharts.md)
· Security: [07](07-rendering-security.md) · Test groups: [11](11-tests-traceability.md#test-groups)

## Register

Every listed case is a required implementation test. The table is a planned mitigation/coverage
register; it is not a report that those future tests passed. Input cross-products are addressed by
generated transition and parser tests in T19 and the matrix in [11](11-tests-traceability.md#matrix-and-evidence).

| Risk | Trigger and failure | Required mitigation | Requirements | Tests |
|---|---|---|---|---|
| E01 | Resting empty/whitespace Markdown falls into a source editor | Styled empty state outside Edit; new + Text explicitly enters Edit | MD-01, MD-03 | T01 |
| E02 | Read-only cell appears editable or blank | Same styled preview; Copy/navigation; mutation refused synchronously | MD-01, MD-14 | T01, T14 |
| E03 | Toolbar click blurs/unmounts editor before formatting | Keep Edit for internal focus, preserve selection, one transaction | MD-03, MD-11 | T02 |
| E04 | Final keystroke lost on immediate preview/save | Flush host source before snapshot/transition; revision agreement | MD-02, MD-14 | T02, T10 |
| E05 | Selecting prose/double-clicking a link accidentally edits | Interactive-child and selection guards; explicit Edit remains primary | MD-03 | T01, T06 |
| E06 | IME/overlay Esc or Enter commits partial text | Completion/dialog consumes first; compositionend before mode transition | MD-03, MD-11 | T02, T09 |
| E07 | Window blur/focus steals caret or changes mode | Preserve view/selection; distinguish external browser blur from cell exit | MD-14 | T12 |
| E08 | Link/Copy/outline keyboard event bubbles into cell commands | Child actions own events; no run/edit side effect | MD-03, MD-08 | T06, T09 |
| E09 | h1/h2 flatten; h5/h6 or duplicates disappear | Preserve depth in AST; contextual semantics; unique heading namespace | MD-04, MD-18 | T03, T16 |
| E10 | Ordered start/nested list/tasks/quotes flatten | Structured parser nodes, static preview tasks, semantic nesting | MD-05 | T04 |
| E11 | Pipes in code/escaped tables or uneven rows misparse | Defined GFM table behavior and locally scrollable semantic table | MD-07 | T04, T08 |
| E12 | Tilde/long/unclosed fence or unknown language misrenders | Fence-aware parser; bounded unclosed code; exact Copy; no execute | MD-06 | T08, T19 |
| E13 | Money/escaped dollars/code mistaken for math | Compatibility corpus and node-aware math token boundaries | MD-06 | T05 |
| E14 | Invalid TeX, module failure or macro expansion blanks notebook | Local source fallback, max size/expansion, accessible alternative | MD-06, MD-10 | T05 |
| E15 | Unsafe/encoded/control-character URL executes or navigates | Normalize then classify; active schemes inert; test redirects | MD-08, MD-10 | T06, T15 |
| E16 | HTML/script/iframe/SVG or agent instruction executes | Text-only HTML fallback; typed allowlisted nodes; no tools on render | MD-10, MD-16 | T06, T15 |
| E17 | Forged PUA marker/NaN index addresses missing math span | Typed math nodes; temporary marker adapter escapes and validates indexes | MD-10 | T05, T19 |
| E18 | Incomplete Markdown prefix stalls parser or swallows tail | Progress invariant, bounded node/depth counts, every-prefix tests | MD-05, MD-15 | T13, T19 |
| E19 | Relative/Unicode/encoded path resolves outside document namespace | Document-directory resolver, namespace traversal guard, caller-scoped links | MD-08 | T06 |
| E20 | Huge/wrong MIME/SVG/animated image exhausts resources | Placeholder; P1 type/byte/pixel limits and bounded decode | MD-09, MD-15 | T07, T17 |
| E21 | Image 401/403 reattempts using privileged credentials | Explain denial; no alternate principal or permission workaround | MD-09, MD-16 | T07, T15 |
| E22 | Remote tracker/redirect leaks identity or unexpected request | Explicit Load; no app credentials/referrer; approved origins only | MD-08, MD-09 | T07, T15 |
| E23 | Collapse/expand loses unsaved text, undo or mode | Flush/snapshot; keep source/history; expand to styled reading | MD-01, MD-14 | T12 |
| E24 | Delete/convert/navigation receives late parse/media result | Abort/dispose; full document/cell/revision/generation match | MD-14 | T12 |
| E25 | Reorder/duplicate heading targets old index | Cell identity + current mapping; distinct outline namespace | MD-04, MD-14 | T12, T16 |
| E26 | Export exceeds 400,000 bytes; user saves visible prefix | Document completeness propagated; read-only; retain original boundary notice | MD-17 | T14 |
| E27 | One source exceeds 20,000 server code points but document is smaller | Promote cell truncation to document unsafe-to-save before serialization | MD-17 | T14 |
| E28 | 401 short cells fit byte limit; parser silently returns 400 | Detect count truncation with one bounded lookahead; document read-only | MD-17 | T14 |
| E29 | Literal magic/separator/BOM/CRLF/edge blanks normalize unexpectedly | Preserve cell source semantics; explicit round-trip refusal; corpus parity | MD-02, MD-12 | T10, T14 |
| E30 | Permission revocation races formatting/save | Recheck mutation permission at invocation and server write boundary | MD-12, MD-14 | T14 |
| E31 | Save double-click/chord while request in flight | Existing single in-flight owner; no duplicate save | MD-12 | T10 |
| E32 | Source changes during Save; success marks newer text clean | Compare accepted snapshot with live revision; newer source remains dirty | MD-12, MD-14 | T10 |
| E33 | Agent edits clean notebook during reading | Existing reconciliation; refresh derived affected models; no scroll theft | MD-14, MD-16 | T11 |
| E34 | Agent/human edit races unsaved source | Preserve draft; incoming/conflict UI; no automatic overwrite | MD-12, MD-16 | T11 |
| E35 | Save denial, conflict, network or reload failure shown as saved | Existing outcomes remain explicit; preview state never settles write | MD-12, MD-14 | T10, T14 |
| E36 | Lazy editor/parser returns after tab/user/workspace switch | Dispose/cancel and scope cache; no wrong-document adoption | MD-14, MD-16 | T12, T15 |
| E37 | 320px/narrow dock/long token widens whole notebook | Container-based toolbar overflow; local table/code scrolling | MD-07, MD-18 | T08, T18 |
| E38 | Dark theme/200% zoom/reduced motion hides content or focus | Semantic colors, contrast/reflow/focus tests; static motion fallback | MD-18 | T03, T18 |
| E39 | Preview text inherits editor font or answer heading scale | Notebook profile; explicit visual-depth selectors in both viewers | MD-01, MD-13 | T03, T13 |
| E40 | Toolbar role has no entry path; read-only focus trapped | Real roving toolbar pattern; current cell entry; clear Tab exit | MD-03, MD-18 | T09 |
| E41 | Math claims accessibility but renders HTML only | DOM MathML/source-alternative assertion and manual reading test | MD-06, MD-18 | T05, T09 |
| E42 | Image alt or table headers missing; Copy denied | Semantic alt/headers; actionable clipboard failure; source still selectable | MD-07, MD-09, MD-18 | T07, T08, T09 |
| E43 | Print saves, prints source only, or loads remote assets | Styled print profile, print-only expanded Markdown; no requests/writes | MD-01, MD-18 | T18 |
| E44 | New grammar regresses streaming answers/file previews/SQL Copy | Shared adapter compatibility corpus, all prefixes; no automatic query action | MD-06, MD-13 | T08, T13 |
| E45 | Deep nesting/near-match delimiters causes superlinear work | Parser/node/depth budgets; instrumented adversarial scaling gates | MD-05, MD-15 | T17, T19 |
| E46 | Hundreds of cells repeatedly rebuild run plans/render caches | One metadata pass, prefix counts; cache unchanged cells; cap/evict | MD-15 | T17 |
| E47 | Draft/cache storage disabled/full or unbounded listener growth | Memory fallback; existing recovery limits; bounded cache, disposal checks | MD-12, MD-15 | T12, T17 |
| E48 | Emoji/surrogate pairs mix Python chars, JS units and byte limits | Server code-point authority; UTF-16 editor ranges; UTF-8 byte fixtures at exact boundaries | MD-02, MD-11, MD-17 | T02, T14, T19 |

## Unknown combinations

Generate event sequences spanning Edit/Preview/format/Save/agent update/collapse/reorder/delete and
navigation, with every async completion permuted before/after newer source revisions. Assert invariants:
source never changes without an authorized source transaction; read mode is interpreted; only current
results render; no background write/execute; resource counts return to baseline after disposal.

Parser fuzz corpus includes every prefix of valid documents and malformed Unicode/delimiter runs.
Seed any discovered failure into a named regression fixture and add an E-ID when its mitigation
differs. Do not promise exhaustive enumeration of all Unicode strings or browser/device combinations.

