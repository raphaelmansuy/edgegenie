"""Live check of Python sessions against a real workspace. Starts compute; run it on purpose.

    .venv/bin/python tools/kernel_live_check.py

It drives the real service (`KernelSessions`) with the real adapters (Jobs, Files API), as whoever the
Databricks CLI/SDK is signed in as, and checks what the tests cannot: that a variable survives between
cells on real serverless compute, that Stop interrupts a loop, that Restart gives a clean session, and
that when it is over the job has ended and no run is left going. Exit code 0 means all of that held.
"""
from __future__ import annotations

import asyncio
import sys
import time

from api.adapters.databricks.serverless import ServerlessRunner
from api.adapters.databricks.session_store import VolumeStore
from api.services.kernel_service import KernelSessions, Policy

ME = "live-check"
KEY = "/live/check"
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("ok   " if ok else "FAIL ") + name + (f" - {detail}" if detail else ""), flush=True)
    if not ok:
        failures.append(name)


async def finish(svc: KernelSessions, handle: str, timeout: float = 300.0) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        got = await svc.poll(ME, handle)
        if got["state"] == "done":
            return got
        await asyncio.sleep(0.8)
    raise TimeoutError("the cell did not finish")


def text(done: dict) -> str:
    return "".join(o.get("text", "") for o in done["result"].get("outputs", []) if o["type"] == "text")


async def main() -> int:
    runner = ServerlessRunner()
    svc = KernelSessions(runner, VolumeStore(), Policy(idle_seconds=300, lease_seconds=120))
    run_id = None
    try:
        t0 = time.time()
        first = await svc.run(ME, KEY, "python", "x = 41\nprint('set')", index=0)
        check("a session starts", "handle" in first, str(first)[:200])
        if "handle" not in first:
            return 1
        done = await finish(svc, first["handle"])
        check("the first cell runs", done["result"]["state"] == "succeeded", done["result"].get("error", ""))
        print(f"     first result after {time.time() - t0:.1f}s (includes starting compute)")
        sid = first["session"]["id"]

        t1 = time.time()
        second = await svc.run(ME, KEY, "python", "x += 1\nprint(x)", index=1)
        done = await finish(svc, second["handle"])
        trip = time.time() - t1
        check("a variable survives to the next cell", "42" in text(done), text(done))
        check("a warm cell comes back in a few seconds", trip < 10, f"{trip:.1f}s")

        third = await svc.run(ME, KEY, "python", "import time\nprint('tick', flush=True)\nwhile True:\n    time.sleep(0.05)", index=2)
        seen = False
        end = time.time() + 60
        while time.time() < end and not seen:
            got = await svc.poll(ME, third["handle"])
            seen = got["state"] == "running" and any("tick" in o.get("text", "") for o in got.get("outputs", []))
            await asyncio.sleep(0.8)
        check("text printed by a running cell is visible before it ends", seen)
        t2 = time.time()
        await svc.interrupt(ME, third["handle"])
        done = await finish(svc, third["handle"], 60)
        check("Stop interrupts a loop", done["result"]["state"] == "cancelled", f"{time.time() - t2:.1f}s")
        after = await svc.run(ME, KEY, "python", "print(x)", index=3)
        check("the variable is still there after an interrupt", "42" in text(await finish(svc, after["handle"])))

        # -- the magics, widgets and nested values, on the real compute -------------------------------------
        sh = await svc.run(ME, KEY, "shell", "echo from-shell; echo to-stderr 1>&2; python3 --version", index=5)
        done = await finish(svc, sh["handle"])
        check("%sh runs a command and captures both streams", done["result"]["state"] == "succeeded"
              and "from-shell" in text(done) and "to-stderr" in text(done), text(done)[:120])
        bad = await svc.run(ME, KEY, "shell", "exit 7", index=6)
        done = await finish(svc, bad["handle"])
        check("%sh reports a failing exit status", done["result"]["state"] == "failed" and "status 7" in done["result"].get("error", ""))
        pip = await svc.run(ME, KEY, "pip", "install --quiet pyfiglet", index=7)
        done = await finish(svc, pip["handle"])
        check("%pip installs a library", done["result"]["state"] == "succeeded", (done["result"].get("error", "") + text(done))[:160])
        use = await svc.run(ME, KEY, "python", "import pyfiglet\nprint(pyfiglet.__name__)\nprint(x)", index=8)
        done = await finish(svc, use["handle"])
        check("the installed library imports, in the same session as the variable", "pyfiglet" in text(done) and "42" in text(done), text(done)[:120])
        md = await svc.run(ME, KEY, "python", "%md\n# Title", index=9)
        done = await finish(svc, md["handle"])
        check("%md comes back as markdown", any(o["type"] == "markdown" for o in done["result"].get("outputs", [])))

        decl = await svc.run(ME, KEY, "python", "dbutils.widgets.text('city', 'Oslo', 'City')\n"
                             "dbutils.widgets.dropdown('size', 'm', ['s', 'm', 'l'])", index=10)
        done = await finish(svc, decl["handle"])
        names = [w["name"] for w in done["result"].get("widgets", [])]
        check("dbutils.widgets declarations come back with the result", names == ["city", "size"], str(names))
        got = await svc.run(ME, KEY, "python", "print(dbutils.widgets.get('city'), dbutils.widgets.get('size'))", index=11,
                            widgets={"city": "Rome", "size": "l"})
        check("widget values reach the cell", "Rome l" in text(await finish(svc, got["handle"])))
        fs = await svc.run(ME, KEY, "python", "print(type(dbutils.fs).__name__)", index=12)
        done = await finish(svc, fs["handle"])
        check("the rest of dbutils still works next to the widget shim", done["result"]["state"] == "succeeded", text(done) + done["result"].get("error", ""))

        nested = await svc.run(ME, KEY, "python", "display(spark.sql(\"select array(1,2) a, named_struct('x', 1, 'y', 's') s, 3 n\"))", index=13)
        done = await finish(svc, nested["handle"])
        table = next((o for o in done["result"].get("outputs", []) if o["type"] == "table"), {})
        check("a Spark table with nested columns sends rows and type texts",
              table.get("rows") == [["[1,2]", '{"x":1,"y":"s"}', "3"]] and (table.get("typeTexts") or [""])[0].startswith("array"),
              str(table)[:200])

        from api.domain import kernel as kernel_domain, run_magic

        class _Cell:
            def __init__(self, i, language, source):
                self.index, self.language, self.source, self.kind = i, language, source, "code"

        async def expand(notebook, ref):
            async def read(path):
                return [_Cell(0, "python", "from_lib = x * 2"), _Cell(1, "shell", "echo in-lib")]
            return await run_magic.expand(read, notebook, ref)

        run = await svc.run(ME, KEY, "run", "./lib", index=14, expand=expand)
        done = await finish(svc, run["handle"])
        check("%run runs another notebook's cells in this session", done["result"]["state"] == "succeeded" and "in-lib" in text(done), text(done)[:100])
        after_run = await svc.run(ME, KEY, "python", "print(from_lib)", index=15)
        check("what %run defined is there afterwards", "84" in text(await finish(svc, after_run["handle"])))
        slow = await svc.run(ME, KEY, "shell", "sleep 120", index=16)
        await asyncio.sleep(4)
        await svc.interrupt(ME, slow["handle"])
        done = await finish(svc, slow["handle"], 60)
        check("Stop interrupts a %sh command", done["result"]["state"] == "cancelled", done["result"]["state"])

        failing = await svc.run(ME, KEY, "python", "a = 1\nprint(undefined_name)", index=4)
        done = await finish(svc, failing["handle"])
        check("an error says the line", "line 2" in done["result"].get("error", ""), done["result"].get("error", "")[:120])

        sess = svc._sessions[sid]
        run_id = sess.run_id
        await svc.stop(ME, KEY)
        end = time.time() + 90
        life = ""
        while time.time() < end:
            info = await runner.info(run_id)
            life = (info.life_cycle or "").upper()
            if life in {"TERMINATED", "INTERNAL_ERROR", "SKIPPED"}:
                break
            await asyncio.sleep(3)
        check("Stop ends the job", life in {"TERMINATED", "INTERNAL_ERROR", "SKIPPED"}, life)
        fresh = await svc.run(ME, KEY, "python", "print('x' in globals())", index=0)
        replaced = fresh.get("replaced", "")
        done = await finish(svc, fresh["handle"])
        check("Restart gives a clean session", "False" in text(done) and "stopped" in replaced, f"{replaced!r} {text(done)!r}")
        run_id = svc._sessions[fresh["session"]["id"]].run_id
        await svc.stop(ME, KEY)
    finally:
        # Leave nothing running whatever happened above.
        for s in list(svc._sessions.values()):
            try:
                await runner.cancel(s.run_id)
            except Exception:  # noqa: BLE001
                pass
    # Nothing may be left running, whatever the checks did.
    import json
    import subprocess
    time.sleep(5)
    active = subprocess.run(["databricks", "jobs", "list-runs", "--active-only", "-o", "json"], capture_output=True, text=True,
                            env={**__import__("os").environ})
    try:
        runs = json.loads(active.stdout or "[]") or []
    except ValueError:
        runs = []
    mine = [r for r in runs if str(r.get("run_name", "")).startswith("coding-agent")]
    check("no run is left going", not mine, str([r.get("run_id") for r in mine]))
    print("\nall checks passed" if not failures else f"\n{len(failures)} failed: {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
