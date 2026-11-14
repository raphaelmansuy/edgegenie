# Specification validation

[Index](README.md) · Product test plan: [11](11-tests-traceability.md)

This record preserves the original specification validation. For subsequent application changes and
executed product tests, see [implementation evidence](13-implementation-evidence.md).

This original record concerns document links, coverage and diagram validity. Product implementation and its
planned unit/E2E/performance/accessibility tests have **not** been performed by creating this spec.

Validated 14 November 2026 against source baseline `548666c`.

| Check | Result |
|---|---|
| Package coverage validator | 18 requirements, 48 edge cases, 20 defined test groups; no uncovered/undefined references |
| Internal file/anchor links | 14 Markdown documents, 172 links, zero broken links |
| Printable ASCII width/borders | Five wireframes, zero alignment errors |
| Mermaid syntax | Eight diagrams parsed successfully with Mermaid 12.3.0 |
| Mermaid SVG rendering | All eight rendered successfully with the installed Mermaid CLI/browser environment |
| Visual sample review | Interaction statechart and logical ER previews inspected; labels and pastel state/entity fills readable |
| Application code changes | None; changes are confined to this specification directory |

The package includes two sequence diagrams, one logical ER diagram, three statecharts, a component
flow and a phase dependency graph. All eight include a pastel base theme with dark text.
Rendered SVG/PNG checks used temporary files; the durable diagrams are the Mermaid source blocks.

Not claimed: product feature implementation, executed future E2E matrix, measured product latency,
live notebook parity, actual screen-reader certification, or production deployment of this spec.
The plan defines those gates for implementation; zero documentation-check failures is not their substitute.

## Reproduce

From the repository root:

```sh
python3 specs/015-notebook-md/validate.py
node apps/coding-agent/web/scripts/verify-spec-links.mjs specs/015-notebook-md
node apps/coding-agent/web/scripts/verify-spec-ascii.mjs specs/015-notebook-md
```

The existing ASCII checker recognizes Unicode boxes. This package uses printable ASCII boxes,
so `validate.py` performs the actual width/border checks as well as requirement/risk coverage.
Use the existing `verify-spec-mermaid.mjs` with an available Mermaid/jsdom tool environment to
parse Mermaid blocks. In this session the installed temporary validation packages were used:

```sh
MERMAID_PATH=/tmp/mmd/node_modules/mermaid/dist/mermaid.core.mjs \
JSDOM_PATH=/tmp/mmd/node_modules/jsdom/lib/api.js \
node apps/coding-agent/web/scripts/verify-spec-mermaid.mjs specs/015-notebook-md
```

These paths are session tooling, not repository prerequisites. Use equivalent installed packages
when reproducing elsewhere. They are not application runtime dependencies. Rendering was checked
by extracting each fenced block to a temporary `.mmd` file and invoking the installed `mmdc`.

