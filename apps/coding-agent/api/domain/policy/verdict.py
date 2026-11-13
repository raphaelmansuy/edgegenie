"""One autonomy verdict table. Unknown actions never acquire authority."""
from enum import Enum


class Mode(str, Enum):
    PLAN = "plan"
    REVIEW = "review"
    AUTO = "auto"


class ActionClass(str, Enum):
    READ = "read"
    RUN_READ = "run_read"
    CHANGE = "change"
    RUN_EFFECT = "run_effect"
    IRREVERSIBLE = "irreversible"
    UNKNOWN = "unknown"


def verdict(mode: Mode, inside_fence: bool, cls: ActionClass) -> str:
    if cls is ActionClass.UNKNOWN:
        return "deny"
    if cls in (ActionClass.READ, ActionClass.RUN_READ):
        return "allow"
    if mode is Mode.PLAN or not inside_fence:
        return "deny"
    if cls is ActionClass.IRREVERSIBLE or mode is Mode.REVIEW:
        return "ask"
    return "allow"
