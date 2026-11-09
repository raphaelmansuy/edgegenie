"""Building the `session/prompt` content array: one text block, plus images when the agent takes them.

This is a pure function over facts both runtimes already hold, and it lives on its own because there are
two runtimes and two prompt paths — four call sites that would otherwise each have their own idea of what
a prompt looks like. It was exactly that duplication that kept the wire text-only after `opencode` started
advertising `promptCapabilities.image` (spec 009 [D7], [D11]).

ACP's rule, quoted because it is the whole design: an agent MUST support `text` and `resource_link`;
everything else is opted in per agent, and "Agents reject others with `-32602`". So the capability is asked
before an image block is added, and an image the agent cannot take becomes a stated omission rather than a
crash or a silence.
"""

from __future__ import annotations

from typing import Any

#: What an agent must accept, always. No capability check, because the spec says so.
BASELINE = ("text", "resource_link")


def prompt_blocks(text: str, images: list[dict[str, Any]] | None,
                  capabilities: Any = None) -> list[dict[str, Any]]:
    """The `prompt` array for `session/prompt`.

    `images` are `{data: <base64>, mimeType: <str>, name: <str>}` — bytes that were already validated and
    stored by the blob stage. This function decides only their transport.

    When the agent does not advertise `image`, the pictures become ONE text block naming them, so the model
    is told what it did not receive. That is the same rule as an unreadable attachment: never let the model
    believe it saw something it did not (spec 009 [AFC-15]).
    """
    blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
    if not images:
        return blocks

    if capabilities is not None and getattr(capabilities, "images", False):
        for img in images:
            block: dict[str, Any] = {
                "type": "image",
                "mimeType": img.get("mimeType") or "image/png",
                "data": img.get("data", ""),
            }
            # `uri` is optional in the spec and useful to an agent that wants to name the source.
            if img.get("uri"):
                block["uri"] = img["uri"]
            blocks.append(block)
        return blocks

    names = ", ".join(f"{i.get('name') or 'image'} ({i.get('mimeType') or 'image'})" for i in images)
    blocks.append({
        "type": "text",
        "text": (
            f"[image omitted: {names} — the agent this session runs on does not advertise "
            f"promptCapabilities.image, so the picture could not be sent. Say that you cannot see it "
            f"rather than guessing at its contents.]"
        ),
    })
    return blocks
