"""The context the agent is TOLD, merged from labelled sources. Pure. `[R-17]`, `[C13]`, `[C14]`.

The gap this closes. Genie Code *"can also automatically discover AGENTS.md and CLAUDE.md files within
your project"* and offers user and workspace instructions. OpenGenie **wrote** an `AGENTS.md` into the
agent's working directory (`adapters/acp/agent_config.py:177`) and read **none** of the user's own. So
every conversation started by rediscovering what the team already knew — the largest accuracy lever left,
and the cheapest to pull.

**Three sources, one precedence rule:**

    workspace instructions   shared, authored by an admin
    personal instructions    the user's own
    AGENTS.md                found by walking up from the session's folder
    ────────────────────────
    the session's SCOPE      generated from the fence. ALWAYS LAST, ALWAYS WINS.

**Why the scope block must win.** An instruction is text a person wrote; the fence is a decision the app
made. If an `AGENTS.md` said *"you may write to /Shared"*, the only defensible behaviour is that the
fence still refuses — and the agent must have been told that, or it will try and be refused for a reason
it thinks it was permitted. So the merged text ends with the fence, unconditionally.

**Why the merge is pure and the reading is not.** Reading needs a token and a workspace client
(`services/instructions.py`); merging is a function of strings, so the *precedence* is testable without a
workspace. That is the same split `domain/context.py` (parse) and `services/context.py` (resolve) use.

**A source that could not be read is reported, never dropped.** An agent that did not see the team's
rules must not answer as if it had; `Missing` travels with the text so the transcript can say so.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: How much of one source to include. A 5 000-line instructions file would crowd out the task, so each
#: source is capped and the cap is REPORTED — the same rule the payload window follows ([R-3]).
MAX_CHARS_EACH = 4_000
#: Across all sources. Beyond this the rules stop being context and become the prompt.
MAX_CHARS_TOTAL = 12_000

Kind = Literal["workspace", "personal", "agents_md"]


@dataclass(frozen=True, slots=True)
class Source:
    """One block of configured context, with what a reader needs to judge it."""

    kind: Kind
    text: str
    #: Where it came from: a path, so the transcript can link to it.
    path: str = ""
    #: Who wrote it, when the platform says. An admin's rule and the user's own are not equal.
    author: str = ""
    truncated: bool = False

    @property
    def label(self) -> str:
        return {
            "workspace": "the workspace's instructions",
            "personal": "your instructions",
            "agents_md": "AGENTS.md in your folder",
        }[self.kind]


@dataclass(frozen=True, slots=True)
class Missing:
    """A source that should have been read and was not, with the reason. Reported, never silent."""

    kind: Kind
    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class Merged:
    text: str
    used: tuple[Source, ...]
    missing: tuple[Missing, ...]

    @property
    def empty(self) -> bool:
        return not self.text.strip()


def clip(text: str, limit: int = MAX_CHARS_EACH) -> tuple[str, bool]:
    """Keep the start of a long source and SAY it was cut.

    The start, not the middle: instructions open with their scope ("these rules apply to pipelines"). A
    silent cut is the defect `[R-3]` fixed for tool results, applied to the one other place a person's
    words reach the model.
    """
    body = (text or "").strip()
    if len(body) <= limit:
        return body, False
    return body[:limit].rstrip() + "\n\n[... this file is longer; its first part is shown]", True


def merge(
    sources: list[Source],
    *,
    scope: str,
    missing: list[Missing] | None = None,
    budget: int = MAX_CHARS_TOTAL,
) -> Merged:
    """Render the labelled blocks, ending with the scope. Pure and total.

    Order is the specification: workspace, personal, `AGENTS.md` — then the scope, which cannot be
    overridden no matter what the others say.
    """
    order = {"workspace": 0, "personal": 1, "agents_md": 2}
    kept: list[Source] = []
    parts: list[str] = []
    spent = 0

    for src in sorted(sources, key=lambda s: order[s.kind]):
        body, cut = clip(src.text)
        if not body:
            continue
        block = f"## Context from {src.label}" + (f" ({src.author})" if src.author else "") + "\n" + body
        if spent + len(block) > budget:
            # Out of room: stop rather than truncate a second time. What is left out is visible because
            # `used` lists what went in, and a reader can compare it with what they expected.
            break
        parts.append(block)
        kept.append(Source(src.kind, body, src.path, src.author, cut))
        spent += len(block)

    if scope.strip():
        parts.append("## This session's scope (enforced by the tool server, not by you)\n" + scope.strip())

    return Merged("\n\n".join(parts).strip(), tuple(kept), tuple(missing or ()))
