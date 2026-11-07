#!/usr/bin/env python3
"""Generate every multi-box ASCII diagram in spec 005, and splice them into the documents.

Why generated: a box one column out of alignment reads as broken and the defect is invisible in a
diff. Here each box measures its own content, so the borders cannot drift.
`apps/coding-agent/web/scripts/verify-spec-ascii.mjs` parses the output and fails CI if that stops
being true.

    python3 tools/diagrams.py            # write into *.md, inside the GEN markers
    python3 tools/diagrams.py --check    # exit 1 if a marker pair is malformed
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from ascii import Box, stack

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent

# A diagram lives between two HTML comments. The block is matched exactly so a re-run is idempotent
# and can never leave a stray fence behind.
GEN = re.compile(
    r"(<!-- GEN:(\w+) -->)[ \t]*\n+```(?:text)?[ \t]*\n.*?\n```[ \t]*\n+(<!-- /GEN:\2 -->)",
    re.S,
)


# --------------------------------------------------------------------------- 01 audit
def today() -> list[str]:
    browser = Box(pad=2)
    browser.line("BROWSER")
    browser.line("EmptyState  <select>  models.map(id)   Chrome.tsx:184-188")
    browser.line("Topbar chip <select>  session.model    App.tsx:433-444")
    browser.line("no groups · no search · no state · two naming styles")

    api = Box(pad=2)
    api.line("FASTAPI")
    api.rule()
    api.line("GET /api/models                api/routers/api.py:105-112")
    api.line("  allowed  StaticModelCatalog  api/services/identity.py:41-51")
    api.line("  served   ServingBrowser      adapters/databricks/serving.py:18-32")
    api.line("  filter   allowed ∩ served, or allowed when served is None")
    api.rule()
    api.line("config_for(model_id, host)     agent_config.py:180-189")
    api.line("  KNOWN_ENDPOINTS  (5 ids)     agent_config.py:96-102")
    api.line("  else: string surgery         agent_config.py:185-186")
    api.line("  ENDPOINT_LIMITS  (5 entries) agent_config.py:84-90")
    api.rule()
    api.line("AgentConfig.as_opencode_json() agent_config.py:37-66")
    api.line("  ONE provider block · ONE apiKey {env:DATABRICKS_TOKEN}")
    api.rule()
    api.line("Orchestrator._provision        orchestrator.py:198-243")
    api.line("  write config → tool server → agent")
    api.line("  SessionSpec.env = {DATABRICKS_TOKEN: token}   :227-229")

    agent = Box(pad=2)
    agent.line("opencode acp")
    agent.line("provider dbx · @ai-sdk/openai-compatible")
    agent.line("baseURL {host}/serving-endpoints · model dbx/<endpoint>")
    agent.line("NO DATABASE: the event store is a dict")
    agent.line("api/adapters/memory/store.py:11-13")

    return stack(
        [browser, api, agent],
        ["GET /api/models · POST /api/sessions · POST .../model", "stdio JSON-RPC (ACP)"],
    )


# --------------------------------------------------------------------------- 03 layers
def layers() -> list[str]:
    web = Box(pad=2)
    web.line("web/   React 19")
    web.line("ModelPicker · ModelInspector · ProviderSettings · HealthBadge")
    web.line("domain/models.ts   pure: grouping · rank · label · order")

    routers = Box(pad=2)
    routers.line("api/routers/       thin: validate, delegate, map errors to statuses")

    services = Box(pad=2)
    services.line("api/services/")
    services.line("ModelService       catalogue assembly + policy   I/O-free")
    services.line("ModelResolver      id → ResolvedModel            I/O-free")
    services.line("CredentialService  ref → secret   the only decrypter")
    services.line("HealthService      probe + classify + cache")

    domain = Box(pad=2)
    domain.line("api/domain/llm/    PURE: dataclasses, no I/O, no vendor names")
    domain.line("model.py   ModelId · ProviderKind · ModelSpec · ResolvedModel")
    domain.line("limits.py  clamp() · Limits(evidence)")
    domain.line("policy.py  may_use(user, model, grants) → Decision")
    domain.line("errors.py  ModelError taxonomy")

    adapters = Box(pad=2)
    adapters.line("api/adapters/      the ONLY place a vendor string may appear")
    adapters.line("llm/store/pg.py        RegistryStore (Lakebase)")
    adapters.line("llm/store/memory.py    RegistryStore (tests, demo)")
    adapters.line("llm/store/seed.py      seed loader")
    adapters.line("llm/providers/         databricks · openai · anthropic · vertex")
    adapters.line("llm/vault/pg.py        CredentialVault")
    adapters.line("llm/vault/local.py     env-only vault (no database, C-5)")
    adapters.line("llm/discovery/         serving-endpoints → ModelSpecs")
    adapters.line("acp/agent_config.py    ResolvedModel → opencode.json")

    out = stack(
        [web, routers, services, domain, adapters],
        ["/api/models · /api/llm/*   JSON only, never a secret", "", "", ""],
    )
    out.append("")
    out.append("  arrows never point up: a request descends, results return as data")
    return out


# --------------------------------------------------------------------------- 06 envelope
def envelope() -> list[str]:
    kek = Box(pad=2)
    kek.line("KEK   AES-256, identified by kek_key_id")
    kek.line("lives in a Databricks secret scope")
    kek.line("or LLM_KEK (base64) in the environment")
    kek.line("NEVER in the database")

    dek = Box(pad=2)
    dek.line("DEK   AES-256-GCM, generated per credential row")
    dek.line("wrapped by the KEK, stored beside the ciphertext")

    ct = Box(pad=2)
    ct.line("ciphertext = AES-256-GCM(DEK, plaintext)")
    ct.line("stored with its iv and auth_tag")

    row = Box(pad=2)
    row.line("one row: ciphertext · iv · auth_tag · wrapped_dek · dek_iv · kek_key_id")
    row.line("a database dump without the KEK yields nothing")

    return stack([kek, dek, ct, row], ["wraps / unwraps", "encrypts", "persisted as"], indent=4)


# --------------------------------------------------------------------------- 07 navigation
def navigation() -> list[str]:
    """A tree, not a connector graph.

    A navigation map answers "how do I get here", which is a tree question. Drawing it as free
    connectors produced a diagram that was correct only by luck; a tree is aligned by construction,
    and both columns are measured from their own content so nothing can overflow.
    """
    rows: list[tuple[int, str, str]] = [
        (0, "Workspace · three panes · /", ""),
        (1, "Model picker (popover, or a sheet below 820)", "chip · ⌘K model · inspector"),
        (2, "Providers and keys · /settings/providers", "\"Manage keys\" · ⌘,"),
        (3, "Add a key · /settings/providers/{kind}/new", "\"Add a key\" on a provider row"),
        (3, "Test connection", "a form button, runs before save"),
        (2, "Inspector pane · ⌘I", "the panel toggle"),
        (3, "Change model", "the same picker, at every width"),
    ]

    def screen(depth: int, text: str) -> str:
        return ("  " * depth) + ("└ " if depth else "") + text

    left = [screen(d, s) for d, s, _ in rows]
    right = [h for _, _, h in rows]
    lw = max(len(s) for s in left) + 2
    rw = max(len(h) for h in right) + 2
    body = ["│" + (" " + s.ljust(lw) + " " + h.ljust(rw) + " ") + "│" for s, h in zip(left, right)]
    w = len(body[0])
    out = [
        "┌" + "─" * (w - 2) + "┐",
        "│" + (" " + "SCREEN".ljust(lw) + " " + "HOW YOU GET THERE".ljust(rw) + " ").ljust(w - 2) + "│",
        "├" + "─" * (w - 2) + "┤",
        *body,
        "└" + "─" * (w - 2) + "┘",
    ]
    out.append("")
    out.append("Three ways into one picker; one way into settings; a back path from every surface.")
    out.append("`esc` always leaves, and focus always returns to the element that opened it.")
    return out


PRODUCERS = {
    "today": today,
    "layers": layers,
    "envelope": envelope,
    "navigation": navigation,
}


def main() -> int:
    check = "--check" in sys.argv
    bad = 0
    for doc in sorted(DOCS.glob("*.md")):
        text = doc.read_text()
        found = GEN.findall(text)
        opens = text.count("<!-- GEN:")
        if opens != len(found):
            bad += 1
            print(f"  {doc.name}: {opens} opening marker(s), {len(found)} well-formed block(s)")
            continue

        def sub(m: re.Match) -> str:
            nonlocal bad
            key = m.group(2)
            if key not in PRODUCERS:
                bad += 1
                print(f"  {doc.name}: unknown diagram {key!r}", file=sys.stderr)
                return m.group(0)
            body = "\n".join(PRODUCERS[key]())
            return f"{m.group(1)}\n\n```text\n{body}\n```\n\n{m.group(3)}"

        new = GEN.sub(sub, text)
        if new != text and not check:
            doc.write_text(new)
            print(f"  {doc.name}: wrote {len(found)} diagram(s)")
        elif found and check:
            print(f"  {doc.name}: {len(found)} diagram(s) ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
