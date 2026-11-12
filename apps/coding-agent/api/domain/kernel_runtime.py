"""What runs INSIDE the compute: run a cell and say what it produced; stay alive between cells.

This file is standard library only, on purpose. It is two things at once:

  * a module the app imports, so tests run the real code in a thread against a temporary folder;
  * source text the app writes into a notebook (`kernel_source`, `pyrun.wrapper_notebook`), so the code
    that runs on serverless is the code the tests ran, not a copy of it.

Nothing here knows about Databricks, HTTP or the app. It reads and writes files under one directory,
which on serverless is a Unity Catalog volume and in a test is a temp folder.

Two pieces:

`CellRuntime` runs one cell in a namespace and returns its outputs in order: text (stdout, stderr, the
value of the last expression), tables (Spark and pandas DataFrames), plots, HTML. The one-shot run and
the session use the same class, so a cell's result looks the same in both.

`Kernel` is the session: a loop that executes numbered commands one at a time in ONE namespace, so a
variable made by one cell is there in the next. Its contract with the app is files:

    cmd/000001.json   the app writes a command. The kernel runs them in order, never one twice.
    out/000001.json   the kernel writes progress (final: false), then the result (final: true).
                      Written to a temporary name and renamed, so a half-written file is never read.
    hb.json           a counter that goes up every beat, so the app can tell the kernel is alive
    ctl/lease.json    a counter the app raises; if it stops rising the app is gone and the kernel ends
    ctl/interrupt     "stop the cell numbered N"
    ctl/stop          "end the session"

Every liveness signal is a COUNTER, not a clock reading. The app and the kernel are different machines
with different clocks; a counter is judged by the reader's own clock ("has it changed in the last N
seconds?"), so skew cannot make a live session look dead or a dead one look alive.
"""
import ast
import base64
import contextlib
import ctypes
import importlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
import traceback

PROTOCOL = 1

DEFAULT_LIMITS = {
    "max_rows": 1000,
    "max_chars": 20_000,
    "max_images": 8,
    "max_image_b64": 1_500_000,
    "max_html": 1_000_000,
    "max_cell_value": 2000,
    "budget": 3_500_000,
}


def _base(name):
    name = str(name).lower()
    for ch in "(<[":
        name = name.split(ch)[0]
    return name.strip()


_PANDAS = {"object": "string", "bool": "boolean", "float64": "double", "float32": "float"}


def _ptype(dtype):
    name = _base(dtype)
    if name in _PANDAS:
        return _PANDAS[name]
    if name.startswith("uint") or name.startswith("int"):
        return "bigint" if name.endswith("64") else "int"
    if name.startswith("datetime"):
        return "timestamp"
    return name or "string"


class _Stream(io.TextIOBase):
    """stdout or stderr, written into the cell's output list in order, so a print between two tables
    appears between them. Consecutive writes to one stream are one block."""

    encoding = "utf-8"

    def __init__(self, rt, name):
        self.rt = rt
        self.name = name

    def writable(self):
        return True

    def write(self, text):
        if not text:
            return 0
        items = self.rt.items
        last = items[-1] if items else None
        if last and last["type"] == "text" and last["stream"] == self.name:
            if len(last["text"]) > 4 * self.rt.limits["max_chars"]:
                last["lost"] = last.get("lost", 0) + len(text)    # a cell that prints forever stays small
            else:
                last["text"] += text
        else:
            items.append({"type": "text", "stream": self.name, "text": text})
        return len(text)

    def flush(self):
        pass


class CellRuntime:
    """Runs cells and collects what they show. One instance per run (one-shot) or per session."""

    def __init__(self, limits=None):
        self.limits = dict(DEFAULT_LIMITS)
        self.limits.update(limits or {})
        self.items = []     # what the cell being run has produced so far, in the order it produced it
        self.srcs = {}      # "<cell N>" -> its lines, so a traceback can show the line that failed
        self.used = 0       # bytes of non-text output spent against the budget
        try:
            import matplotlib   # a headless backend: serverless has no display, and Agg makes PNG bytes
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            # `plt.show()` is where Jupyter and Databricks draw the figure, so that is where it lands
            # among the prints around it. Left open at the end of a cell, a figure is drawn there instead.
            plt.show = lambda *a, **k: self.capture_figs()
        except Exception:
            pass

    # -- small helpers ----------------------------------------------------------------------

    def clip(self, text, lost=0):
        cap = self.limits["max_chars"]
        total = len(text) + lost
        if total <= cap:
            return text
        half = cap // 2
        return text[:half] + "\n... [%d characters not shown] ...\n" % (total - cap) + text[-half:]

    def note(self, text):
        self.items.append({"type": "text", "stream": "notice", "text": text})

    @staticmethod
    def plain(v):
        """A nested value as plain JSON types: a Spark Row is a struct, a list an array, a dict a map."""
        if hasattr(v, "asDict"):
            try:
                v = v.asDict(recursive=True)
            except Exception:
                pass
        if isinstance(v, dict):
            return {str(k): CellRuntime.plain(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [CellRuntime.plain(x) for x in v]
        if isinstance(v, bool) or v is None or isinstance(v, (float, str)):
            return v
        if isinstance(v, int):
            return v if abs(v) < 2 ** 53 else str(v)   # JSON readers round a bigger integer; text does not
        return str(v)

    def sval(self, v):
        if v is None:
            return None   # NULL stays null: an empty string and a NULL are different values
        if isinstance(v, (list, tuple, dict)) or hasattr(v, "asDict"):
            try:
                t = json.dumps(self.plain(v), separators=(",", ":"))
            except Exception:
                t = str(v)
        else:
            t = str(v)
        cap = self.limits["max_cell_value"]
        return t if len(t) <= cap else t[:cap] + "..."

    # -- values -----------------------------------------------------------------------------

    def as_table(self, value):
        """A Spark or pandas DataFrame as a table output, or None for anything else."""
        rows_cap = self.limits["max_rows"]
        kind = type(value).__module__
        if hasattr(value, "collect") and hasattr(value, "columns") and hasattr(value, "limit"):
            rows = value.limit(rows_cap + 1).collect()
            cols = [str(c) for c in value.columns]
            data = [[self.sval(v) for v in r] for r in rows[:rows_cap]]
            try:
                full = [str(t) for _, t in value.dtypes]
                types = [_base(t) for t in full]
            except Exception:
                full, types = [], []
            table = {"type": "table", "columns": cols, "rows": data, "truncated": len(rows) > rows_cap,
                     "types": types}
            if any(t in ("array", "map", "struct") for t in types):
                table["typeTexts"] = full
            return table
        if kind.startswith("pandas") and hasattr(value, "head") and hasattr(value, "columns"):
            head = value.head(rows_cap)
            cols = [str(c) for c in head.columns]
            data = [[self.sval(v) for v in row] for row in head.itertuples(index=False, name=None)]
            try:
                types = [_ptype(t) for t in head.dtypes]
            except Exception:
                types = []
            return {"type": "table", "columns": cols, "rows": data, "truncated": len(value) > rows_cap,
                    "types": types}
        return None

    @staticmethod
    def is_figure(value):
        return (value is not None and type(value).__name__ == "Figure"
                and "matplotlib" in getattr(type(value), "__module__", ""))

    def fig_png(self, fig):
        """PNG bytes as base64. 144 dpi is the Jupyter retina compromise: sharp on a 2x screen, still small."""
        buf = io.BytesIO()
        try:
            fig.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor(), dpi=144)
        except Exception:
            return None
        data = base64.b64encode(buf.getvalue()).decode("ascii")
        return data if len(data) <= self.limits["max_image_b64"] else None

    def add_image(self, fig):
        if sum(1 for i in self.items if i["type"] == "image") >= self.limits["max_images"]:
            return
        png = self.fig_png(fig)
        if png:
            self.items.append({"type": "image", "png": png})
        else:
            self.note("a plot was not shown: it is larger than %d KB as a PNG" % (self.limits["max_image_b64"] // 1000))

    def capture_figs(self):
        """Every figure still open, in order, as PNG. Closed afterwards so the next cell starts clean."""
        try:
            import matplotlib.pyplot as plt
        except Exception:
            return
        for num in list(plt.get_fignums()):
            self.add_image(plt.figure(num))
        # Anything past the cap is closed too: a leak into the next cell is worse than a missing plot.
        try:
            for num in list(plt.get_fignums()):
                plt.close(plt.figure(num))
        except Exception:
            pass

    def add_html(self, html):
        if len(html) > self.limits["max_html"]:
            self.note("HTML output was not shown: %d characters is over the %d limit" % (len(html), self.limits["max_html"]))
        else:
            self.items.append({"type": "html", "html": html})

    @staticmethod
    def html_of(value):
        fn = getattr(value, "_repr_html_", None)
        if callable(fn):
            try:
                html = fn()
            except Exception:
                return None
            if isinstance(html, str) and html.strip():
                return html
        return None

    def show_value(self, value):
        """One value, drawn the way Databricks draws it. Returns False when it is only text."""
        table = self.as_table(value)
        if table is not None:
            self.items.append(table)
            return True
        if self.is_figure(value):
            self.add_image(value)
            try:
                import matplotlib.pyplot as plt
                plt.close(value)
            except Exception:
                pass
            return True
        html = self.html_of(value)
        if html is not None:
            self.add_html(html)
            return True
        return False

    def display(self, value=None, *args, **kwargs):
        if value is None:
            return
        if not self.show_value(value):
            print(value if isinstance(value, str) else repr(value))

    def displayHTML(self, html=None, *args, **kwargs):
        if html is not None:
            self.add_html(str(html))

    def builtins(self):
        """The names a Databricks notebook has that a bare namespace does not."""
        return {"display": self.display, "displayHTML": self.displayHTML}

    # -- running ----------------------------------------------------------------------------

    def frames(self, exc):
        """The traceback, from the user's cells only (the runtime's own frames are noise), with the line."""
        lines = []
        for f in traceback.extract_tb(exc.__traceback__):
            if f.filename in self.srcs:
                where = "  %s, line %d" % (f.filename.strip("<>"), f.lineno)
                if f.name and f.name != "<module>":
                    where += ", in %s" % f.name
                lines.append(where)
                src = self.srcs.get(f.filename)
                if src and 0 < f.lineno <= len(src) and src[f.lineno - 1].strip():
                    lines.append("    " + src[f.lineno - 1].strip())
        return ("Traceback (cells only):\n" + "\n".join(lines) + "\n" if lines else "") + "".join(
            traceback.format_exception_only(type(exc), exc)).strip()

    def finish(self, items):
        """The cell's outputs within what is left of the budget. Text is clipped; a plot, a table or HTML
        that no longer fits is dropped and one sentence says how many."""
        budget = self.limits["budget"]
        out, dropped = [], 0
        for it in items:
            if it["type"] == "text":
                it["text"] = self.clip(it["text"], it.pop("lost", 0))
            size = len(json.dumps(it))
            if self.used + size > budget and it["type"] != "text":
                dropped += 1
                continue
            self.used += size
            out.append(it)
        if dropped:
            out.append({"type": "text", "stream": "notice", "text":
                        "%d output%s not shown: the results reached the %d MB budget for one run. "
                        "Show less per cell, or run fewer cells at once." % (
                            dropped, "" if dropped == 1 else "s", budget // 1000000)})
        return out

    def snapshot(self):
        """What the running cell has printed so far, as text outputs. Safe to call from another thread."""
        try:
            out = []
            for it in list(self.items):
                if it["type"] == "text":
                    out.append({"type": "text", "stream": it["stream"], "text": self.clip(it["text"], it.get("lost", 0))})
            return out
        except Exception:
            return []

    def run(self, index, source, namespace, *, keep_outputs=True, label=None):
        """Run one cell. Always returns an entry: {"i", "ok", "outputs", "error"?, "interrupted"?}.

        `keep_outputs=False` runs the cell only for what it leaves behind (its variables): its outputs are
        not collected against the budget. `label` names the cell in a traceback ("other, cell 2" for a
        cell of a notebook that `%run` pulled in); the default is "cell N".

        Whatever the cell raises, including SystemExit and KeyboardInterrupt, ends the cell and not the
        runtime. Figures left open are drawn at the end, in the order they were made.
        """
        self.items = []
        error = ""
        interrupted = False
        name = "<%s>" % label if label else "<cell %d>" % (index + 1)
        self.srcs[name] = source.splitlines()
        try:
            tree = ast.parse(source, name)
            last = ast.Expression(tree.body.pop().value) if tree.body and isinstance(tree.body[-1], ast.Expr) else None
            with contextlib.redirect_stdout(_Stream(self, "stdout")), contextlib.redirect_stderr(_Stream(self, "stderr")):
                exec(compile(tree, name, "exec"), namespace)
                if last is not None:
                    value = eval(compile(last, name, "eval"), namespace)
                    if value is not None and not self.show_value(value):
                        self.items.append({"type": "text", "stream": "result", "text": repr(value)})
        except KeyboardInterrupt:
            interrupted = True
            error = "Interrupted"
        except BaseException as exc:  # a cell may raise anything, including SystemExit
            error = self.frames(exc)
        try:
            self.capture_figs()
        except BaseException:
            pass
        entry = {"i": index, "ok": not error}
        if keep_outputs:
            entry["outputs"] = self.finish(list(self.items))
        if error:
            entry["error"] = self.clip(error)
        if interrupted:
            entry["interrupted"] = True
        return entry


# -- widgets ------------------------------------------------------------------------------------

WIDGET_TYPES = ("text", "dropdown", "combobox", "multiselect")


class Widgets:
    """`dbutils.widgets` for a session. The app shows what a cell declares and sends the values back.

    Declarations are kept for the life of the session (as in a Databricks notebook) and travel back with every
    result, so the UI always shows the widgets the session really has. Values come from the person, with each
    command; a value the widget does not allow is replaced by its default rather than failing a later cell.
    """

    def __init__(self):
        self.decl = {}
        self.values = {}

    def _add(self, kind, name, default, choices=None, label=None):
        name = str(name)
        if not name or len(name) > 64:
            raise ValueError("a widget name must be 1 to 64 characters")
        default = str(default)
        options = [str(c) for c in (choices or [])][:200]
        if kind in ("dropdown", "multiselect") and default not in options:
            raise ValueError("the default value of widget %s is %r, which is not one of its choices" % (name, default))
        self.decl[name] = {"name": name, "type": kind, "default": default,
                           "label": str(label)[:120] if label else name, "choices": options}

    def text(self, name, defaultValue="", label=None):
        self._add("text", name, defaultValue, None, label)

    def dropdown(self, name, defaultValue, choices, label=None):
        self._add("dropdown", name, defaultValue, choices, label)

    def combobox(self, name, defaultValue, choices, label=None):
        self._add("combobox", name, defaultValue, choices, label)

    def multiselect(self, name, defaultValue, choices, label=None):
        self._add("multiselect", name, defaultValue, choices, label)

    def get(self, name):
        d = self.decl.get(name)
        if d is None:
            raise Exception("InputWidgetNotDefined: no input widget named %s is defined" % name)
        v = self.values.get(name)
        if v is None:
            return d["default"]
        if d["type"] == "dropdown" and v not in d["choices"]:
            return d["default"]
        if d["type"] == "multiselect" and not all(p in d["choices"] for p in v.split(",") if p):
            return d["default"]
        return v

    getArgument = get

    def getAll(self):
        return {n: self.get(n) for n in self.decl}

    def remove(self, name):
        self.decl.pop(str(name), None)

    def removeAll(self):
        self.decl.clear()

    def set_values(self, values):
        self.values = {str(k): str(v) for k, v in values.items()} if isinstance(values, dict) else {}

    def declared(self):
        return [dict(d, value=self.get(n)) for n, d in self.decl.items()]


class _DbUtils:
    """The notebook's `dbutils`, with `widgets` ours and everything else the platform's."""

    def __init__(self, real, widgets):
        self.__dict__["_real"] = real
        self.__dict__["widgets"] = widgets

    def __getattr__(self, name):
        real = self.__dict__["_real"]
        if real is None:
            raise AttributeError("dbutils.%s is not available in this session" % name)
        return getattr(real, name)

    def __dir__(self):
        real = self.__dict__["_real"]
        return sorted(set(dir(real) if real is not None else []) | {"widgets"})



# -- the session --------------------------------------------------------------------------------

def put_json(path, obj):
    """Write a file so a reader sees all of it or none of it: a temporary name, then a rename."""
    tmp = "%s.%d.tmp" % (path, threading.get_ident())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def get_json(path):
    """The file's JSON, or None when it is missing or not (yet) readable."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def seq_name(seq):
    return "%06d.json" % seq


#: Why a session ended. These strings are part of the protocol: the app shows them.
ENDED = {
    "stop": "the session was stopped",
    "idle": "the session ended after being idle",
    "lease": "the session ended because the app stopped asking for it",
    "fatal": "the session stopped because of an internal error",
}


class Kernel:
    """A loop that runs numbered commands, one at a time, in one namespace."""

    def __init__(self, root, namespace=None, *, runtime=None, limits=None, idle_seconds=1200.0,
                 lease_seconds=180.0, poll_seconds=0.1, beat_seconds=1.0, hard_limit=8_000_000,
                 session_id=""):
        self.root = root
        self.rt = runtime or CellRuntime(limits)
        self.ns = {"__name__": "__main__"}
        self.ns.update(self.rt.builtins())
        self.ns.update(namespace or {})
        self.widgets = Widgets()
        self.ns["dbutils"] = _DbUtils(self.ns.get("dbutils"), self.widgets)
        self.idle_seconds = idle_seconds
        self.lease_seconds = lease_seconds
        self.poll_seconds = poll_seconds
        self.beat_seconds = beat_seconds
        self.hard_limit = hard_limit
        self.read_attempts = 30
        self.read_wait = 0.1
        self.session_id = session_id
        self._lock = threading.Lock()
        self._busy = None            # the sequence number being run, or None
        self._busy_since = 0.0
        self._current = None
        self._skip = set()           # numbers the app asked to cancel before they started
        self._exit = None            # why the loop should end; set by the beat thread
        self._beat = 0
        self._seq = 0                # the last command finished
        self._active = time.monotonic()
        self._main_tid = None
        self._interrupted = None    # the cell an interrupt was last sent to
        self._lease_n = None
        self._lease_changed = time.monotonic()
        self._stopped = threading.Event()

    # paths
    def _p(self, *parts):
        return os.path.join(self.root, *parts)

    # -- the heartbeat thread: liveness, interrupts, progress ----------------------------------

    def _interrupt_main(self):
        if self._main_tid is not None:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(self._main_tid), ctypes.py_object(KeyboardInterrupt))

    def _tick(self):
        now = time.monotonic()
        self._beat += 1
        with self._lock:
            busy = self._busy
            put_json(self._p("hb.json"), {
                "protocol": PROTOCOL, "n": self._beat, "state": "busy" if busy else "idle",
                "seq": busy or self._seq, "t": time.time(), "session": self.session_id})
            if busy:
                put_json(self._p("out", seq_name(busy)), {
                    "protocol": PROTOCOL, "seq": busy, "final": False, "n": self._beat,
                    "seconds": round(now - self._busy_since, 2), "outputs": self.rt.snapshot()})
        # the app asks to stop one cell
        req = get_json(self._p("ctl", "interrupt"))
        if req is not None:
            try:
                os.remove(self._p("ctl", "interrupt"))
            except OSError:
                pass
            target = req.get("seq") if isinstance(req, dict) else None
            with self._lock:
                if target is not None and target == self._busy:
                    # A deleted file can still be read for a moment on a volume. One request stops a cell
                    # once: a second interrupt could land in the cleanup of the first.
                    if target != self._interrupted:
                        self._interrupted = target
                        self._interrupt_main()
                elif target is not None and target > self._seq:
                    self._skip.add(target)          # not started yet: it will be cancelled, not run
        # the app asks to end the session
        if os.path.exists(self._p("ctl", "stop")):
            self._ask_exit("stop")
        # the app has stopped asking for the session
        lease = get_json(self._p("ctl", "lease.json"))
        n = lease.get("n") if isinstance(lease, dict) else None
        if n != self._lease_n:
            self._lease_n = n
            self._lease_changed = now
        if now - self._lease_changed > self.lease_seconds:
            self._ask_exit("lease")

    def _ask_exit(self, reason):
        with self._lock:
            if self._exit is None:
                self._exit = reason
            if self._busy:
                self._interrupt_main()

    def _beat_loop(self):
        while not self._stopped.is_set():
            try:
                self._tick()
            except Exception:
                pass   # a failed beat is not a reason to end the session; the next one will try again
            self._stopped.wait(self.beat_seconds)

    # -- the command loop -----------------------------------------------------------------------

    def _finished_up_to(self):
        """The last command with a final result already written (a restarted kernel resumes after it)."""
        seq = 0
        while True:
            doc = get_json(self._p("out", seq_name(seq + 1)))
            if isinstance(doc, dict) and doc.get("final"):
                seq += 1
            else:
                return seq

    def serve(self):
        """Run until told to stop. Returns why it ended (a key of ENDED)."""
        for sub in ("cmd", "out", "ctl"):
            os.makedirs(self._p(sub), exist_ok=True)
        self._main_tid = threading.get_ident()
        self._seq = self._finished_up_to()
        self._tick()
        beat = threading.Thread(target=self._beat_loop, name="kernel-beat", daemon=True)
        beat.start()
        reason = "fatal"
        try:
            while True:
                try:
                    with self._lock:
                        reason_now = self._exit
                    if reason_now:
                        reason = reason_now
                        break
                    seq = self._seq + 1
                    cmd = self._read_command(seq)
                    if cmd is None:
                        if time.monotonic() - self._active > self.idle_seconds:
                            reason = "idle"
                            break
                        time.sleep(self.poll_seconds)
                        continue
                    self._run_command(seq, cmd)
                    self._active = time.monotonic()
                except KeyboardInterrupt:
                    # An interrupt can land in the few instructions between a command being marked as
                    # running and its code starting. That command is then settled as interrupted: it must
                    # not be read again and run a second time. An interrupt aimed at a cell that had just
                    # ended finds nothing running and costs the next cell nothing.
                    current = self._current
                    if self._busy and current:
                        self._settle(current[0], current[1], {"ok": False, "outputs": [],
                                     "error": "Interrupted", "interrupted": True}, current[2])
                    continue
        except BaseException:
            reason = "fatal"
        finally:
            self._stopped.set()
            self._clear_pending_interrupt()
            with self._lock:
                put_json(self._p("hb.json"), {"protocol": PROTOCOL, "n": self._beat + 1, "state": "ended",
                                              "seq": self._seq, "t": time.time(), "reason": reason,
                                              "session": self.session_id})
        return reason

    def _clear_pending_interrupt(self):
        try:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(self._main_tid), None)
        except Exception:
            pass

    def _read_command(self, seq):
        path = self._p("cmd", seq_name(seq))
        if not os.path.exists(path):
            return None
        for _ in range(self.read_attempts):       # an unreadable file is more likely still arriving
            doc = get_json(path)
            if isinstance(doc, dict) and isinstance(doc.get("source"), str):
                return doc
            time.sleep(self.read_wait)
        return {"kind": "invalid", "source": "", "error": "the command file could not be read"}

    def _run_command(self, seq, cmd):
        started = time.monotonic()
        with self._lock:
            skipped = seq in self._skip
            self._skip.discard(seq)
            if not skipped:
                self._current = (seq, cmd, started)
                self._busy = seq
                self._busy_since = started
        try:
            if skipped:
                result = {"ok": False, "outputs": [], "error": "Cancelled before it ran", "interrupted": True}
            else:
                self.rt.items = []
                self.rt.used = 0
                self.widgets.set_values(cmd.get("widgets"))
                result = self._execute(seq, cmd)
        except KeyboardInterrupt:
            result = {"ok": False, "outputs": self.rt.snapshot(), "error": "Interrupted", "interrupted": True}
        except BaseException as exc:
            result = {"ok": False, "outputs": [], "error": "the session could not run this cell: %s" % exc}
        self._settle(seq, cmd, result, started)

    def _settle(self, seq, cmd, result, started):
        """Write the final result and mark the cell finished.

        An interrupt aimed at a cell that was just ending can land anywhere in here. If it broke this
        section the result would never be written and the cell would run a second time, so the section
        is retried until it completes: it is idempotent (the same file, the same state).
        """
        while True:
            try:
                doc = {"protocol": PROTOCOL, "seq": seq, "id": cmd.get("id"), "final": True,
                       "seconds": round(time.monotonic() - started, 2)}
                doc.update({k: v for k, v in result.items() if k != "i"})
                try:
                    doc["widgets"] = self.widgets.declared()   # always: an empty list means "none now"
                except Exception:
                    pass
                doc = self._within_limit(doc)
                with self._lock:
                    put_json(self._p("out", seq_name(seq)), doc)
                    self._busy = None
                    self._seq = seq
                self._clear_pending_interrupt()
                return
            except KeyboardInterrupt:
                continue

    def _within_limit(self, doc):
        """Last resort when the budget still let through a result too large to ship: keep every word."""
        if len(json.dumps(doc)) <= self.hard_limit:
            return doc
        kept = [o for o in doc.get("outputs", []) if o["type"] == "text"]
        if len(kept) != len(doc.get("outputs", [])):
            kept.append({"type": "text", "stream": "notice",
                         "text": "tables, plots and HTML were not shown: the result was too large"})
        doc["outputs"] = kept
        return doc

    def _execute(self, seq, cmd):
        kind = cmd.get("kind", "python")
        if kind == "cells":
            return self._cells(seq, cmd)
        return self._one(seq, cmd, kind)

    def _one(self, seq, cmd, kind, label=None):
        """One command of one kind. Returns the same entry `CellRuntime.run` does."""
        if kind == "python":
            index = cmd.get("index")
            return self.rt.run(index if isinstance(index, int) else seq - 1, cmd["source"], self.ns, label=label)
        if kind == "sh":
            return self._shell(cmd)
        if kind == "pip":
            return self._pip(cmd)
        if kind == "md":
            return {"ok": True, "outputs": [{"type": "markdown", "text": cmd["source"]}]}
        if kind == "invalid":
            return {"ok": False, "outputs": [], "error": cmd.get("error", "the command is not valid")}
        return {"ok": False, "outputs": [], "error": "this session cannot run %s cells" % kind}

    def _cells(self, seq, cmd):
        """The cells of another notebook (`%run`), in order, in this namespace, stopping at the first failure.

        The app chose these cells and wrote them into the command; the session never goes and fetches code.
        """
        merged = [{"type": "text", "stream": "notice", "text": str(n)[:400] + "\n"} for n in (cmd.get("notes") or [])[:20]]
        for position, sub in enumerate(cmd.get("cells") or []):
            if not isinstance(sub, dict) or not isinstance(sub.get("source"), str):
                continue
            name = str(sub.get("name") or "cell %d" % (position + 1))[:120]
            self.rt.items = []
            res = self._one(seq, sub, sub.get("kind", "python"), label=name)
            merged.extend(res.get("outputs") or [])
            if not res.get("ok", False):
                out = {"ok": False, "outputs": merged, "error": "in %s: %s" % (name, res.get("error", "failed"))}
                if res.get("interrupted"):
                    out["interrupted"] = True
                return out
        return {"ok": True, "outputs": merged}

    # -- subprocesses: %sh and %pip ----------------------------------------------------------

    def _spawn(self, argv, timeout):
        """Run a program with its output written into the cell as it arrives. Returns (exit code, timed out).

        Stdin is closed (nothing can ask a question), the program leads its own process group so that stopping
        it stops what it started, and an interrupt or a timeout kills the whole group.
        """
        out, err = _Stream(self.rt, "stdout"), _Stream(self.rt, "stderr")
        lock = threading.Lock()
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, errors="replace", start_new_session=True)

        def pump(pipe, sink):
            for line in iter(pipe.readline, ""):
                with lock:
                    sink.write(line)

        threads = [threading.Thread(target=pump, args=(proc.stdout, out), daemon=True),
                   threading.Thread(target=pump, args=(proc.stderr, err), daemon=True)]
        for t in threads:
            t.start()

        def kill():
            try:
                os.killpg(proc.pid, 9)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        deadline = time.monotonic() + timeout
        timed_out = False
        stopped = None
        try:
            while proc.poll() is None:
                if time.monotonic() > deadline:
                    timed_out = True
                    kill()
                    break
                time.sleep(0.05)
        except BaseException as exc:
            stopped = exc
        # Whatever ended the wait, the program is killed and reaped before going on, and a further
        # interrupt landing in this cleanup does not skip it.
        while True:
            try:
                if stopped is not None:
                    kill()
                proc.wait()
                for t in threads:
                    t.join(2.0)
                break
            except BaseException as again:
                stopped = stopped or again
        if stopped is not None:
            raise stopped
        return proc.returncode, timed_out

    def _program(self, argv, timeout):
        code, timed_out = self._spawn(argv, timeout)
        entry = {"ok": code == 0 and not timed_out, "outputs": self.rt.finish(list(self.rt.items))}
        if timed_out:
            entry["error"] = "it did not finish in %d seconds and was stopped" % timeout
        elif code != 0:
            entry["error"] = "it exited with status %s" % code
        return entry

    def _timeout(self, cmd, default):
        t = cmd.get("timeout")
        return int(t) if isinstance(t, (int, float)) and 1 <= t <= 3600 else default

    def _shell(self, cmd):
        if not cmd["source"].strip():
            return {"ok": False, "outputs": [], "error": "there is no command to run"}
        shell = shutil.which("bash") or "/bin/sh"
        return self._program([shell, "-c", cmd["source"]], self._timeout(cmd, 600))

    def _pip(self, cmd):
        try:
            args = shlex.split(cmd["source"])
        except ValueError as exc:
            return {"ok": False, "outputs": [], "error": "could not read the pip arguments: %s" % exc}
        if not args:
            return {"ok": False, "outputs": [], "error": "pip needs a command, for example: %pip install pandas"}
        entry = self._program([sys.executable, "-m", "pip", "--disable-pip-version-check", "--no-input"] + args,
                              self._timeout(cmd, 1800))
        if args[0] in ("install", "uninstall") and entry["ok"]:
            importlib.invalidate_caches()
            entry["outputs"].append({"type": "text", "stream": "notice", "text":
                                     "A module that was imported before this keeps the version it has. "
                                     "Restart the session to load a new one.\n"})
        return entry
