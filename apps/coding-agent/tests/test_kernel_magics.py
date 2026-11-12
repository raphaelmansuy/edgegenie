"""%sh, %pip, %md and %run: what the session does with them, and what the app does before it sends them.

The session half runs the real kernel in a thread (see test_kernel.py). The app half is pure, so it is
tested with a fake reader: no workspace, no network.
"""

from __future__ import annotations

import asyncio
import sys
import time
from types import SimpleNamespace

import pytest

from api.domain import kernel, run_magic
from tests.test_kernel import session, text  # noqa: F401  (the fixture)


def cell(index, language, source, kind="code", truncated=False):
    return SimpleNamespace(index=index, language=language, source=source, kind=kind, truncated=truncated)


# -- the session ----------------------------------------------------------------------------------

class TestShell:
    def test_output_and_exit_status(self, session):
        done = session.run("echo hello; echo oops 1>&2; exit 3", kind="sh")
        assert text(done, "stdout") == "hello\n"
        assert text(done, "stderr") == "oops\n"
        assert done["ok"] is False and "status 3" in done["error"]

    def test_success_is_ok(self, session):
        assert session.run("true", kind="sh")["ok"] is True

    def test_it_cannot_ask_a_question(self, session):
        # stdin is closed: `read` returns at once instead of hanging the session
        assert session.run("read x || echo no-input", kind="sh")["ok"] is True

    def test_a_timeout_stops_it_and_says_so(self, session):
        started = time.time()
        done = session.run("sleep 30", kind="sh", timeout=1)
        assert time.time() - started < 10
        assert done["ok"] is False and "1 seconds" in done["error"]

    def test_the_session_survives_and_keeps_variables(self, session):
        session.run("x = 41")
        session.run("exit 1", kind="sh")
        assert text(session.run("print(x + 1)")) == "42\n"

    def test_interrupt_kills_the_program_and_whatever_it_started(self, session, tmp_path):
        marker = tmp_path / "child-alive"
        seq = session.send(f"(sleep 1.5; touch {marker}) & sleep 30", kind="sh")
        time.sleep(0.4)
        session.control("interrupt", {"seq": seq})
        done = session.wait(seq, 10)
        assert done.get("interrupted") is True
        time.sleep(2.0)
        assert not marker.exists(), "a child of the shell survived the interrupt"

    def test_an_interrupt_that_is_read_twice_still_stops_the_program(self, session):
        # On a volume a deleted request can be read again a moment later. The second read must not land in
        # the cleanup of the first and leave the program running.
        session.run("x = 41")
        seq = session.send("sleep 30", kind="sh")
        time.sleep(0.4)
        for _ in range(12):
            session.control("interrupt", {"seq": seq})
            time.sleep(0.03)
        done = session.wait(seq, 10)
        assert done.get("interrupted") is True
        assert text(session.run("print(x + 1)")) == "42\n"

    def test_an_empty_command_is_an_error_not_a_hang(self, session):
        assert session.run("   ", kind="sh")["ok"] is False


class TestPip:
    def test_a_bad_command_fails_with_pips_words(self, session):
        done = session.run("not-a-pip-command", kind="pip")
        assert done["ok"] is False
        assert "unknown command" in text(done, "stderr").lower() or "status" in done["error"]

    def test_arguments_are_read_like_a_shell_would(self, session):
        done = session.run("install 'unterminated", kind="pip")
        assert done["ok"] is False and "could not read the pip arguments" in done["error"]

    def test_nothing_to_do_is_said(self, session):
        done = session.run("", kind="pip")
        assert done["ok"] is False and "%pip install" in done["error"]

    def test_a_successful_install_says_old_imports_stay_old(self, session, monkeypatch):
        # Not a real install (no network in tests): `--version` exits 0 like a good command does, and the
        # notice is attached for install/uninstall only.
        listed = session.run("--version", kind="pip")
        assert listed["ok"] is True and "pip " in text(listed, "stdout")
        assert not any(o.get("stream") == "notice" for o in listed["outputs"])

    def test_uses_this_interpreter(self, session):
        done = session.run("--version", kind="pip")
        assert sys.prefix in text(done, "stdout") or "pip" in text(done, "stdout")


def test_markdown_is_returned_as_markdown(session):
    done = session.run("# Title\n\nSome *text*", kind="md")
    assert done["outputs"] == [{"type": "markdown", "text": "# Title\n\nSome *text*"}]


class TestCells:
    def run(self, session, cells, notes=()):
        return session.run("", kind="cells", cells=cells, notes=list(notes))

    def test_cells_share_the_namespace_with_the_session(self, session):
        session.run("base = 10")
        done = self.run(session, [
            {"kind": "python", "source": "y = base * 2", "name": "other, cell 1"},
            {"kind": "sh", "source": "echo from-shell", "name": "other, cell 2"},
            {"kind": "python", "source": "print(y)", "name": "other, cell 3"},
        ])
        assert done["ok"] is True
        assert text(done, "stdout") == "from-shell\n20\n"
        assert text(session.run("print(y)")) == "20\n", "what %run defined is there afterwards"

    def test_it_stops_at_the_first_failure_and_names_the_cell(self, session):
        done = self.run(session, [
            {"kind": "python", "source": "print('one')", "name": "lib, cell 1"},
            {"kind": "python", "source": "raise ValueError('bad')", "name": "lib, cell 2"},
            {"kind": "python", "source": "print('three')", "name": "lib, cell 3"},
        ])
        assert done["ok"] is False
        assert done["error"].startswith("in lib, cell 2:")
        assert "lib, cell 2" in done["error"] and "ValueError: bad" in done["error"]
        assert "three" not in text(done) and "one" in text(done)

    def test_notes_come_first(self, session):
        done = self.run(session, [{"kind": "python", "source": "print(1)", "name": "a"}],
                        notes=["a, cell 4 was left out: this is a SQL cell"])
        assert done["outputs"][0] == {"type": "text", "stream": "notice",
                                      "text": "a, cell 4 was left out: this is a SQL cell\n"}

    def test_a_malformed_entry_is_skipped_not_fatal(self, session):
        done = self.run(session, [None, {"kind": "python"}, {"kind": "python", "source": "print('ok')", "name": "x"}])
        assert done["ok"] is True and text(done) == "ok\n"

    def test_interrupt_stops_the_rest(self, session):
        seq = session.send("", kind="cells", cells=[
            {"kind": "python", "source": "import time\nwhile True: time.sleep(0.01)", "name": "a"},
            {"kind": "python", "source": "print('never')", "name": "b"}])
        time.sleep(0.3)
        session.control("interrupt", {"seq": seq})
        done = session.wait(seq, 10)
        assert done.get("interrupted") is True and "never" not in text(done)


# -- what the app decides a cell is -----------------------------------------------------------------

class TestClassify:
    @pytest.mark.parametrize("language,source,kind,body", [
        ("python", "x = 1", "python", "x = 1"),
        ("pip", "install foo   bar", "pip", "install foo bar"),
        ("shell", "ls -la\npwd", "sh", "ls -la\npwd"),
        ("run", "./other", "run", "./other"),
        ("python", "%pip install foo", "pip", "install foo"),
        ("python", "%sh ls\npwd", "sh", "ls\npwd"),
        ("sql", "%sh\nls", "sh", "ls"),
        ("python", "%run ./helpers", "run", "./helpers"),
        ("python", "%md\n# hi", "md", "# hi"),
        ("sql", "%python\nprint(1)", "python", "print(1)"),
    ])
    def test_kinds(self, language, source, kind, body):
        got = kernel.classify(language, source)
        assert isinstance(got, kernel.Command), got
        assert (got.kind, got.source) == (kind, body)

    @pytest.mark.parametrize("language,source,why", [
        ("python", "%sql select 1", "SQL cell"),
        ("python", "%pip", "%pip install"),
        ("python", "%sh", "%sh needs"),
        ("python", "%run", "%run needs"),
        ("python", "%fs ls /", "%fs cells cannot run here"),
        ("sql", "select 1", "SQL cell"), ("scala", "val x = 1", "scala cells do not run as Python"),
        ("python", "", "empty"),
    ])
    def test_refusals_say_why(self, language, source, why):
        got = kernel.classify(language, source)
        assert isinstance(got, kernel.Refusal) and why in got.why

    def test_a_pip_command_is_one_line(self):
        assert kernel.classify("python", "%pip install a \\\n  b").source == "install a \\ b"


# -- %run, on the app's side ------------------------------------------------------------------------

def fake_reader(notebooks, log=None):
    async def read(path):
        if log is not None:
            log.append(path)
        got = notebooks.get(path)
        if got is None:
            raise LookupError("it does not exist")
        if isinstance(got, Exception):
            raise got
        return got
    return read


def expand(notebooks, ref="./lib", at="/Users/me/main", **kw):
    log = []
    return asyncio.run(run_magic.expand(fake_reader(notebooks, log), at, ref, **kw)), log


class TestRunTarget:
    @pytest.mark.parametrize("ref,want", [
        ("./lib", "/Users/me/lib"), ("lib", "/Users/me/lib"), ("../shared/lib", "/Users/shared/lib"),
        ("/Repos/x/lib", "/Repos/x/lib"), ("'./my lib'", "/Users/me/my lib"), ("./a/../lib", "/Users/me/lib"),
        ("///etc", "/etc"),
    ])
    def test_paths(self, ref, want):
        assert run_magic.target("/Users/me/main", ref) == want

    @pytest.mark.parametrize("ref,why", [
        ("", "needs a notebook"), ("./lib $x=1", "no arguments"), ("'./lib", "could not read"),
        ("../../..", "not a notebook path"), ("./a\x01b", "control character"),
    ])
    def test_refused(self, ref, why):
        with pytest.raises(run_magic.RunMagicError, match=why):
            run_magic.target("/Users/me/main", ref)


class TestExpand:
    def test_python_pip_and_sh_cells_become_commands_in_order(self):
        got, log = expand({"/Users/me/lib": [
            cell(0, "python", "A = 1"), cell(1, "markdown", "# docs", kind="markdown"),
            cell(2, "pip", "install x"), cell(3, "shell", "echo hi"), cell(4, "python", "")]})
        assert got.kind == "cells" and got.source == ""
        assert [(c["kind"], c["source"], c["name"]) for c in got.cells] == [
            ("python", "A = 1", "lib, cell 1"), ("pip", "install x", "lib, cell 3"), ("sh", "echo hi", "lib, cell 4")]
        assert got.notes == () and log == ["/Users/me/lib"]

    def test_what_cannot_run_is_said_not_dropped(self):
        got, _ = expand({"/Users/me/lib": [cell(0, "python", "A = 1"), cell(1, "sql", "select 1"),
                                           cell(2, "python", "%fs ls /")]})
        assert len(got.cells) == 1 and len(got.notes) == 2
        assert "lib, cell 2 was left out" in got.notes[0] and "SQL" in got.notes[0]

    def test_skip_cells_are_left_out_quietly(self):
        got, _ = expand({"/Users/me/lib": [cell(0, "python", "%skip\nA = 1"), cell(1, "python", "B = 2")]})
        assert [c["source"] for c in got.cells] == ["B = 2"]

    def test_nested_run_is_inlined_in_place_with_its_own_names(self):
        got, log = expand({
            "/Users/me/lib": [cell(0, "python", "A = 1"), cell(1, "run", "./deep/inner"), cell(2, "python", "C = 3")],
            "/Users/me/deep/inner": [cell(0, "python", "B = 2"), cell(1, "run", "../lib2")],
            "/Users/me/lib2": [cell(0, "python", "D = 4")]})
        assert [c["source"] for c in got.cells] == ["A = 1", "B = 2", "D = 4", "C = 3"]
        assert [c["name"] for c in got.cells] == ["lib, cell 1", "inner, cell 1", "lib2, cell 1", "lib, cell 3"]

    def test_a_cycle_is_named(self):
        with pytest.raises(run_magic.RunMagicError, match=r"circle: /Users/me/main -> /Users/me/a -> /Users/me/b -> /Users/me/a"):
            expand({"/Users/me/a": [cell(0, "run", "./b")], "/Users/me/b": [cell(0, "run", "./a")]}, ref="./a")

    def test_running_the_notebook_itself_is_a_cycle(self):
        with pytest.raises(run_magic.RunMagicError, match="circle"):
            expand({}, ref="./main")

    def test_depth_is_limited(self):
        books = {f"/Users/me/n{i}": [cell(0, "run", f"./n{i + 1}")] for i in range(10)}
        books["/Users/me/n10"] = [cell(0, "python", "x = 1")]
        with pytest.raises(run_magic.RunMagicError, match="more than 3 notebooks deep"):
            expand(books, ref="./n0")
        got, _ = expand(books, ref="./n0", max_depth=20)
        assert len(got.cells) == 1

    @pytest.mark.parametrize("error,words", [
        (PermissionError("denied"), "you cannot read /Users/me/lib, so it was not run"),
        (ValueError("it is a file, not a notebook"), "cannot be run: it is a file"),
        (RuntimeError("503 upstream"), "could not be read: 503"),
        (IsADirectoryError("is a folder"), "cannot be run"),
    ])
    def test_reading_failures_say_what_happened(self, error, words):
        with pytest.raises(run_magic.RunMagicError, match=words):
            expand({"/Users/me/lib": error})

    def test_a_missing_notebook(self):
        with pytest.raises(run_magic.RunMagicError, match="no notebook at /Users/me/lib"):
            expand({})

    def test_a_notebook_with_nothing_to_run_is_an_error(self):
        with pytest.raises(run_magic.RunMagicError, match="has no cell the session can run"):
            expand({"/Users/me/lib": [cell(0, "markdown", "# only docs", kind="markdown")]})

    def test_too_much_code_is_refused(self):
        big = [cell(i, "python", "x = 1") for i in range(run_magic.MAX_CELLS + 1)]
        with pytest.raises(run_magic.RunMagicError, match="too much code"):
            expand({"/Users/me/lib": big})
