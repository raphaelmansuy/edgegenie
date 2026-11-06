#!/usr/bin/env python3
"""Capture Databricks UI screenshots for the E2E evidence set.

The workspace uses SSO, so automated login is not possible without credentials.
This script instead supports a saved storage-state file produced by a one-time
manual login (see --login), and captures the pages the spec references.

    python docs/e2e/capture.py --login      # one-time, opens a browser
    python docs/e2e/capture.py              # captures every page
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

HOST = "https://dbc-cb61f1e1-bd8e.cloud.databricks.com"
OUT = Path(__file__).parent / "screenshots"
STATE = Path(__file__).parent / ".storage_state.json"

PAGES = [
    ("01-workspace-home", f"{HOST}/"),
    ("02-genie-code-command-center", f"{HOST}/genie-code"),
    ("03-notebooks-home", f"{HOST}/browse/notebooks"),
    ("04-catalog-explorer", f"{HOST}/explore/data"),
    ("05-sql-editor", f"{HOST}/sql/editor"),
    ("06-compute", f"{HOST}/compute"),
    ("07-jobs", f"{HOST}/jobs"),
    ("08-mcp-marketplace", f"{HOST}/mcp"),
    ("09-settings-compute", f"{HOST}/settings/compute"),
]


async def login() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 1000})
        page = await ctx.new_page()
        await page.goto(HOST)
        print("Log in in the opened window, then press Enter here.")
        await asyncio.get_event_loop().run_in_executor(None, input)
        await ctx.storage_state(path=str(STATE))
        print(f"saved {STATE}")
        await browser.close()


async def capture() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 1600, "height": 1000},
            storage_state=str(STATE) if STATE.exists() else None,
        )
        page = await ctx.new_page()
        for name, url in PAGES:
            try:
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(3000)
                await page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
                print(f"ok   {name}")
            except Exception as exc:  # noqa: BLE001
                print(f"fail {name}: {type(exc).__name__}")
        await browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true")
    a = ap.parse_args()
    asyncio.run(login() if a.login else capture())
