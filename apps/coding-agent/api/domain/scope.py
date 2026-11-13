"""The write fence: what a session may touch. Pure and total — every target is classified.

Policy adapters for legacy editor callers. Agent authorization uses the same pure policy package;
editor saves outside the working folder retain their explicit human approval flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

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


# Compatibility exports for editor callers; implementation lives in one policy module.
from .policy.paths import inside as _inside, normalize as _norm
from .policy.sql import classify, check_scope
from .policy.verdict import ActionClass


def classify_sql(sql: str) -> Action:
    cls = classify(sql).action
    return {ActionClass.READ: Action.READ, ActionClass.CHANGE: Action.WRITE,
            ActionClass.IRREVERSIBLE: Action.DESTRUCTIVE}.get(cls, Action.DESTRUCTIVE)


def check_sql(scope: Scope, sql: str) -> Decision:
    error = check_scope(sql, [scope.schema] if scope.schema else [])
    action = classify_sql(sql)
    if error:
        return Decision(Verdict.DENY, action, sql[:160], error)
    return Decision(Verdict.ASK if action is Action.DESTRUCTIVE else Verdict.ALLOW, action, sql[:160])


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
