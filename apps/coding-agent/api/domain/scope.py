"""The write fence: what a session may touch. Pure and total — every target is classified.

This is a policy function, not the boundary itself. The boundary is that the tool server
only receives requests that passed here, and that approval is required for anything the
rules cannot prove safe. See specs/001 04 and 09.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

DESTRUCTIVE = re.compile(r"\b(drop\s+(table|schema|view|database)|truncate|delete\s+from)\b", re.I)
WRITE_SQL = re.compile(r"\b(create|replace|insert|update|merge|alter|optimize|vacuum|grant|revoke)\b", re.I)
_TABLE_RE = re.compile(
    r"\b(?:table|view|schema|database)\s+(?:if\s+not\s+exists\s+|or\s+replace\s+)?"
    r"([\w.$`\"]+)",
    re.I,
)
_FROM_RE = re.compile(r"\b(?:from|into|update|join)\s+([\w.$`\"]+)", re.I)


class Action(str, Enum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    RUN = "run"
    CREATE_APP = "create_app"


class Verdict(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class Scope:
    folder: str
    schema: str | None
    job_prefix: str
    app_prefix: str
    instance_prefix: str

    @staticmethod
    @staticmethod
    def for_session(session_id: str, folder: str, schema: str | None) -> Scope:
        short = session_id[:8]
        return Scope(
            # An empty folder stays empty. `"".rstrip("/") + "/"` is "/", which would make the
            # scope look like a root folder rather than "no folder at all" — and a root folder is
            # a wildcard, so the distinction matters for the fence.
            folder=(folder.rstrip("/") + "/") if folder.strip("/") else "",
            schema=schema,
            job_prefix=f"agent_{short}_",
            app_prefix=f"agent-{short}-",
            instance_prefix=f"agent-{short}-",
        )


@dataclass(frozen=True, slots=True)
class Decision:
    verdict: Verdict
    action: Action
    target: str
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.verdict is Verdict.ALLOW


def _norm(path: str) -> str:
    p = path.replace("\\", "/").strip("`\"'")
    while "//" in p:
        p = p.replace("//", "/")
    return p


def _inside(path: str, folder: str) -> bool:
    p = _norm(path)
    if ".." in p.split("/"):
        return False
    f = _norm(folder)
    # An empty folder means "there is no writable folder", NOT "every folder is writable".
    # `"anything".startswith("")` is True, so without this guard a session-less save would be
    # classified as inside the fence and silently allowed — a real widening of the write boundary.
    if not f or f == "/":
        return False
    return p.startswith(f) and len(p) > len(f) - 1


def classify_sql(sql: str) -> Action:
    if DESTRUCTIVE.search(sql):
        return Action.DESTRUCTIVE
    if WRITE_SQL.search(sql):
        return Action.WRITE
    return Action.READ


def sql_targets(sql: str) -> list[str]:
    return [t.strip('`"') for t in _TABLE_RE.findall(sql) + _FROM_RE.findall(sql)]


def check_sql(scope: Scope, sql: str) -> Decision:
    action = classify_sql(sql)
    if action is Action.READ:
        return Decision(Verdict.ALLOW, Action.READ, "")
    if action is Action.DESTRUCTIVE:
        return Decision(
            Verdict.ASK,
            Action.DESTRUCTIVE,
            " ".join(sql.split())[:160],
            "destructive SQL always needs a human",
        )
    targets = sql_targets(sql)
    if not scope.schema:
        return Decision(
            Verdict.ASK, action, ", ".join(targets)[:160], "this session has no writable schema"
        )
    outside = [t for t in targets if not t.lower().startswith(scope.schema.lower() + ".")]
    if outside:
        return Decision(
            Verdict.ASK, action, ", ".join(outside)[:160], f"outside the writable schema {scope.schema}"
        )
    return Decision(Verdict.ALLOW, action, ", ".join(targets)[:160])


def check_path(scope: Scope, path: str) -> Decision:
    if _inside(path, scope.folder):
        return Decision(Verdict.ALLOW, Action.WRITE, _norm(path))
    reason = (f"outside {scope.folder}" if scope.folder
              else "no session is open, so there is no working folder to save into")
    return Decision(Verdict.ASK, Action.WRITE, _norm(path)[:160], reason)


def check_job(scope: Scope, name: str) -> Decision:
    if name.startswith(scope.job_prefix):
        return Decision(Verdict.ALLOW, Action.RUN, name)
    return Decision(
        Verdict.ASK, Action.RUN, name[:160], f"job names in this session start with {scope.job_prefix}"
    )


def check_app(scope: Scope, name: str) -> Decision:
    if name.startswith(scope.app_prefix):
        return Decision(Verdict.ALLOW, Action.CREATE_APP, name)
    return Decision(
        Verdict.ASK,
        Action.CREATE_APP,
        name[:160],
        f"app names in this session start with {scope.app_prefix}",
    )


def check_instance(scope: Scope, name: str) -> Decision:
    if name.startswith(scope.instance_prefix):
        return Decision(Verdict.ALLOW, Action.WRITE, name)
    return Decision(
        Verdict.ASK,
        Action.WRITE,
        name[:160],
        f"instance names in this session start with {scope.instance_prefix}",
    )


def describe(scope: Scope) -> dict:
    return {
        "folder": scope.folder,
        "schema": scope.schema,
        "jobPrefix": scope.job_prefix,
        "appPrefix": scope.app_prefix,
        "instancePrefix": scope.instance_prefix,
    }
