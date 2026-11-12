"""Phase 0 spike: can a serverless job act as a persistent Python session, driven through a volume?

    .venv/bin/python tools/kernel_spike.py            # needs `databricks` auth (the dev profile)

It answers four questions with numbers, then ends the job and removes its files:
  1. how long from submit to the kernel's first heartbeat
  2. the round trip of one command (app writes it, kernel runs it, app reads the result)
  3. whether a variable made by one command is there in the next
  4. whether a running cell can be interrupted, and whether the job then ends when asked

This is a measuring tool, not product code. The product kernel lives in api/domain/kernel.py.
"""
from __future__ import annotations

import io
import json
import statistics
import sys
import time
import uuid

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs, workspace

VOLUME = "/Volumes/workspace/agent_scratch/kernel_sessions"

KERNEL = r'''# Databricks notebook source
import ctypes, json, os, sys, threading, time, traceback, io, contextlib

ROOT = dbutils.widgets.get("root")
os.makedirs(ROOT + "/cmd", exist_ok=True); os.makedirs(ROOT + "/out", exist_ok=True); os.makedirs(ROOT + "/ctl", exist_ok=True)
NS = {"__name__": "__main__"}
main_tid = threading.get_ident()
state = {"busy": False, "seq": 0, "last": time.time()}

def put(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f: json.dump(obj, f)
    os.replace(tmp, path)

def beat():
    while True:
        put(ROOT + "/hb.json", {"t": time.time(), "busy": state["busy"], "seq": state["seq"]})
        if os.path.exists(ROOT + "/ctl/interrupt"):
            try: os.remove(ROOT + "/ctl/interrupt")
            except OSError: pass
            if state["busy"]:
                ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(main_tid), ctypes.py_object(KeyboardInterrupt))
        time.sleep(1.0)

threading.Thread(target=beat, daemon=True).start()
while True:
    if os.path.exists(ROOT + "/ctl/stop") or time.time() - state["last"] > 240:
        break
    nxt = state["seq"] + 1
    p = "%s/cmd/%06d.json" % (ROOT, nxt)
    if not os.path.exists(p):
        time.sleep(0.2); continue
    cmd = json.load(open(p)); state["busy"] = True; state["last"] = time.time()
    t0 = time.time(); out = io.StringIO(); err = None
    try:
        with contextlib.redirect_stdout(out):
            exec(compile(cmd["source"], "<cell>", "exec"), NS)
    except KeyboardInterrupt:
        err = "interrupted"
    except BaseException:
        err = traceback.format_exc(limit=3)
    state["seq"] = nxt; state["busy"] = False; state["last"] = time.time()
    put("%s/out/%06d.json" % (ROOT, nxt), {"stdout": out.getvalue(), "error": err, "ran": time.time() - t0})
dbutils.notebook.exit("stopped")
'''


def main() -> int:
    w = WorkspaceClient()
    me = w.current_user.me().user_name
    sid = uuid.uuid4().hex[:10]
    root = f"{VOLUME}/spike_{sid}"
    nb = f"/Users/{me}/coding_agent_cell_runs/kernel_spike_{sid}"
    w.workspace.mkdirs(f"/Users/{me}/coding_agent_cell_runs")
    w.workspace.upload(nb, io.BytesIO(KERNEL.encode()), format=workspace.ImportFormat.SOURCE,
                       language=workspace.Language.PYTHON, overwrite=True)

    def write(rel, obj):
        w.files.upload(f"{root}/{rel}", io.BytesIO(json.dumps(obj).encode()), overwrite=True)

    def read(rel):
        r = w.files.download(f"{root}/{rel}")
        return json.loads(r.contents.read())

    def exists(rel):
        try:
            w.files.get_metadata(f"{root}/{rel}")
            return True
        except Exception:  # noqa: BLE001
            return False

    report: dict = {"session": sid}
    run_id = None
    try:
        t_submit = time.time()
        waiter = w.jobs.submit(run_name=f"kernel-spike {sid}", timeout_seconds=900, tasks=[jobs.SubmitTask(
            task_key="kernel", notebook_task=jobs.NotebookTask(
                notebook_path=nb, source=jobs.Source.WORKSPACE, base_parameters={"root": root}))])
        run_id = int(getattr(waiter, "response", waiter).run_id)
        print("run", run_id, flush=True)

        # 1. time to the first heartbeat
        while True:
            if exists("hb.json"):
                report["first_heartbeat_s"] = round(time.time() - t_submit, 1)
                break
            if time.time() - t_submit > 600:
                report["error"] = "no heartbeat in 10 minutes"
                return emit(report)
            time.sleep(2)
        print("kernel up", report["first_heartbeat_s"], flush=True)

        def run(seq, source, timeout=60):
            t0 = time.time()
            write(f"cmd/{seq:06d}.json", {"source": source})
            while time.time() - t0 < timeout:
                if exists(f"out/{seq:06d}.json"):
                    res = read(f"out/{seq:06d}.json")
                    return time.time() - t0, res
                time.sleep(0.1)
            return None, None

        # 2 + 3. round trips, and a variable carried across commands
        trips = []
        dt, res = run(1, "x = 41\nprint('set')")
        trips.append(dt)
        dt, res = run(2, "x += 1\nprint(x)")
        trips.append(dt)
        report["variable_carried"] = bool(res and res["stdout"].strip() == "42")
        for i in range(3, 13):
            dt, res = run(i, "pass")
            trips.append(dt)
        ok = [t for t in trips if t]
        report["roundtrip_s"] = {"n": len(ok), "median": round(statistics.median(ok), 2),
                                 "max": round(max(ok), 2)}

        # 4. interrupt a loop that would run for a minute
        write("cmd/000013.json", {"source": "import time\nfor _ in range(600):\n    time.sleep(0.1)\nprint('finished')"})
        time.sleep(3)
        t_int = time.time()
        write("ctl/interrupt", {})
        stopped = None
        while time.time() - t_int < 30:
            if exists("out/000013.json"):
                stopped = read("out/000013.json")
                break
            time.sleep(0.2)
        report["interrupt"] = {"seconds": round(time.time() - t_int, 1) if stopped else None,
                               "result": (stopped or {}).get("error")}

        # a cell that ignores the interrupt: a blocking C call
        write("cmd/000014.json", {"source": "import threading\nthreading.Event().wait(20)\nprint('woke')"})
        time.sleep(2)
        t_int = time.time()
        write("ctl/interrupt", {})
        late = None
        while time.time() - t_int < 40:
            if exists("out/000014.json"):
                late = read("out/000014.json")
                break
            time.sleep(0.5)
        report["interrupt_blocking_call"] = {"seconds": round(time.time() - t_int, 1) if late else None,
                                             "result": (late or {}).get("error") or (late or {}).get("stdout")}

        # end the job on request
        write("ctl/stop", {})
        t_stop = time.time()
        while time.time() - t_stop < 120:
            run_ = w.jobs.get_run(run_id)
            life = getattr(run_.state.life_cycle_state, "value", "")
            if life in {"TERMINATED", "INTERNAL_ERROR", "SKIPPED"}:
                report["ended_after_stop_s"] = round(time.time() - t_stop, 1)
                report["end_state"] = getattr(run_.state.result_state, "value", "")
                break
            time.sleep(2)
        return emit(report)
    finally:
        if run_id is not None:
            try:
                w.jobs.cancel_run(run_id)
            except Exception:  # noqa: BLE001
                pass
        try:
            w.workspace.delete(nb)
        except Exception:  # noqa: BLE001
            pass
        try:
            for e in w.files.list_directory_contents(f"{root}/cmd"):
                w.files.delete(e.path)
            for e in w.files.list_directory_contents(f"{root}/out"):
                w.files.delete(e.path)
        except Exception:  # noqa: BLE001
            pass


def emit(report: dict) -> int:
    print(json.dumps(report, indent=2))
    return 0 if "error" not in report else 1


if __name__ == "__main__":
    sys.exit(main())
