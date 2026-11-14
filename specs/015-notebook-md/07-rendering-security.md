# 07 — Rendering dialect and trust boundaries

[Index](README.md) · Evidence: [02](02-code-grounding.md) · Architecture: [05](05-architecture.md)
· Failure handling: [06](06-statecharts.md) · Coverage: [09](09-edge-cases.md)

## Dialect

Target: CommonMark block/inline semantics plus the specified GFM features below and the existing
accepted math delimiters. An AST parser is a candidate implementation, not a substitute for this
contract. Preserve exact source separately; rendering does not serialize its own AST back to source.

| Construct | P0 interpretation | Edge rules |
|---|---|---|
| ATX and setext headings | Source levels 1–6, semantic context + separate visual depth | Duplicate labels receive namespaced IDs; empty/escaped markers remain valid text |
| Paragraphs and breaks | Soft breaks as spaces, two-space/backslash hard breaks as `<br>` | No paragraph-wide trim that loses intended code/hard-break meaning |
| Emphasis / strong / strike | Nested inline nodes, escaped delimiters literal | Preserve underscores in identifiers; no catastrophic regex search |
| Inline code | Matching backtick runs, code is inert | Dollar signs and Markdown inside code do not become math/formatting |
| Lists / quotes / tasks | Nested blocks, real `<ol start>`, `<ul>`, `<blockquote>`; disabled task checkbox | Formatting a task is explicit source editing; clicking preview cannot toggle it |
| Code fences | Backtick/tilde runs, valid closing length, language label, Copy | Unknown languages plain code; unclosed fence bounded to cell end; no auto-run |
| Tables | Alignment, escaped pipes, code spans and uneven rows per parser contract | Real headers; local scroll; do not invent data-grid sorting/execution |
| Math | `$...$`, `$$...$$`, `\(...\)`, `\[...\]` compatibility | Money/escaped dollars/code exclusions; valid HTML+MathML or source alternative |
| Links / references | Label/title and policy-approved destination | Broken reference remains readable; unsafe destination inert with reason |
| Images | Styled alt-text placeholder and source destination | P1 load lifecycle below; never auto-upload |
| Raw HTML | Literal/unsupported content with bounded display | No rehype-raw, innerHTML, SVG DOM, iframe or event handlers |
| Other extensions | Literal source or explicit unsupported block | Footnotes may be parsed by a library but are not an enabled product promise; test fallback |
| Mermaid fence | A code fence with Copy | The diagrams in this spec do not authorize runtime diagram scripts |

## Heading semantics

The AST keeps source depth. `MarkdownDocument` takes an explicit heading context, separate from
its visual profile. Proposed notebook context has a named document region and a document title
heading; source h1 maps to semantic h2, h2 to h3, and so on. Depth beyond h6 uses a heading role
with explicit `aria-level`, subject to manual assistive-technology testing. Never claim that
multiple h1 elements are inherently invalid; this context is a product outline decision.
Notebook visual h1 remains substantially larger than h2 even though its semantic tag may be h2.
Chat preserves its adapter contract until migrated deliberately, with its own outline assertions.

## URL policy

One pure classifier returns `{kind, normalizedDestination, allowed, reason}`. Parsing a URL is not
approval to fetch it. Normalize control characters and scheme casing; validate after canonicalization
and again at the request boundary. Never attach credentials to a destination supplied by Markdown.

| Destination | Policy |
|---|---|
| `https:` link | Allow ordinary navigation; explicit external indication; `noopener noreferrer` for new tabs |
| `http:` link | Inert with an insecure-link explanation; source can be copied |
| `mailto:` link | Allow only as a user-activated link, no background request |
| `#fragment` | Resolve within this notebook's heading namespace; use explicit navigation, not global `querySelector` on arbitrary source |
| `/Workspace/...`, `/Users/...`, `/Shared/...`, `/Repos/...` | Workspace navigation via existing host-scoped helper; no implied write permission |
| `./` / `../` relative link | Resolve against current document directory within workspace namespace; normalize segments, reject traversal above namespace root |
| `/Volumes/...` image | P1 authenticated volume-content resolver, not a browser navigation URL or a table query |
| Scheme-relative `//host`, userinfo URLs, `javascript:`, `data:`, `blob:` from source, `file:`, `vbscript:` | Reject; application-created object URLs are an internal capability, never source-authorized |
| Databricks HTML `$./notebook` anchor syntax | Preserve inert HTML text with compatibility note; no general raw-HTML exception |

URLs with spaces, parentheses, Unicode, percent escapes, backslashes and encoded controls require
explicit fixtures, not a single naive regex. Redirection is allowed only under the same media policy;
no backend fetcher can follow arbitrary external redirects. See [E15–E22](09-edge-cases.md#register).

## Images and privacy

P0 supports image-reference insertion, alt text and styled placeholders. P1 workspace/volume reads
use the caller's identity and existing workspace/file services where their contracts are appropriate.
If a new endpoint is needed, it accepts a typed workspace path, not a general URL. Check permission
at every read; 401/403 stays visible and is never retried with an app/service-principal credential.
No business SQL or warehouse is involved in Markdown rendering.

External images load only after explicit per-image action. Browser-direct HTTPS fetch omits app
credentials and uses `referrerpolicy="no-referrer"`; deployment CSP must permit only the product's
approved image origins. If no origin is approved, keep the placeholder. Do not add a wildcard
image proxy or broaden workspace OAuth scopes as part of a visual change.

Proposed P1 limits: 5 MiB compressed transfer, 16 megapixels decoded, 10-second request timeout,
maximum 4 concurrent loads per notebook. Enforce byte/type limits before decoding authenticated
content; external browser loading needs an implementation that can enforce equivalent bounds,
or remains a link/placeholder. Reject SVG, animated formats and unsupported MIME in P1.
Reserve a bounded aspect-ratio box; render `max-inline-size:100%`; provide alt text and Retry on
transient failure. Do not persist binary media or object URLs in preview caches.

## Math, parsing, and fallback

Keep `trust:false`, bounded size and explicit expansion limits. Require `htmlAndMathml` or an
equivalent accessible representation verified in the DOM; the existing HTML-only option cannot
be treated as proof of MathML ([C7](02-code-grounding.md#c7)). Keep KaTeX-owned DOM isolated
from React-owned fallback text. A failed formula falls back locally, not at notebook scope.

Do not insert private-use string markers that untrusted text can forge. Prefer real typed math
nodes with validated source ranges. If compatibility temporarily needs marker stashing, escape
literal marker characters and validate every finite integer/index before lookup. Test PUA,
NaN/out-of-range indexes, malformed delimiters, long macro expansions and repeated near-matches.

Parser failure, node/depth budget exhaustion or unavailable lazy modules yields a compact notice,
Copy source and a readable bounded source region. Edit is available only if complete and writable.
Fallback is visibly labeled **Preview unavailable**; it is the explicit exception to normal styled
reading, never the default render policy. Unknown AST node types receive bounded textual fallback.

## AI and provenance

No prompt parsing, tool invocation, SQL promotion side effect or remote asset fetch occurs merely
because an agent emitted Markdown. Existing “Open as query” is an explicit action, not execution;
the notebook profile hides chat-only promotion controls. Agent updates follow the existing clean-
adopt/dirty-conflict flow, retain cell identities when reconcilable and never move the user's focus.
Provenance, timestamps and render errors must not be invented from prose headings.

