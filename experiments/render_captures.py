#!/usr/bin/env python3
"""Turn the saved notebook-cell captures into PNG "screenshots" (cell code on top, real output below).

    python experiments/render_captures.py [--captures docs/tutorial/captures.json] [--out docs/e2e/screenshots/tutorial]

These images are renderings of REAL output text, not photographs of the Databricks web page. Before drawing, the
text is scrubbed: tokens, the workspace address and the account email are replaced by placeholders.
"""
from __future__ import annotations

import asyncio
import html
import json
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "exams"))
import lib  # noqa: E402

ARGS = sys.argv[1:]
CAP = Path(ARGS[ARGS.index("--captures") + 1]) if "--captures" in ARGS else ROOT / "docs" / "tutorial" / "captures.json"
OUT = Path(ARGS[ARGS.index("--out") + 1]) if "--out" in ARGS else ROOT / "docs" / "e2e" / "screenshots" / "tutorial"

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def scrub(t: str) -> str:
    t = ANSI.sub("", t)
    t = t.replace(lib.TOKEN, "dapi********")
    t = re.sub(r"dapi[0-9a-f]{20,}", "dapi********", t)
    t = t.replace(lib.HOST, "https://YOUR-WORKSPACE.cloud.databricks.com").replace(lib.HOST.replace("https://", ""), "YOUR-WORKSPACE.cloud.databricks.com")
    t = t.replace(lib.USER, "you@example.com").replace(lib.USER.split("@")[0], "you")
    return t


PAGE = """<html><body style="margin:0;background:#F4F1FA;padding:28px;font-family:-apple-system,Segoe UI,sans-serif">
<div id="win" style="width:1180px;border-radius:12px;overflow:hidden;box-shadow:0 8px 28px rgba(80,60,120,.18);border:1px solid #D9D2EA;background:#fff">
 <div style="background:#E8F0FE;border-bottom:1px solid #C9D7F0;padding:10px 16px;display:flex;align-items:center;gap:8px">
  <span style="width:12px;height:12px;border-radius:6px;background:#F2B5CB"></span><span style="width:12px;height:12px;border-radius:6px;background:#F2D98D"></span><span style="width:12px;height:12px;border-radius:6px;background:#A8D5B5"></span>
  <span style="margin-left:12px;font-size:14px;color:#374151;font-weight:600">__TITLE__</span>
  <span style="margin-left:auto;font-size:12px;color:#6B7280">__META__</span></div>
 <div style="background:#FFFDF5;border-bottom:1px solid #EFE7C8;padding:14px 18px"><div style="font:11px sans-serif;color:#9A8F5F;letter-spacing:.06em;margin-bottom:6px">NOTEBOOK CELL (what you run)</div>
  <pre style="margin:0;font:13px/1.5 ui-monospace,Menlo,monospace;color:#1F2937;white-space:pre-wrap;word-break:break-word">__CODE__</pre></div>
 <div style="background:#1F2430;padding:14px 18px"><div style="font:11px sans-serif;color:#8B93A7;letter-spacing:.06em;margin-bottom:6px">OUTPUT (real, captured)</div>
  <pre style="margin:0;font:13px/1.5 ui-monospace,Menlo,monospace;color:#E6EAF2;white-space:pre-wrap;word-break:break-word">__OUT__</pre></div>
</div></body></html>"""


TERM = """<html><body style="margin:0;background:#F4F1FA;padding:28px;font-family:-apple-system,Segoe UI,sans-serif">
<div id="win" style="width:1180px;border-radius:12px;overflow:hidden;box-shadow:0 8px 28px rgba(80,60,120,.18);border:1px solid #D9D2EA;background:#fff">
 <div style="background:#E8DCF7;border-bottom:1px solid #D3C2EC;padding:10px 16px;display:flex;align-items:center;gap:8px">
  <span style="width:12px;height:12px;border-radius:6px;background:#F2B5CB"></span><span style="width:12px;height:12px;border-radius:6px;background:#F2D98D"></span><span style="width:12px;height:12px;border-radius:6px;background:#A8D5B5"></span>
  <span style="margin-left:12px;font-size:14px;color:#374151;font-weight:600">__TITLE__</span>
  <span style="margin-left:auto;font-size:12px;color:#6B7280">sandbox shell · __META__</span></div>
 <div style="background:#1B2130;padding:16px 18px"><div style="font:11px sans-serif;color:#8B93A7;letter-spacing:.06em;margin-bottom:8px">WHAT YOU TYPE AND WHAT CAME BACK</div>
  <pre style="margin:0;font:13px/1.55 ui-monospace,Menlo,monospace;color:#E6EAF2;white-space:pre-wrap;word-break:break-word">__BODY__</pre></div>
</div></body></html>"""


def colour(out: str) -> str:
    out = html.escape(out)
    out = re.sub(r"(READY[^\n]*|signed in as [^\n]*|tool server is up|\[\d/\d\][^\n]*)", r'<span style="color:#A8D5B5">\1</span>', out)
    out = re.sub(r"(=== FINAL ANSWER ===|--- the agent made[^\n]*)", r'<span style="color:#F2D98D;font-weight:600">\1</span>', out)
    out = re.sub(r"(ERROR[^\n]*|Error[^\n]*|not allowed[^\n]*|refus[^\n]*)", r'<span style="color:#F2B5CB">\1</span>', out)
    return out


async def main() -> None:
    caps = json.loads(CAP.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1260, "height": 900}, device_scale_factor=2)
        for i, c in enumerate(caps, 1):
            code = scrub(c["code"]).strip()
            code = "\n".join(l for l in code.splitlines() if "put_tree(sandbox_id" not in l or True)
            out = scrub(c["output"]).strip() or "(no output)"
            lines = out.splitlines()
            if len(lines) > 70:                      # keep screenshots readable
                out = "\n".join(lines[:12] + ["... (middle trimmed) ..."] + lines[-55:])
            doc = (PAGE.replace("__TITLE__", html.escape(c["heading"] or f"Cell {i}")).replace("__META__", f"{c['seconds']} s")
                   .replace("__CODE__", html.escape(code)).replace("__OUT__", colour(out)))
            await pg.set_content(doc)
            el = await pg.query_selector("#win")
            name = re.sub(r"[^a-z0-9]+", "-", (c["heading"] or f"cell-{i}").lower()).strip("-")[:40]
            f = OUT / f"{i:02d}-{name}.png"
            await el.screenshot(path=str(f))
            print("wrote", f.relative_to(ROOT))
        await b.close()


async def terminals() -> None:
    """Shell captures: command lines in green, real output below, terminal window chrome."""
    caps = json.loads(CAP.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1260, "height": 900}, device_scale_factor=2)
        for i, c in enumerate(caps, 1):
            parts = []
            for line in c["command"].splitlines():
                parts.append(f'<span style="color:#A8D5B5">$ {html.escape(scrub(line))}</span>')
            body = "\n".join(parts) + "\n" + colour(scrub(c["output"]))
            doc = (TERM.replace("__TITLE__", html.escape(c["title"])).replace("__META__", c["seconds"])
                   .replace("__BODY__", body))
            await pg.set_content(doc)
            el = await pg.query_selector("#win")
            name = re.sub(r"[^a-z0-9]+", "-", c["title"].lower()).strip("-")[:40]
            f = OUT / f"shell-{i:02d}-{name}.png"
            await el.screenshot(path=str(f))
            print("wrote", f.relative_to(ROOT))
        await b.close()


if __name__ == "__main__":
    if "--terminal" in ARGS:
        asyncio.run(terminals())
    else:
        asyncio.run(main())
