"""The session loop, run for real: the same file that runs on serverless, in a thread, on a temp folder.

Nothing is mocked except the clock's speed (short intervals). What is under test is the contract a
real session keeps with the app: numbered commands, one namespace, a result for every command, and an
end that always comes.
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.domain import kernel, kernel_runtime
from api.domain.kernel_runtime import Kernel, get_json, put_json, seq_name


class Session:
    """A kernel on a temp folder, and the app's side of the protocol, in a few lines."""

    def __init__(self, root: Path, **kw):
        self.root = str(root)
        kw.setdefault("poll_seconds", 0.01)
        kw.setdefault("beat_seconds", 0.05)
        self.kernel = Kernel(self.root, **kw)
        self.reason: str | None = None
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.seq = 0

    def _serve(self):
        self.reason = self.kernel.serve()

    def start(self):
        self.thread.start()
        return self

    def send(self, source: str, **extra) -> int:
        self.seq += 1
        os.makedirs(f"{self.root}/cmd", exist_ok=True)
        put_json(f"{self.root}/cmd/{seq_name(self.seq)}", {"seq": self.seq, "id": f"c{self.seq}", "kind": "python",
                                                           "source": source, **extra})
        return self.seq

    def out(self, seq: int):
        return get_json(f"{self.root}/out/{seq_name(seq)}")

    def wait(self, seq: int, timeout: float = 10.0):
        end = time.time() + timeout
        while time.time() < end:
            doc = self.out(seq)
            if doc and doc.get("final"):
                return doc
            time.sleep(0.01)
        raise AssertionError(f"no final result for command {seq}: {self.out(seq)}")

    def run(self, source: str, **extra):
        return self.wait(self.send(source, **extra))

    def control(self, name: str, body=None):
        os.makedirs(f"{self.root}/ctl", exist_ok=True)
        put_json(f"{self.root}/ctl/{name}", body if body is not None else {})

    def lease(self, n: int):
        self.control("lease.json", {"n": n})

    def stop(self):
        self.control("stop")
        self.thread.join(10)
        assert not self.thread.is_alive(), "the session did not end when told to"
        return self.reason


def text(doc, stream=None) -> str:
    return "".join(o["text"] for o in doc["outputs"] if o["type"] == "text" and (stream is None or o["stream"] == stream))


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "s1", idle_seconds=60, lease_seconds=60).start()
    yield s
    if s.thread.is_alive():
        s.control("stop")
        s.thread.join(10)


# -- the point of a session ------------------------------------------------------------------


def test_a_variable_made_by_one_cell_is_there_in_the_next(session):
    assert session.run("x = 41\nprint('set')")["ok"]
    nxt = session.run("x += 1\nprint(x)")
    assert nxt["ok"] and text(nxt, "stdout").strip() == "42"


def test_functions_and_imports_persist_too(session):
    session.run("import math\ndef area(r):\n    return math.pi * r * r")
    out = session.run("round(area(2), 3)")
    assert text(out, "result") == "12.566"


def test_the_last_expression_is_shown_and_a_print_before_it_comes_first(session):
    out = session.run("print('a')\n1 + 1")
    assert [(o["stream"], o["text"].strip()) for o in out["outputs"]] == [("stdout", "a"), ("result", "2")]


def test_html_and_display_are_outputs_in_order(session):
    out = session.run("print('one')\ndisplayHTML('<b>two</b>')\nprint('three')")
    assert [o["type"] for o in out["outputs"]] == ["text", "html", "text"]


def test_commands_sent_before_the_session_started_run_in_order(tmp_path):
    s = Session(tmp_path / "early", idle_seconds=60, lease_seconds=60)
    a, b = s.send("order = ['a']"), s.send("order.append('b')\nprint(order)")
    s.start()
    try:
        s.wait(a)
        assert "['a', 'b']" in text(s.wait(b))
    finally:
        s.stop()


# -- failure never ends the session -----------------------------------------------------------


def test_an_exception_reports_the_line_and_the_session_carries_on(session):
    session.run("keep = 1")
    bad = session.run("a = 1\nb = 1 / 0\nc = 3")
    assert not bad["ok"] and "ZeroDivisionError" in bad["error"] and "line 2" in bad["error"]
    assert session.run("print(keep)")["ok"]


def test_a_syntax_error_is_a_failed_cell_not_a_dead_session(session):
    bad = session.run("def broken(:\n    pass")
    assert not bad["ok"] and "SyntaxError" in bad["error"]
    assert session.run("print('alive')")["ok"]


def test_sys_exit_in_a_cell_ends_the_cell_not_the_session(session):
    bad = session.run("import sys\nsys.exit(3)")
    assert not bad["ok"] and "SystemExit" in bad["error"]
    assert text(session.run("print('still here')")).strip() == "still here"


def test_a_huge_output_is_clipped_and_says_so(session):
    out = session.run("print('x' * 500000)")
    body = text(out, "stdout")
    assert len(body) < 25_000 and "characters not shown" in body


def test_a_cell_that_prints_forever_stays_small(session):
    out = session.run("for _ in range(20000):\n    print('line ' * 50)")
    assert len(json.dumps(out)) < 200_000


# -- progress while running -------------------------------------------------------------------


def test_text_so_far_is_visible_while_the_cell_runs(session):
    seq = session.send("import time\nprint('first line', flush=True)\ntime.sleep(2)\nprint('last')")
    seen = None
    end = time.time() + 5
    while time.time() < end:
        doc = session.out(seq)
        if doc and not doc.get("final") and "first line" in text(doc):
            seen = doc
            break
        time.sleep(0.02)
    assert seen is not None, "no progress was written while the cell ran"
    assert isinstance(seen["n"], int)
    assert session.wait(seq)["ok"]


def test_the_heartbeat_counter_goes_up(session):
    session.run("pass")                               # the session is up once it has answered
    first = get_json(f"{session.root}/hb.json")["n"]
    time.sleep(0.4)
    assert get_json(f"{session.root}/hb.json")["n"] > first


# -- stopping one cell ------------------------------------------------------------------------


def test_interrupt_stops_a_running_loop_and_the_variables_survive(session):
    session.run("kept = 'still here'")
    seq = session.send("import time\nwhile True:\n    time.sleep(0.01)")
    time.sleep(0.4)
    session.control("interrupt", {"seq": seq})
    doc = session.wait(seq)
    assert doc.get("interrupted") and not doc["ok"]
    assert text(session.run("print(kept)")).strip() == "still here"


def test_interrupt_of_a_queued_cell_cancels_it_without_running_it(session):
    blocker = session.send("import time\ntime.sleep(1.2)")
    time.sleep(0.2)
    queued = session.send("ran = True")
    session.control("interrupt", {"seq": queued})
    session.wait(blocker)
    cancelled = session.wait(queued)
    assert cancelled.get("interrupted") and "Cancelled" in cancelled["error"]
    assert "NameError" in session.run("print(ran)")["error"]


def test_interrupt_aimed_at_a_cell_that_already_ended_does_nothing(session):
    done = session.run("v = 5")
    session.control("interrupt", {"seq": done["seq"]})
    time.sleep(0.3)
    assert session.run("print(v)")["ok"]


def test_every_command_runs_exactly_once_whatever_the_interrupts(tmp_path):
    """An interrupt can land in the instants between one cell ending and the next starting. It must never
    lose a result or run a command twice. This throws many at it."""
    s = Session(tmp_path / "storm", idle_seconds=60, lease_seconds=60).start()
    try:
        s.run("hits = []")
        n = 60
        for i in range(1, n + 1):
            s.send(f"hits.append({i})\nimport time\ntime.sleep(0.005)")
        last = s.seq
        stop = threading.Event()

        def hammer():
            rnd = random.Random(7)
            while not stop.is_set():
                s.control("interrupt", {"seq": rnd.randint(2, last)})
                time.sleep(0.003)

        t = threading.Thread(target=hammer, daemon=True)
        t.start()
        for seq in range(2, last + 1):
            s.wait(seq, timeout=30)
        stop.set()
        t.join()
        final = s.run("print(sorted(hits))")
        shown = eval(text(final, "stdout").strip())
        assert len(shown) == len(set(shown)), f"a command ran twice: {shown}"
    finally:
        s.stop()


# -- ending -----------------------------------------------------------------------------------


def test_stop_ends_the_session_and_says_why(tmp_path):
    s = Session(tmp_path / "stop", idle_seconds=60, lease_seconds=60).start()
    s.run("x = 1")
    assert s.stop() == "stop"
    assert get_json(f"{s.root}/hb.json")["state"] == "ended"
    assert get_json(f"{s.root}/hb.json")["reason"] == "stop"


def test_stop_interrupts_a_running_cell(tmp_path):
    s = Session(tmp_path / "stopbusy", idle_seconds=60, lease_seconds=60).start()
    seq = s.send("import time\nwhile True:\n    time.sleep(0.01)")
    time.sleep(0.3)
    assert s.stop() == "stop"
    assert s.out(seq)["final"]


def test_a_session_nobody_asks_for_ends_by_itself(tmp_path):
    s = Session(tmp_path / "lease", idle_seconds=60, lease_seconds=0.4).start()
    s.thread.join(5)
    assert not s.thread.is_alive() and s.reason == "lease"


def test_renewing_the_lease_keeps_it_alive_and_stopping_renewal_ends_it(tmp_path):
    # A lease several times longer than the renewal interval: a loaded machine may delay a beat, and
    # the rule under test is "renewed means alive", not "a late beat is fatal".
    s = Session(tmp_path / "renew", idle_seconds=60, lease_seconds=2.0).start()
    for n in range(12):
        s.lease(n)
        time.sleep(0.2)
    assert s.thread.is_alive(), "a lease that kept being renewed expired"
    s.thread.join(8)
    assert s.reason == "lease"


def test_a_lease_that_expires_during_a_cell_interrupts_it(tmp_path):
    s = Session(tmp_path / "leasebusy", idle_seconds=60, lease_seconds=0.5).start()
    seq = s.send("import time\nwhile True:\n    time.sleep(0.01)")
    s.thread.join(8)
    assert not s.thread.is_alive() and s.reason == "lease"
    assert s.out(seq)["final"]


def test_an_idle_session_ends(tmp_path):
    s = Session(tmp_path / "idle", idle_seconds=0.4, lease_seconds=60).start()
    s.thread.join(5)
    assert not s.thread.is_alive() and s.reason == "idle"


def test_a_session_that_is_working_is_not_idle(tmp_path):
    s = Session(tmp_path / "busy", idle_seconds=0.6, lease_seconds=60).start()
    seq = s.send("import time\ntime.sleep(1.0)")
    assert s.wait(seq)["ok"]
    assert s.thread.is_alive(), "a session that had just finished a cell ended as idle"
    s.stop()


# -- restarts and bad input -------------------------------------------------------------------


def test_a_restarted_kernel_resumes_after_the_last_finished_command(tmp_path):
    root = tmp_path / "resume"
    first = Session(root, idle_seconds=60, lease_seconds=60).start()
    first.run("print('one')")
    first.run("print('two')")
    first.stop()
    (root / "ctl" / "stop").unlink()
    second = Session(root, idle_seconds=60, lease_seconds=60)
    second.seq = 2
    second.start()
    try:
        third = second.run("print('three')")
        assert third["seq"] == 3 and text(third).strip() == "three"
        assert text(second.out(1)).strip() == "one", "a finished command was run again"
    finally:
        second.stop()


def test_an_unreadable_command_is_a_failed_cell(tmp_path):
    s = Session(tmp_path / "bad", idle_seconds=60, lease_seconds=60)
    s.kernel.read_attempts, s.kernel.read_wait = 3, 0.02
    s.start()
    try:
        os.makedirs(f"{s.root}/cmd", exist_ok=True)
        Path(f"{s.root}/cmd/{seq_name(1)}").write_text("{not json")
        s.seq = 1
        assert not s.wait(1)["ok"]
        assert s.run("print('next')")["ok"]
    finally:
        s.stop()


def test_a_command_of_a_kind_it_cannot_run_is_refused_in_words(session):
    out = session.run("anything", kind="cobol")
    assert not out["ok"] and "cobol" in out["error"]


def test_a_result_too_large_to_ship_keeps_its_words(tmp_path):
    s = Session(tmp_path / "big", idle_seconds=60, lease_seconds=60, hard_limit=50_000,
                limits={"budget": 10_000_000}).start()
    try:
        out = s.run("displayHTML('<p>' + 'x' * 200000 + '</p>')\nprint('words')")
        assert text(out, "stdout").strip() == "words"
        assert all(o["type"] == "text" for o in out["outputs"])
        assert "too large" in text(out, "notice")
    finally:
        s.stop()


# -- the notebook that starts a session -----------------------------------------------------


def test_the_generated_notebook_is_the_tested_code_and_starts_a_session(tmp_path):
    root = tmp_path / "nb"
    os.makedirs(root / "ctl")
    put_json(str(root / "ctl" / "stop"), {})           # end at once: this proves it starts and exits
    exited: list[str] = []
    ns = {"dbutils": SimpleNamespace(notebook=SimpleNamespace(exit=exited.append)), "spark": "SPARK"}
    src = kernel.kernel_notebook(str(root), "sess1", idle_seconds=5, lease_seconds=30)
    assert src.startswith("# Databricks notebook source")
    exec(compile(src, "<kernel notebook>", "exec"), ns)
    assert exited == ["stop"]
    assert ns["_kernel"].ns["spark"] == "SPARK"        # a Databricks notebook has `spark`; so does this


def test_the_notebook_carries_the_runtime_unchanged():
    assert kernel.runtime_source() in kernel.kernel_notebook("/Volumes/x/y/z", "s")


def test_a_hostile_root_is_data_not_code():
    evil = '"""; raise SystemExit("pwned"); x = """\n\\'
    src = kernel.kernel_notebook(evil, "s")
    compile(src, "<kernel notebook>", "exec")                       # still valid Python
    line = next(l for l in src.splitlines() if l.startswith("_config = json.loads("))
    cfg = json.loads(eval(line[len("_config = json.loads("):-1]))   # the literal, read back
    assert cfg["root"] == evil


# -- reading a result back --------------------------------------------------------------------


def test_a_final_file_becomes_a_result_the_ui_draws():
    doc = {"protocol": 1, "seq": 1, "id": "c1", "final": True, "ok": True, "seconds": 1.5,
           "outputs": [{"type": "text", "stream": "stdout", "text": "hi\n"}]}
    p = kernel.read_out(doc, command_id="c1")
    assert p and p.final and p.result.state.value == "succeeded" and p.result.output == "hi\n"
    assert p.result.warehouse == kernel.WHERE


def test_an_interrupted_cell_is_cancelled_not_failed():
    doc = {"protocol": 1, "final": True, "ok": False, "interrupted": True, "error": "Interrupted", "outputs": []}
    assert kernel.read_out(doc).result.state.value == "cancelled"


def test_progress_is_not_a_result():
    doc = {"protocol": 1, "final": False, "n": 4, "seconds": 2,
           "outputs": [{"type": "text", "stream": "stdout", "text": "so far"}]}
    p = kernel.read_out(doc)
    assert p and not p.final and p.result is None and p.beat == 4 and p.outputs[0]["text"] == "so far"


@pytest.mark.parametrize("junk", [None, [], "x", {"protocol": 99}, {"final": True}])
def test_a_file_that_is_not_ours_is_ignored(junk):
    assert kernel.read_out(junk) is None


def test_a_result_for_another_command_is_ignored():
    doc = {"protocol": 1, "final": True, "ok": True, "id": "someone-else", "outputs": []}
    assert kernel.read_out(doc, command_id="c1") is None


def test_a_hostile_out_file_cannot_smuggle_an_unknown_output():
    doc = {"protocol": 1, "final": True, "ok": True, "outputs": [
        {"type": "script", "code": "alert(1)"}, {"type": "image", "png": 123},
        {"type": "text", "stream": "weird", "text": "kept"}]}
    outs = kernel.read_out(doc).result.outputs
    assert [o["type"] for o in outs] == ["text"] and outs[0]["stream"] == "stdout"


def test_classify():
    assert kernel.classify("python", "print(1)") == kernel.Command("python", "print(1)")
    assert isinstance(kernel.classify("python", "   "), kernel.Refusal)
    assert isinstance(kernel.classify("sql", "select 1"), kernel.Refusal)
    assert kernel.classify("sql", "%python\nprint(1)") == kernel.Command("python", "print(1)")


# -- nested values in a Python table ------------------------------------------------------------------

class _Row(tuple):
    """What a Spark Row does that the table code relies on."""

    def asDict(self, recursive=False):
        return {"x": 1, "tags": ["a", "b"], "big": 2 ** 60, "when": "t"}


def test_nested_python_values_are_json_the_ui_can_type():
    rt = kernel_runtime.CellRuntime()
    assert rt.sval([1, 2, None]) == "[1,2,null]"
    assert rt.sval({"k": (1, "b")}) == '{"k":[1,"b"]}'
    assert rt.sval(_Row()) == '{"x":1,"tags":["a","b"],"big":"1152921504606846976","when":"t"}'
    assert rt.sval(None) is None and rt.sval("s") == "s" and rt.sval(5) == "5"


def test_a_spark_table_with_a_nested_column_sends_its_type_text():
    class Df:
        columns = ["a", "n"]
        dtypes = [("a", "array<int>"), ("n", "int")]

        def limit(self, n):
            return self

        def collect(self):
            return [([1, 2], 3)]

    table = kernel_runtime.CellRuntime().as_table(Df())
    assert table["types"] == ["array", "int"] and table["typeTexts"] == ["array<int>", "int"]
    assert table["rows"] == [["[1,2]", "3"]]


def test_a_table_without_a_nested_column_has_no_type_texts():
    class Df:
        columns = ["n"]
        dtypes = [("n", "int")]

        def limit(self, n):
            return self

        def collect(self):
            return [(3,)]

    assert "typeTexts" not in kernel_runtime.CellRuntime().as_table(Df())


# -- dbutils.widgets ------------------------------------------------------------------------------------------

DECLARE = """
dbutils.widgets.text("city", "Oslo", "City")
dbutils.widgets.dropdown("size", "m", ["s", "m", "l"])
dbutils.widgets.combobox("tag", "a", ["a", "b"])
dbutils.widgets.multiselect("pick", "x", ["x", "y", "z"])
"""


def test_widgets_are_declared_and_come_back_with_the_result(session):
    done = session.run(DECLARE)
    assert done["ok"] is True
    got = {w["name"]: w for w in done["widgets"]}
    assert list(got) == ["city", "size", "tag", "pick"]
    assert got["city"] == {"name": "city", "type": "text", "default": "Oslo", "label": "City", "choices": [], "value": "Oslo"}
    assert got["size"]["choices"] == ["s", "m", "l"] and got["pick"]["type"] == "multiselect"


def test_get_returns_the_value_the_app_sent_and_the_default_without_one(session):
    session.run(DECLARE)
    assert text(session.run("print(dbutils.widgets.get('city'))")) == "Oslo\n"
    assert text(session.run("print(dbutils.widgets.get('city'))", widgets={"city": "Rome"})) == "Rome\n"
    assert text(session.run("print(dbutils.widgets.get('city'))")) == "Oslo\n", "values travel with each command"


def test_a_value_a_widget_does_not_allow_becomes_its_default(session):
    session.run(DECLARE)
    got = session.run("print(dbutils.widgets.get('size'), dbutils.widgets.get('pick'), dbutils.widgets.get('tag'))",
                      widgets={"size": "xl", "pick": "x,nope", "tag": "free text"})
    assert text(got) == "m x free text\n", "a combobox takes any text; a dropdown and a multiselect do not"
    assert text(session.run("print(dbutils.widgets.get('pick'))", widgets={"pick": "x,z"})) == "x,z\n"


def test_undefined_widget_is_an_error_in_databricks_words(session):
    done = session.run("dbutils.widgets.get('nope')")
    assert done["ok"] is False and "InputWidgetNotDefined" in done["error"]


def test_a_default_that_is_not_a_choice_is_refused(session):
    done = session.run("dbutils.widgets.dropdown('d', 'q', ['a', 'b'])")
    assert done["ok"] is False and "not one of its choices" in done["error"]
    assert done["widgets"] == []


def test_remove_and_remove_all_are_reported_as_an_empty_list_not_silence(session):
    session.run(DECLARE)
    assert [w["name"] for w in session.run("dbutils.widgets.remove('tag')")["widgets"]] == ["city", "size", "pick"]
    assert session.run("dbutils.widgets.removeAll()")["widgets"] == []


def test_get_all_and_a_widget_declared_in_a_failed_cell_stay(session):
    done = session.run("dbutils.widgets.text('a', '1')\nraise ValueError('x')")
    assert done["ok"] is False and [w["name"] for w in done["widgets"]] == ["a"]
    assert text(session.run("print(dbutils.widgets.getAll())", widgets={"a": "2"})) == "{'a': '2'}\n"


def test_the_value_each_widget_has_is_reported(session):
    done = session.run(DECLARE, widgets={"city": "Rome", "size": "l"})
    assert {w["name"]: w["value"] for w in done["widgets"]} == {"city": "Rome", "size": "l", "tag": "a", "pick": "x"}


def test_the_rest_of_dbutils_is_left_alone():
    from api.domain.kernel_runtime import _DbUtils, Widgets

    class Real:
        fs = "the real fs"

    proxy = _DbUtils(Real(), Widgets())
    assert proxy.fs == "the real fs" and proxy.widgets is not None
    with pytest.raises(AttributeError, match="not available in this session"):
        _DbUtils(None, Widgets()).fs
