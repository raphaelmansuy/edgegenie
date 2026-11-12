"""Declarative hooks: a platform team's rules, evaluated where the fence already is. Pure. `[R-13]`.

The gap this closes. OpenGenie has exactly one hook point and it is hard-coded: the fence in the tool
server, plus the supervisor after a turn. There is nowhere for a *workspace* to say "after every notebook
write, refuse `DELETE` on `main.gold`" or "before any `dbx_run_sql`, check this". Cursor and Claude Code
both expose the agent loop to a platform team (33 hook events in Claude Code); a governed product that
decides the rules for you is a product whose rules you cannot change.

**Why a rule and not a script.** A hook that runs an arbitrary program inside the tool server is a second
identity inside the process that holds the user's token, needing its own timeout, failure mode and audit
row. A declarative rule inherits all four from the fence: the same place, the same reason sentence, the same
audit row. `then: run` is specified and gated behind an administrator (`[E-16]`), because it is a program —
but the *declaration* is a rule, which is what makes the common case safe.

**The expression language is deliberately tiny.** `equals`, `starts_with`, `matches`, `in`, `not`, `all`,
`any` over the tool name and its named arguments. It cannot call Python, so it cannot exfiltrate. That is
the whole reason it is not `eval`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal


class RuleError(ValueError):
    """A rule that cannot be understood. Reported once; it never disables the fence."""


@dataclass(frozen=True, slots=True)
class Predicate:
    """One condition over a tool call. A closed set of operators, by design."""

    op: Literal["equals", "starts_with", "matches", "in", "contains", "not", "all", "any"]
    field: str = ""
    value: Any = None
    of: tuple["Predicate", ...] = ()

    def test(self, call: "Call") -> bool:
        """Total: a field that is absent makes the condition False, never an exception."""
        if self.op == "not":
            return not self.of[0].test(call)
        if self.op == "all":
            return all(p.test(call) for p in self.of)
        if self.op == "any":
            return any(p.test(call) for p in self.of)
        got = call.get(self.field)
        if got is None:
            return False
        text = str(got)
        if self.op == "equals":
            return text == str(self.value)
        if self.op == "starts_with":
            return text.startswith(str(self.value))
        if self.op == "contains":
            return str(self.value) in text
        if self.op == "in":
            return text in [str(v) for v in (self.value or [])]
        if self.op == "matches":
            try:
                return re.search(str(self.value), text, re.I) is not None
            except re.error:
                # A bad pattern is a rule error, not a crash: the caller logs it once and the fence stands.
                return False
        raise RuleError(f"unknown operator {self.op!r}")


@dataclass(frozen=True, slots=True)
class Call:
    """What a rule is evaluated against: the tool's name and its arguments, flattened."""

    tool: str
    args: dict[str, Any] = field(default_factory=dict)

    def get(self, field_name: str) -> Any:
        if field_name in ("tool", "name"):
            return self.tool
        return self.args.get(field_name)


@dataclass(frozen=True, slots=True)
class Rule:
    name: str
    on: Literal["before_tool", "after_tool"]
    #: A tool name, or a regex when it starts with `^`.
    tool: str = ""
    when: Predicate | None = None
    then: Literal["refuse", "allow", "run"] = "refuse"
    say: str = ""
    run: tuple[str, ...] = ()

    def matches(self, call: Call, phase: str) -> bool:
        if self.on != phase:
            return False
        if self.tool.startswith("^"):
            try:
                if re.search(self.tool, call.tool) is None:
                    return False
            except re.error:
                return False
        elif self.tool and self.tool != call.tool:
            return False
        return self.when is None or self.when.test(call)


@dataclass(frozen=True, slots=True)
class Verdict:
    """What happened, with the sentence a user reads and the rule's name for the audit row."""

    outcome: Literal["allow", "refuse", "run"]
    rule: str = ""
    say: str = ""
    run: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        return self.outcome == "allow"


ALLOW = Verdict("allow")


def evaluate(rules: list[Rule], call: Call, *, phase: str = "before_tool",
             allow_run: bool = False) -> Verdict:
    """The first matching rule wins. Total: an unevaluable rule is skipped, and the fence still stands.

    `allow_run=False` refuses a `then: run` rule rather than executing it — a program inside the tool
    server is an administrator's decision (`[E-16]`), and the default must be "no".
    """
    for rule in rules:
        try:
            if not rule.matches(call, phase):
                continue
        except Exception:  # noqa: BLE001 - one bad rule must not decide the fence
            continue
        if rule.then == "allow":
            return Verdict("allow", rule.name)
        if rule.then == "run":
            if not allow_run:
                return Verdict("refuse", rule.name,
                               f"{rule.say or 'this rule needs to run a program'} "
                               "(running a hook program needs an administrator).")
            return Verdict("run", rule.name, rule.say, rule.run)
        return Verdict("refuse", rule.name, rule.say or f"this call is refused by the rule {rule.name}.")
    return ALLOW


# -- parsing, so a workspace can write YAML rather than Python ------------------------------------
def parse(raw: Any) -> list[Rule]:
    """Rules from the shape a `hooks.yaml` yields. Unparseable rules are ERRORS, not omissions.

    A hook that silently disappears is a rule a platform team believes is enforcing something. So a bad
    file raises with the rule's name, and the caller reports it once (`[E-16]`).
    """
    if not raw:
        return []
    if not isinstance(raw, list):
        raise RuleError("hooks must be a list of rules")
    out: list[Rule] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise RuleError(f"rule {i} is not a mapping")
        name = str(item.get("name") or "").strip()
        if not name:
            raise RuleError(f"rule {i} has no name")
        if name in seen:
            raise RuleError(f"rule {name!r} is declared twice")
        seen.add(name)
        on = str(item.get("on") or "before_tool")
        if on not in ("before_tool", "after_tool"):
            raise RuleError(f"rule {name!r}: `on` must be before_tool or after_tool, not {on!r}")
        then = str(item.get("then") or "refuse")
        if then not in ("refuse", "allow", "run"):
            raise RuleError(f"rule {name!r}: `then` must be refuse, allow or run")
        match = item.get("match") or {}
        tool = str(match.get("tool") or "") if isinstance(match, dict) else str(match)
        run = item.get("run") or ()
        if then == "run" and not run:
            raise RuleError(f"rule {name!r}: `then: run` needs a `run` program")
        out.append(Rule(
            name=name, on=on, tool=tool, when=_predicate(item.get("when"), name), then=then,
            say=str(item.get("say") or ""),
            run=tuple(str(x) for x in run) if isinstance(run, (list, tuple)) else (str(run),),
        ))
    return out


def _predicate(raw: Any, rule: str) -> Predicate | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise RuleError(f"rule {rule!r}: `when` must be a mapping")
    if "not" in raw:
        return Predicate("not", of=(_predicate(raw["not"], rule) or Predicate("equals"),))
    for key in ("all", "any"):
        if key in raw:
            return Predicate(key, of=tuple(_predicate(x, rule) or Predicate("equals") for x in raw[key]))
    for op in ("equals", "starts_with", "contains", "in", "matches"):
        if op in raw:
            spec = raw[op]
            if isinstance(spec, dict):
                field_name = str(spec.get("field") or "")
                return Predicate(op, field=field_name, value=spec.get("value"))
            return Predicate(op, field="", value=spec)
    raise RuleError(f"rule {rule!r}: `when` has no known operator (equals, starts_with, matches, in, "
                    f"contains, not, all, any)")
