"""Python cells on serverless compute: the plan, the generated notebook, the run's life, who may ask.

The generated wrapper is executed here for real (with a stand-in `dbutils`), because it is the one piece
of code that only ever runs on a cluster: if it were wrong, the first sign would be a failed run in
production.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.domain import pyrun
from api.domain.cellrun import RunState
from api.main import build
from api.services.pyrun_service import PythonRuns

ADMIN = "boss@example.com"


def cells(*pairs: tuple[str, str]) -> list[pyrun.PyCell]:
    return [pyrun.PyCell(i, lang, src) for i, (lang, src) in enumerate(pairs)]


def run_wrapper(p: pyrun.Plan) -> dict:
    """Execute the generated notebook the way a cluster would, and return what it exits with."""
    exited: list[str] = []
    ns = {"dbutils": SimpleNamespace(notebook=SimpleNamespace(exit=exited.append)), "__name__": "wrapper"}
    exec(compile(pyrun.wrapper_notebook(p), "<wrapper>", "exec"), ns)
    return json.loads(exited[0])


# -- the plan ------------------------------------------------------------------------------------
def test_python_cells_run_and_other_engines_do_not():
    assert pyrun.python_source("python", "x = 1")[0] == "x = 1"
    assert pyrun.python_source("sql", "select 1")[0] is None
    assert pyrun.python_source("sql", "%python\nprint(1)")[0] == "print(1)"
    body, why = pyrun.python_source("python", "%sql\nselect 1")
    assert body is None and "SQL warehouse" in why
    body, why = pyrun.python_source("python", "%pip install x")
    assert body is None and "%pip" in why
    assert pyrun.python_source("python", "  \n")[1] == "this cell is empty"


def test_running_one_cell_also_runs_the_python_above_it_but_shows_only_that_one():
    nb = cells(("python", "a = 1"), ("sql", "select 1"), ("python", "b = a + 1"), ("python", "c = b"))
    p = pyrun.plan(nb, upto=2, show={2})
    assert [i for i, _ in p.steps] == [0, 2]          # the SQL cell is another engine's; cell 3 is below
    assert p.show == frozenset({2})


def test_a_skip_cell_is_left_out_of_a_batch_and_run_when_asked_for():
    nb = cells(("python", "a = 1"), ("python", "%skip\nb = 2"), ("python", "c = 3"))
    batch = pyrun.plan(nb, upto=2, show=None)
    assert [i for i, _ in batch.steps] == [0, 2]
    alone = pyrun.plan(nb, upto=1, show={1})
    assert [i for i, _ in alone.steps] == [0, 1]
    assert alone.steps[1][1].strip() == "b = 2"


def test_a_requested_cell_that_cannot_run_is_refused_with_its_reason():
    nb = cells(("python", "a = 1"), ("python", "%pip install x"))
    p = pyrun.plan(nb, upto=1, show={1})
    assert 1 in p.refused and not p.show


# -- the generated notebook, executed ------------------------------------------------------------
def test_cells_share_variables_and_report_stdout_and_the_last_expression():
    nb = cells(("python", "a = 20"), ("python", "print('hello')\nb = a + 1\nb * 2"))
    out = run_wrapper(pyrun.plan(nb, upto=1, show={1}))
    first, second = out["cells"]
    assert first == {"i": 0, "ok": True}                   # ran, but its output was not asked for
    assert second["stdout"] == "hello\n" and second["value"] == "42"


def test_an_error_stops_the_run_and_shows_the_cell_not_the_wrapper():
    nb = cells(("python", "x = 1"), ("python", "print(undefined_name)"), ("python", "y = 2"))
    out = run_wrapper(pyrun.plan(nb, upto=2, show=None))
    assert [c["i"] for c in out["cells"]] == [0, 1]        # cell 3 never ran
    err = out["cells"][1]["error"]
    assert "NameError" in err and "cell 2" in err and "wrapper" not in err


def test_user_code_cannot_break_out_of_the_string_it_travels_in():
    nasty = "print('\"\"\"; import os; print(\"pwned\") #')\n'''"
    nb = cells(("python", "print('''\"\"\" and ''' + \"'\" * 3)"), ("python", "print(1)"))
    out = run_wrapper(pyrun.plan(nb, upto=1, show=None))
    assert out["cells"][1]["stdout"] == "1\n"
    assert nasty not in pyrun.wrapper_notebook(pyrun.plan(nb, upto=1, show=None))  # it is data, not source


def test_a_chatty_cell_is_clipped_not_returned_whole():
    nb = cells(("python", "print('x' * 100000)"))
    out = run_wrapper(pyrun.plan(nb, upto=0, show=None))
    assert len(out["cells"][0]["stdout"]) < pyrun.MAX_OUTPUT_CHARS + 100
    assert "characters not shown" in out["cells"][0]["stdout"]


def test_a_dataframe_comes_back_as_a_table():
    class Frame:
        columns = ["n", "word"]
        def limit(self, k): return self
        def collect(self): return [(1, "a"), (2, None)]
    nb = cells(("python", "df = make()\ndf"))
    exited: list[str] = []
    ns = {"dbutils": SimpleNamespace(notebook=SimpleNamespace(exit=exited.append)), "make": Frame}
    # `make` stands in for spark.sql(...): the wrapper's globals are the cells' globals.
    exec(compile(pyrun.wrapper_notebook(pyrun.plan(nb, upto=0, show=None)), "<w>", "exec"), ns)
    table = json.loads(exited[0])["cells"][0]["table"]
    assert table["columns"] == ["n", "word"] and table["rows"] == [["1", "a"], ["2", ""]]


# -- reading a run back --------------------------------------------------------------------------
def read(p, output=None, *, life="TERMINATED", result="SUCCESS", error="", message=""):
    return pyrun.results_from_run(p, life_cycle=life, result_state=result, message=message,
                                  output=output, error=error, seconds=3.0)


def test_a_live_run_is_not_finished():
    p = pyrun.plan(cells(("python", "1")), upto=0, show=None)
    assert read(p, life="RUNNING", result="") == (False, {})


def test_a_failed_start_says_why_instead_of_hanging():
    p = pyrun.plan(cells(("python", "1")), upto=0, show=None)
    done, out = read(p, None, result="FAILED", message="Serverless compute is not enabled for this workspace")
    assert done and out[0].state is RunState.FAILED and "not enabled" in out[0].error
    assert out[0].warehouse == pyrun.WHERE


def test_a_cancelled_run_is_cancelled_for_every_cell_asked_for():
    p = pyrun.plan(cells(("python", "1"), ("python", "2")), upto=1, show=None)
    done, out = read(p, None, life="TERMINATED", result="CANCELED")
    assert done and {r.state for r in out.values()} == {RunState.CANCELLED}


def test_a_cell_after_a_failure_names_the_cell_that_failed_first():
    nb = cells(("python", "boom"), ("python", "1"))
    p = pyrun.plan(nb, upto=1, show={1})
    doc = {"v": 1, "cells": [{"i": 0, "ok": False, "error": "NameError: boom"}]}
    done, out = read(p, json.dumps(doc))
    assert out[1].state is RunState.FAILED and "cell 1 failed" in out[1].error


def test_every_python_result_says_where_it_ran():
    p = pyrun.plan(cells(("python", "print(1)")), upto=0, show=None)
    doc = {"v": 1, "cells": [{"i": 0, "ok": True, "stdout": "1\n"}]}
    _, out = read(p, json.dumps(doc))
    assert out[0].warehouse == "Serverless · as the app" and out[0].output == "1\n"


def test_a_matplotlib_png_travels_on_the_result():
    """The wrapper puts base64 PNGs on the cell; the reader keeps them for the UI to draw."""
    p = pyrun.plan(cells(("python", "plt.show()")), upto=0, show=None)
    png = "iVBORw0KGgo="  # not a full image; the reader only checks shape and length
    doc = {"v": 1, "cells": [{"i": 0, "ok": True, "stdout": "KPI Summary\n", "images": [png, 12, ""]}]}
    _, out = read(p, json.dumps(doc))
    assert out[0].images == [png]
    assert out[0].to_dict()["images"] == [png]
    assert "KPI Summary" in out[0].output


def test_the_wrapper_mentions_matplotlib_and_image_caps():
    src = pyrun.wrapper_notebook(pyrun.plan(cells(("python", "1")), upto=0, show=None))
    assert "matplotlib" in src and "_capture_figs" in src
    assert str(pyrun.MAX_IMAGES) in src and str(pyrun.MAX_IMAGE_B64) in src


# -- the service ---------------------------------------------------------------------------------
class FakeRunner:
    def __init__(self, states, output=None):
        self.states, self.output_doc, self.submitted, self.cancelled, self.discarded = list(states), output, [], [], []
    async def submit(self, name, source):
        self.submitted.append((name, source)); return 77, f"/Users/sp/{name}"
    async def info(self, run_id):
        life, result = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return SimpleNamespace(life_cycle=life, result_state=result, message="", task_run_id=5)
    async def output(self, task_run_id): return self.output_doc, ""
    async def cancel(self, run_id): self.cancelled.append(run_id)
    async def discard(self, path): self.discarded.append(path)


def test_a_run_is_started_polled_to_the_end_and_cleaned_up():
    doc = json.dumps({"v": 1, "cells": [{"i": 0, "ok": True, "stdout": "hi\n"}]})
    runner = FakeRunner([("PENDING", ""), ("RUNNING", ""), ("TERMINATED", "SUCCESS")], doc)
    runs = PythonRuns(runner)
    async def go():
        started = await runs.start("a@x", cells(("python", "print('hi')")), upto=0, show={0})
        h = started["handle"]
        stages = [(await runs.poll("a@x", h))["state"] for _ in range(3)]
        return h, stages, await runs.poll("a@x", h)
    h, stages, last = asyncio.run(go())
    assert stages == ["running", "running", "done"]
    assert last["results"]["0"]["output"] == "hi\n" and last["results"]["0"]["state"] == "succeeded"
    assert runner.discarded == [f"/Users/sp/run_{h}"]        # the scratch notebook does not pile up


def test_someone_elses_handle_is_not_found():
    runs = PythonRuns(FakeRunner([("RUNNING", "")]))
    async def go():
        h = (await runs.start("a@x", cells(("python", "1")), upto=0, show={0}))["handle"]
        with pytest.raises(LookupError):
            await runs.poll("intruder@x", h)
    asyncio.run(go())


def test_nothing_to_run_never_reaches_compute():
    runner = FakeRunner([("RUNNING", "")])
    out = asyncio.run(PythonRuns(runner).start("a@x", cells(("sql", "select 1")), upto=0, show={0}))
    assert "handle" not in out and out["refused"][0]["state"] == "refused" and not runner.submitted


# -- who may ask ---------------------------------------------------------------------------------
def api(admins=ADMIN, **kw) -> TestClient:
    cfg = Settings(agent_mode="fake", demo_scenario="notebook", dev_user=ADMIN, llm_demo_seed=True,
                   allowed_models=["fake/model-a"], default_model="fake/model-a", llm_admins=admins, **kw)
    app = build(cfg)
    return TestClient(app)


BODY = {"cells": [{"language": "python", "source": "print(1)"}], "show": [0]}


def test_a_non_administrator_is_told_why_and_nothing_starts():
    with api(admins="someone-else@example.com") as c:
        me = c.get("/api/me").json()["pythonRun"]
        assert me["enabled"] is False and "administrators" in me["reason"]
        r = c.post("/api/notebook/python-runs", json=BODY)
        assert r.status_code == 403 and "not as you" in r.text


def test_the_owner_can_switch_python_off_even_for_administrators():
    with api(python_run=False) as c:
        assert c.get("/api/me").json()["pythonRun"]["enabled"] is False
        assert c.post("/api/notebook/python-runs", json=BODY).status_code == 403


def test_an_administrator_starts_a_run_through_the_route():
    doc = json.dumps({"v": 1, "cells": [{"i": 0, "ok": True, "stdout": "1\n"}]})
    runner = FakeRunner([("TERMINATED", "SUCCESS")], doc)
    with api() as c:
        c.app.state.pyruns = PythonRuns(runner)
        assert c.get("/api/me").json()["pythonRun"]["enabled"] is True
        started = c.post("/api/notebook/python-runs", json=BODY).json()
        polled = c.get(f"/api/notebook/python-runs/{started['handle']}").json()
        assert polled["state"] == "done" and polled["results"]["0"]["output"] == "1\n"
        assert c.get("/api/notebook/python-runs/unknown").status_code == 404
        assert c.post("/api/notebook/python-runs", json={**BODY, "show": [5]}).status_code == 422


# -- the agent's tool asks the app to run a notebook -----------------------------------------------
import importlib.util
import pathlib

from api.services.run_bridge import RunBridge

SOURCE = "# Databricks notebook source\nx = 20\n\n# COMMAND ----------\n\nprint(x + 1)\n"


def internal(admins=ADMIN):
    c = api(admins=admins)
    return c


def test_the_bridge_key_opens_one_session_and_only_with_a_grant():
    bridge = RunBridge("http://127.0.0.1:8000")
    k = bridge.key_for("s1")
    assert bridge.verify("s1", k) and not bridge.verify("s2", k) and not bridge.verify("s1", "x" * 64)
    assert not bridge.granted("s1")
    bridge.grant("s1")
    assert bridge.granted("s1")
    assert bridge.env_for("s1")["NBMCP_RUN_KEY"] == k


def test_agent_internal_execution_refuses_even_a_legacy_admin_grant():
    with internal() as c:
        class NeverRun:
            async def start(self, *args, **kwargs):
                raise AssertionError("model code reached the app execution identity")
            async def poll(self, *args, **kwargs):
                raise AssertionError("model code reached the app execution identity")
        c.app.state.pyruns = NeverRun()
        bridge = c.app.state.run_bridge
        bridge.grant("sess1")
        body = {"session": "sess1", "key": bridge.key_for("sess1"), "source": SOURCE, "language": "PYTHON"}
        response = c.post("/internal/run-notebook", json=body)
        assert response.status_code == 403
        assert "never runs as the app service principal" in response.json()["detail"]
        assert c.get("/internal/run-notebook/old-handle", params={"session": "sess1", "key": body["key"]}).status_code == 403


def test_creating_a_session_never_grants_the_agent_app_identity_even_to_an_admin():
    for admins in (ADMIN, "someone-else@example.com"):
        with internal(admins) as c:
            sid = c.post("/api/sessions", json={"folder": "/Users/tester@example.com/agent_scratch"}).json()["id"]
            assert not c.app.state.run_bridge.granted(sid)


def _tool_module():
    path = pathlib.Path(__file__).resolve().parents[1] / "tools" / "databricks_notebook_mcp.py"
    spec = importlib.util.spec_from_file_location("nbmcp_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_tool_falls_back_to_the_app_when_the_users_token_cannot_submit_runs(monkeypatch):
    mod = _tool_module()
    monkeypatch.setattr(mod, "RUN_URL", "http://127.0.0.1:1/internal/run-notebook")
    monkeypatch.setattr(mod, "ALLOW_WRITES", True)
    monkeypatch.setattr(mod, "_check_path_scope", lambda p: None)
    def denied(path, body=None): raise PermissionError("permission denied by the workspace for POST /api/2.1/jobs/runs/submit")
    monkeypatch.setattr(mod, "_post", denied)
    import base64
    monkeypatch.setattr(mod, "_get", lambda path, params=None: {"content": base64.b64encode(SOURCE.encode()).decode(), "language": "PYTHON"})
    calls = []
    def app(method, url, **kw):
        calls.append(method)
        if method == "POST":
            assert "x = 20" in kw["json"]["source"]       # read with the user's token, sent as text
            return {"handle": "h1"}
        return {"state": "done", "seconds": 4.0, "results": {"1": {"state": "succeeded", "output": "21\n"}}}
    monkeypatch.setattr(mod, "_app_call", app)
    with pytest.raises(PermissionError, match="never runs as the app"):
        mod.dbx_run_notebook("/Users/me/x/nb")
    assert calls == []


def test_without_the_app_run_service_the_denial_stands(monkeypatch):
    mod = _tool_module()
    monkeypatch.setattr(mod, "RUN_URL", "")
    monkeypatch.setattr(mod, "ALLOW_WRITES", True)
    monkeypatch.setattr(mod, "_check_path_scope", lambda p: None)
    def denied(path, body=None): raise PermissionError("denied")
    monkeypatch.setattr(mod, "_post", denied)
    with pytest.raises(PermissionError):
        mod.dbx_run_notebook("/Users/me/x/nb")
