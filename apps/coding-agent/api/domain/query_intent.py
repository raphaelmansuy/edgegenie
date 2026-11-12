"""Conservative query-specific completion goals; never infer them from attached SQL text."""

import re

_OBJECT = r"(?:(?:the|this|attached|open|current|my|a|an|updated|modified|SQL)\s+){0,5}(?:query|SQL|it)\b"
_EDIT = re.compile(
    r"\b(?:write|create|build|generate|fix|update|modify|rewrite|optimi[sz]e|replace|edit|change)\s+"
    + _OBJECT,
    re.I,
)
_RUN = re.compile(r"\b(?:run|execute)\s+" + _OBJECT, re.I)


def query_goals(text: str) -> tuple[bool, bool]:
    return (
        bool(_EDIT.search(text)) and not forbidden_query_action(text, "update"),
        bool(_RUN.search(text)) and not forbidden_query_action(text, "run"),
    )


def query_explanation_only(text: str) -> bool:
    if any(query_goals(text)):
        return False
    return bool(
        re.match(
            r"\s*(?:please\s+)?(?:explain|summari[sz]e|describe|review|walk\s+me\s+through|"
            r"what\s+does|what\s+is\s+(?:this|the\s+query)|how\s+does)\b",
            text,
            re.I,
        )
    )


def forbidden_query_action(prompt: str, action: str) -> bool:
    verbs = r"(?:run|execute)" if action == "run" else r"(?:edit|change|update|modify|rewrite|replace)"
    without = r"running|executing" if action == "run" else r"editing|changing|modifying"
    coordinated = r"(?:(?:run|execute|edit|change|update|modify|rewrite|replace)\s+(?:or|and)\s+)*"
    return bool(
        re.search(r"\b(?:do\s+not|don't|never)\s+(?:ever\s+)?" + coordinated + verbs + r"\b", prompt, re.I)
        or re.search(r"\bwithout\s+(?:" + without + r")\b", prompt, re.I)
        or re.search(
            r"\bwithout\s+(?:using\s+)?tools?\b|\bno\s+tools\b|\bjust\s+(?:explain|describe|review)\b",
            prompt,
            re.I,
        )
    )
