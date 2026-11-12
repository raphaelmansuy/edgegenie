"""The session service against the REAL session code.

The kernel here is not a fake: `InProcessRunner` runs the generated notebook (the very text that goes to
serverless) in a thread, and `LocalStore` is a folder where the volume would be. So these tests exercise
the whole conversation (numbered files, heartbeats, leases, interrupts) and only the network is missing.
The clock the service uses is a variable, so "forty-six seconds without a heartbeat" takes no time.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.domain import kernel, kernel_runtime
from api.services.kernel_service import (
    JOB_CHECK_SECONDS, KEEP_SECONDS, LEASE_RENEW_SECONDS, KernelSessions, Policy, Unavailable)

ME, YOU = "me@example.com", "you@example.com"


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds: float):
        self.t += seconds


class LocalStore:
    """A folder standing in for the volume. Failures can be switched on."""

    def __init__(self):
        self.fail_put = False
        self.frozen: dict[str, dict | None] | None = None
        self.deleted: list[str] = []

    async def put(self, path, doc):
        if self.fail_put:
            raise PermissionError("PERMISSION_DENIED: no WRITE VOLUME on the volume")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        kernel_runtime.put_json(path, doc)

    async def get(self, path):
        if self.frozen is not None:
            # A hung kernel, or a volume that stopped updating: the app sees what it saw first, forever.
            if path not in self.frozen:
                self.frozen[path] = kernel_runtime.get_json(path)
            return self.frozen[path]
        return kernel_runtime.get_json(path)

    async def delete_tree(self, root):
        self.deleted.append(root)
        shutil.rmtree(root, ignore_errors=True)


class InProcessRunner:
    """Runs the generated notebook in a thread, as serverless would run it as a job."""

    def __init__(self, volume: Path, *, start_kernel=True, fail_submit=False):
        self.volume = volume
        self.start_kernel = start_kernel
        self.fail_submit = fail_submit
        self.submitted: list[dict] = []
        self.cancelled: list[int] = []
        self.discarded: list[str] = []
        self.threads: dict[int, threading.Thread] = {}
        self.roots: dict[int, str] = {}
        self.crashed: set[int] = set()
        self.exits: dict[int, str] = {}

    async def submit(self, name, source, *, timeout_seconds=None):
        if self.fail_submit:
            raise RuntimeError("QUOTA_EXCEEDED: no more serverless compute for this workspace")
        run_id = 1000 + len(self.submitted)
        sid = name.removeprefix("session_")
        self.submitted.append({"name": name, "timeout": timeout_seconds, "source": source})
        self.roots[run_id] = f"{self.volume}/{sid}"
        if self.start_kernel:
            def job():
                ns = {"dbutils": SimpleNamespace(notebook=SimpleNamespace(
                    exit=lambda reason, run_id=run_id: self.exits.__setitem__(run_id, reason))), "spark": object()}
                exec(compile(source, "<kernel>", "exec"), ns)

            t = threading.Thread(target=job, daemon=True)
            self.threads[run_id] = t
            t.start()
        return run_id, f"/Users/x/{name}"

    async def info(self, run_id):
        if run_id in self.crashed:
            return SimpleNamespace(life_cycle="INTERNAL_ERROR", result_state="FAILED", message="Cluster was lost",
                                   task_run_id=None)
        t = self.threads.get(run_id)
        alive = True if t is None else t.is_alive()
        return SimpleNamespace(life_cycle="RUNNING" if alive else "TERMINATED", result_state="" if alive else "SUCCESS",
                               message="", task_run_id=run_id)

    async def output(self, task_run_id):
        return self.exits.get(task_run_id), ""

    async def cancel(self, run_id):
        self.cancelled.append(run_id)
        stop = self.roots[run_id] + "/ctl/stop"
        os.makedirs(os.path.dirname(stop), exist_ok=True)
        kernel_runtime.put_json(stop, {})

    async def discard(self, path):
        self.discarded.append(path)


class World:
    def __init__(self, tmp_path: Path, **policy):
        self.volume = tmp_path / "vol"
        self.volume.mkdir()
        self.clock = Clock()
        self.store = LocalStore()
        self.runner = InProcessRunner(self.volume)
        defaults = dict(volume=str(self.volume), idle_seconds=60, lease_seconds=60, interrupt_grace=10,
                        max_per_user=2, max_total=3)
        defaults.update(policy)
        self.policy = Policy(**defaults)
        self.svc = KernelSessions(self.runner, self.store, self.policy, clock=self.clock,
                                  wall=lambda: "2026-11-12T10:00:00+00:00")

    def stop_all(self):
        for root in self.runner.roots.values():
            p = Path(root) / "ctl"
            p.mkdir(parents=True, exist_ok=True)
            kernel_runtime.put_json(str(p / "stop"), {})
        for t in self.runner.threads.values():
            t.join(10)

    async def finish(self, owner: str, handle: str, timeout: float = 15.0) -> dict:
        end = time.time() + timeout
        while time.time() < end:
            got = await self.svc.poll(owner, handle)
            if got["state"] == "done":
                return got
            await asyncio.sleep(0.03)
        raise AssertionError(f"never finished; last: {got}")

    async def run(self, source: str, *, owner: str = ME, key: str = "/nb/a", language: str = "python") -> dict:
        started = await self.svc.run(owner, key, language, source)
        assert "handle" in started, started
        return await self.finish(owner, started["handle"])


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    yield w
    w.stop_all()


def go(coro):
    return asyncio.run(coro)


def text(done: dict) -> str:
    return "".join(o["text"] for o in done["result"].get("outputs", []) if o["type"] == "text")


# -- the point ----------------------------------------------------------------------------------


def test_a_cell_runs_in_a_session_and_the_result_says_who_and_where(world):
    done = go(world.run("print('hi')\n2 + 2"))
    r = done["result"]
    assert r["state"] == "succeeded" and "hi" in text(done) and "4" in text(done)
    assert r["warehouse"] == kernel.WHERE and r["ranBy"] == ME and r["finishedAt"]


def test_a_variable_made_by_one_run_is_there_in_the_next(world):
    async def main():
        await world.run("x = 41")
        return await world.run("print(x + 1)")

    assert "42" in text(go(main()))


def test_one_session_is_reused_for_a_notebook_and_the_job_is_bounded(world):
    async def main():
        await world.run("a = 1")
        await world.run("b = 2")

    go(main())
    assert len(world.runner.submitted) == 1
    assert world.runner.submitted[0]["timeout"] == world.policy.max_session_seconds


def test_a_cell_that_cannot_run_as_python_is_refused_and_starts_nothing(world):
    async def main():
        return [await world.svc.run(ME, "/nb/a", "sql", "select 1"), await world.svc.run(ME, "/nb/a", "python", "  ")]

    sql, empty = go(main())
    assert sql["refused"]["state"] == "refused" and empty["refused"]["state"] == "refused"
    assert world.runner.submitted == []


def test_text_so_far_comes_back_while_the_cell_runs(world):
    async def main():
        started = await world.svc.run(ME, "/nb/a", "python", "import time\nprint('early', flush=True)\ntime.sleep(2.5)")
        end = time.time() + 12
        while time.time() < end:
            got = await world.svc.poll(ME, started["handle"])
            if got["state"] == "running" and any("early" in o.get("text", "") for o in got["outputs"]):
                await world.finish(ME, started["handle"])
                return got
            await asyncio.sleep(0.05)
        raise AssertionError("no progress seen")

    assert go(main())["stage"] == "running your cell"


# -- who owns what ------------------------------------------------------------------------------


def test_another_users_handle_is_not_found(world):
    async def main():
        started = await world.svc.run(ME, "/nb/a", "python", "1")
        with pytest.raises(LookupError):
            await world.svc.poll(YOU, started["handle"])
        with pytest.raises(LookupError):
            await world.svc.interrupt(YOU, started["handle"])
        with pytest.raises(LookupError):
            await world.svc.poll(ME, "guessed")
        await world.finish(ME, started["handle"])

    go(main())


def test_two_users_do_not_share_a_namespace(world):
    async def main():
        await world.run("secret = 'mine'", owner=ME)
        return await world.run("print(secret)", owner=YOU)

    done = go(main())
    assert done["result"]["state"] == "failed" and "NameError" in done["result"]["error"]


# -- limits -------------------------------------------------------------------------------------


def test_a_user_cannot_hold_more_sessions_than_the_limit(world):
    async def main():
        await world.run("1", key="/nb/a")
        await world.run("1", key="/nb/b")
        with pytest.raises(Unavailable, match="already have 2"):
            await world.svc.run(ME, "/nb/c", "python", "1")

    go(main())


def test_the_app_cannot_hold_more_sessions_than_the_total(tmp_path):
    w = World(tmp_path, max_per_user=5, max_total=2)
    try:
        async def main():
            await w.run("1", owner=ME, key="/nb/a")
            await w.run("1", owner=YOU, key="/nb/a")
            with pytest.raises(Unavailable, match="as many Python sessions"):
                await w.svc.run("third@example.com", "/nb/a", "python", "1")

        go(main())
    finally:
        w.stop_all()


# -- cannot start -------------------------------------------------------------------------------


def test_an_unwritable_store_is_reported_before_any_compute_is_started(world):
    world.store.fail_put = True
    with pytest.raises(Unavailable, match="could not be written.*read and write"):
        go(world.svc.run(ME, "/nb/a", "python", "1"))
    assert world.runner.submitted == []


def test_a_failed_job_start_is_reported_and_leaves_no_files(world):
    world.runner.fail_submit = True
    with pytest.raises(Unavailable, match="QUOTA_EXCEEDED"):
        go(world.svc.run(ME, "/nb/a", "python", "1"))
    assert world.store.deleted and not any(world.volume.iterdir())


def test_a_session_that_never_starts_ends_with_a_reason_and_is_cancelled(tmp_path):
    w = World(tmp_path)
    w.runner.start_kernel = False                      # the job is "running" but nothing ever answers

    async def main():
        started = await w.svc.run(ME, "/nb/a", "python", "1")
        got = await w.svc.poll(ME, started["handle"])
        assert got["state"] == "running" and got["stage"] == "starting serverless compute"
        w.clock.advance(w.policy.start_timeout + 1)
        return await w.svc.poll(ME, started["handle"])

    done = go(main())
    assert done["state"] == "done" and done["result"]["state"] == "failed"
    assert "did not start" in done["result"]["error"] and w.runner.cancelled


# -- a session that dies ------------------------------------------------------------------------


def test_a_session_that_dies_mid_cell_ends_that_cell_in_words_and_the_next_cell_starts_fresh(world):
    async def main():
        await world.run("kept = 1")
        started = await world.svc.run(ME, "/nb/a", "python", "import time\ntime.sleep(30)")
        await asyncio.sleep(0.4)
        world.runner.crashed.add(1000)                 # the platform loses the compute
        world.clock.advance(JOB_CHECK_SECONDS + 1)
        dead = await world.finish(ME, started["handle"])
        again = await world.svc.run(ME, "/nb/a", "python", "print(kept)")
        gone = await world.finish(ME, again["handle"])
        return dead, again, gone

    dead, again, gone = go(main())
    err = dead["result"]["error"]
    assert dead["result"]["state"] == "failed" and "Cluster was lost" in err and "variables from earlier cells are gone" in err
    assert "Cluster was lost" in again["replaced"]      # the client is told this is a new session
    assert "NameError" in gone["result"]["error"]       # and it really is: the variable did not survive


def test_a_session_that_stops_reporting_is_ended(world):
    async def main():
        await world.run("1")
        # From now on the app sees the same heartbeat forever: the kernel is hung, or the volume is stale.
        world.store.frozen = {}
        started = await world.svc.run(ME, "/nb/a", "python", "import time\ntime.sleep(5)")
        world.clock.advance(4)                       # past the pause between heartbeat reads
        await world.svc.poll(ME, started["handle"])  # the app takes in the frozen heartbeat here
        world.clock.advance(world.policy.heartbeat_stale + 5)
        return await world.finish(ME, started["handle"])

    done = go(main())
    assert "stopped responding" in done["result"]["error"] and world.runner.cancelled


def test_an_idle_session_is_reported_ended_and_the_next_cell_replaces_it(tmp_path):
    w = World(tmp_path, idle_seconds=0.5)
    try:
        async def main():
            await w.run("v = 1")
            time.sleep(1.5)
            w.clock.advance(5)
            status = await w.svc.status(ME, "/nb/a")
            again = await w.svc.run(ME, "/nb/a", "python", "1")
            await w.finish(ME, again["handle"])
            return status, again

        status, again = go(main())
        assert status["state"] == "ended" and "idle" in status["reason"]
        assert "idle" in again["replaced"] and len(w.runner.submitted) == 2
    finally:
        w.stop_all()


# -- stopping a cell, and the session -------------------------------------------------------------


def test_interrupt_cancels_the_cell_and_keeps_the_session(world):
    async def main():
        await world.run("kept = 'here'")
        started = await world.svc.run(ME, "/nb/a", "python", "import time\nwhile True:\n    time.sleep(0.01)")
        await asyncio.sleep(0.5)
        await world.svc.interrupt(ME, started["handle"])
        stopped = await world.finish(ME, started["handle"])
        after = await world.run("print(kept)")
        return stopped, after

    stopped, after = go(main())
    assert stopped["result"]["state"] == "cancelled" and "here" in text(after)
    assert len(world.runner.submitted) == 1


def test_a_cell_that_ignores_the_interrupt_ends_the_session_after_the_grace(world):
    async def main():
        started = await world.svc.run(ME, "/nb/a", "python", "import threading\nthreading.Event().wait(4)")
        await asyncio.sleep(0.5)
        await world.svc.interrupt(ME, started["handle"])
        world.clock.advance(world.policy.interrupt_grace + 1)
        return await world.finish(ME, started["handle"])

    done = go(main())
    assert done["result"]["state"] in {"failed", "cancelled"}
    assert world.runner.cancelled, "a session stuck in a cell that will not stop must be ended"


def test_stop_ends_the_session_and_the_next_cell_gets_a_new_one(world):
    async def main():
        await world.run("v = 1")
        stopped = await world.svc.stop(ME, "/nb/a")
        again = await world.run("print('v' in globals())")
        return stopped, again

    stopped, again = go(main())
    assert stopped["state"] == "stopping" and "False" in text(again)
    assert len(world.runner.submitted) == 2


def test_status_before_any_run_is_none_and_does_not_start_anything(world):
    assert go(world.svc.status(ME, "/nb/a")) == {"state": "none"}
    assert world.runner.submitted == []


def test_status_shows_busy_then_idle(world):
    async def main():
        started = await world.svc.run(ME, "/nb/a", "python", "import time\ntime.sleep(1.5)")
        busy = await world.svc.status(ME, "/nb/a")
        await world.finish(ME, started["handle"])
        idle = await world.svc.status(ME, "/nb/a")
        return busy, idle

    busy, idle = go(main())
    assert busy["state"] in {"starting", "busy"} and idle["state"] == "idle"


# -- the lease ----------------------------------------------------------------------------------


def test_the_lease_is_renewed_while_the_app_is_in_use_and_not_more_often_than_needed(world):
    async def main():
        await world.run("1")
        lease = f"{world.runner.roots[1000]}/ctl/lease.json"
        first = kernel_runtime.get_json(lease)["n"]
        await world.svc.status(ME, "/nb/a")
        same = kernel_runtime.get_json(lease)["n"]
        world.clock.advance(LEASE_RENEW_SECONDS + 1)
        await world.svc.status(ME, "/nb/a")
        return first, same, kernel_runtime.get_json(lease)["n"]

    first, same, later = go(main())
    assert same == first and later == first + 1


def test_a_session_whose_app_went_away_ends_by_its_lease(tmp_path):
    w = World(tmp_path, lease_seconds=0.6)
    try:
        go(w.run("1"))
        # The app "restarts": a new service knows nothing of the session and renews nothing.
        fresh = KernelSessions(w.runner, w.store, w.policy, clock=w.clock)
        w.runner.threads[1000].join(8)
        assert not w.runner.threads[1000].is_alive(), "an orphaned session kept running"
        assert w.runner.exits[1000] == "lease"
        with pytest.raises(LookupError):
            go(fresh.poll(ME, "a-handle-from-before-the-restart"))
    finally:
        w.stop_all()


# -- housekeeping -------------------------------------------------------------------------------


def test_an_ended_sessions_files_are_removed_after_a_while(world):
    async def main():
        await world.run("1")
        await world.svc.stop(ME, "/nb/a")
        world.runner.threads[1000].join(10)
        world.clock.advance(5)
        await world.svc.status(ME, "/nb/a")             # notices the end
        world.clock.advance(KEEP_SECONDS + 1)
        await world.svc.status(ME, "/nb/b")             # any call does the housekeeping

    go(main())
    assert world.store.deleted and not (world.volume / Path(world.runner.roots[1000]).name).exists()
    assert world.runner.discarded, "the session notebook was not removed from the workspace"


def test_a_result_for_another_command_is_not_accepted(world):
    async def main():
        await world.run("1")
        second = await world.svc.run(ME, "/nb/a", "python", "import time\ntime.sleep(1.5)\nprint('real')")
        out = f"{world.runner.roots[1000]}/out/000002.json"
        planted = {"protocol": 1, "final": True, "ok": True, "id": "somebody-else", "outputs": [
            {"type": "text", "stream": "stdout", "text": "planted"}]}
        kernel_runtime.put_json(out, planted)
        early = await world.svc.poll(ME, second["handle"])
        done = await world.finish(ME, second["handle"])
        return early, done

    early, done = go(main())
    assert early["state"] == "running"
    assert "planted" not in json.dumps(done) and "real" in text(done)


# -- the routes ---------------------------------------------------------------------------------

from fastapi.testclient import TestClient

from api.config import Settings
from api.main import build

ADMIN = "boss@example.com"


def api(admins=ADMIN, **kw) -> TestClient:
    cfg = Settings(agent_mode="fake", demo_scenario="notebook", dev_user=ADMIN, llm_demo_seed=True,
                   allowed_models=["fake/model-a"], default_model="fake/model-a", llm_admins=admins, **kw)
    return TestClient(build(cfg))


def wait_done(c: TestClient, handle: str, timeout: float = 15.0) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        got = c.get(f"/api/notebook/kernels/runs/{handle}").json()
        if got["state"] == "done":
            return got
        time.sleep(0.05)
    raise AssertionError(f"never finished: {got}")


def test_the_routes_run_a_cell_in_a_session_end_to_end(tmp_path):
    w = World(tmp_path)
    try:
        with api() as c:
            c.app.state.kernels = w.svc
            assert c.get("/api/me").json()["pythonRun"]["session"] is True
            body = {"path": "/Users/x/nb", "language": "python", "source": "n = 20", "index": 0}
            h1 = c.post("/api/notebook/kernels/run", json=body).json()["handle"]
            assert wait_done(c, h1)["result"]["state"] == "succeeded"
            h2 = c.post("/api/notebook/kernels/run", json={**body, "source": "print(n + 1)", "index": 1}).json()["handle"]
            done = wait_done(c, h2)
            assert "21" in text(done)
            assert c.get("/api/notebook/kernels", params={"path": "/Users/x/nb"}).json()["state"] == "idle"
            assert c.delete("/api/notebook/kernels", params={"path": "/Users/x/nb"}).json()["state"] == "stopping"
            assert c.get("/api/notebook/kernels/runs/unknown").status_code == 404
    finally:
        w.stop_all()


def test_a_non_administrator_cannot_use_sessions(tmp_path):
    w = World(tmp_path)
    with api(admins="someone-else@example.com") as c:
        c.app.state.kernels = w.svc
        r = c.post("/api/notebook/kernels/run", json={"path": "/x", "source": "1"})
        assert r.status_code == 403 and "not as you" in r.text
        assert c.get("/api/notebook/kernels", params={"path": "/x"}).status_code == 403
    assert w.runner.submitted == []


def test_a_session_that_cannot_start_is_a_fallback_not_an_error(tmp_path):
    w = World(tmp_path)
    w.store.fail_put = True
    with api() as c:
        c.app.state.kernels = w.svc
        r = c.post("/api/notebook/kernels/run", json={"path": "/x", "source": "1"})
        assert r.status_code == 200 and "read and write" in r.json()["unavailable"]


def test_the_owner_can_switch_sessions_off_and_one_shot_runs_remain(tmp_path):
    w = World(tmp_path)
    with api(python_session="off") as c:
        c.app.state.kernels = w.svc
        me = c.get("/api/me").json()["pythonRun"]
        assert me["enabled"] is True and me["session"] is False
        r = c.post("/api/notebook/kernels/run", json={"path": "/x", "source": "1"})
        assert "switched off" in r.json()["unavailable"]
        assert c.get("/api/notebook/kernels", params={"path": "/x"}).json() == {"state": "off"}
    assert w.runner.submitted == []


# -- %run through the route: the app reads the other notebook, as the user ------------------------

class FakeWorkspace:
    """What `%run` reads. It records the token each read was made with."""

    def __init__(self, notebooks):
        self.notebooks, self.tokens, self.paths = notebooks, [], []

    async def read(self, path, token):
        from types import SimpleNamespace
        self.tokens.append(token)
        self.paths.append(path)
        if path not in self.notebooks:
            raise LookupError("it does not exist")
        if isinstance(self.notebooks[path], Exception):
            raise self.notebooks[path]
        cells = [SimpleNamespace(index=i, language=lang, source=src, kind="code", truncated=False)
                 for i, (lang, src) in enumerate(self.notebooks[path])]
        return SimpleNamespace(kind="notebook", truncated=False, cells=cells)


def test_run_brings_another_notebooks_cells_into_the_session_using_the_users_token(tmp_path):
    w = World(tmp_path)
    ws = FakeWorkspace({"/Users/x/lib": [("python", "LIB = 5"), ("shell", "echo from lib")]})
    try:
        with api() as c:
            c.app.state.kernels = w.svc
            c.app.state.workspace = ws
            body = {"path": "/Users/x/nb", "language": "python", "index": 0}
            r = c.post("/api/notebook/kernels/run", json={**body, "language": "run", "source": "./lib"},
                       headers={"x-forwarded-access-token": "user-token-1"}).json()
            done = wait_done(c, r["handle"])
            assert done["result"]["state"] == "succeeded" and "from lib" in text(done)
            assert ws.tokens == ["user-token-1"] and ws.paths == ["/Users/x/lib"]
            h = c.post("/api/notebook/kernels/run", json={**body, "source": "print(LIB + 1)", "index": 1}).json()["handle"]
            assert "6" in text(wait_done(c, h))
    finally:
        w.stop_all()


@pytest.mark.parametrize("notebooks,source,words", [
    ({}, "./gone", "no notebook at /Users/x/gone"),
    ({"/Users/x/lib": PermissionError("no access")}, "./lib", "you cannot read /Users/x/lib"),
    ({"/Users/x/lib": [("python", "x=1")]}, "./lib $a=1", "no arguments"),
    ({"/Users/x/a": [("run", "./a")]}, "./a", "circle"),
])
def test_run_that_cannot_be_done_is_refused_and_starts_no_compute(tmp_path, notebooks, source, words):
    w = World(tmp_path)
    try:
        with api() as c:
            c.app.state.kernels = w.svc
            c.app.state.workspace = FakeWorkspace(notebooks)
            got = c.post("/api/notebook/kernels/run",
                         json={"path": "/Users/x/nb", "language": "python", "source": f"%run {source}"}).json()
            assert got["refused"]["state"] == "refused" and words in got["refused"]["error"]
            assert "handle" not in got
            assert c.get("/api/notebook/kernels", params={"path": "/Users/x/nb"}).json()["state"] == "none"
    finally:
        w.stop_all()


def test_widget_values_travel_with_the_cell_and_the_declarations_come_back(tmp_path):
    w = World(tmp_path)
    try:
        with api() as c:
            c.app.state.kernels = w.svc
            body = {"path": "/Users/x/nb", "language": "python", "index": 0}
            decl = c.post("/api/notebook/kernels/run", json={**body, "source": "dbutils.widgets.text('city', 'Oslo')"}).json()["handle"]
            got = wait_done(c, decl)["result"]
            assert [x["name"] for x in got["widgets"]] == ["city"] and got["widgets"][0]["value"] == "Oslo"
            h = c.post("/api/notebook/kernels/run", json={**body, "source": "print(dbutils.widgets.get('city'))",
                                                          "widgets": {"city": "Rome"}}).json()["handle"]
            assert "Rome" in text(wait_done(c, h))
            bad = c.post("/api/notebook/kernels/run", json={**body, "source": "1", "widgets": {"a": "x" * 2001}})
            assert bad.status_code == 422
    finally:
        w.stop_all()


def test_a_session_result_with_no_widgets_key_says_nothing_about_them_and_a_hostile_one_is_cleaned():
    from api.domain import kernel

    assert kernel.result_of({"ok": True, "outputs": []}, 1.0).widgets is None
    assert kernel.result_of({"ok": True, "outputs": []}, 1.0).to_dict().get("widgets") is None
    got = kernel.result_of({"ok": True, "outputs": [], "widgets": [
        {"name": "ok", "type": "text", "default": "d", "label": "L", "choices": ["a", 3], "value": "v"},
        {"name": "bad type", "type": "slider", "default": "d"}, {"name": "", "type": "text", "default": "d"},
        {"name": "n" * 65, "type": "text", "default": "d"}, "nope", {"name": "x", "type": "text", "default": 5}]}, 1.0)
    assert got.widgets == [{"name": "ok", "type": "text", "default": "d", "label": "L", "choices": ["a"], "value": "v"}]
    assert kernel.result_of({"ok": True, "outputs": [], "widgets": []}, 1.0).to_dict()["widgets"] == []
    assert kernel.result_of({"ok": True, "outputs": [], "widgets": "junk"}, 1.0).widgets == []
