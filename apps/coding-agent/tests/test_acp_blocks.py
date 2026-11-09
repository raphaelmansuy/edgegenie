"""The prompt content array: text always, images only when the agent said it can take them.

ACP's rule is the design: an agent MUST support `text` and opts in to everything else, and "Agents reject
others with `-32602`". So this is the one place that decides what a prompt is made of, and the tests below
are the reason the wire stopped being text-only (spec 009 [D7]).
"""

from __future__ import annotations

from dataclasses import dataclass

from api.adapters.acp.blocks import prompt_blocks

IMG = {"data": "iVBORw0KGgo=", "mimeType": "image/png", "name": "chart.png"}


@dataclass
class Caps:
    images: bool = False


def test_text_only_when_there_is_nothing_to_send():
    assert prompt_blocks("hello", None) == [{"type": "text", "text": "hello"}]
    assert prompt_blocks("hello", []) == [{"type": "text", "text": "hello"}]


def test_an_image_block_is_added_when_the_agent_advertises_it():
    """The measured shape from opencode 1.18.19: `promptCapabilities: {image: true}`."""
    blocks = prompt_blocks("what is this", [IMG], Caps(images=True))
    assert blocks[0] == {"type": "text", "text": "what is this"}
    assert blocks[1] == {"type": "image", "mimeType": "image/png", "data": "iVBORw0KGgo="}
    # No `name` key: ACP's ImageContent is {type, data, mimeType, uri?} and an extra key is not it.
    assert "name" not in blocks[1]


def test_the_bytes_are_verbatim():
    blocks = prompt_blocks("x", [IMG], Caps(images=True))
    assert blocks[1]["data"] == IMG["data"]


def test_a_uri_is_carried_when_the_caller_gave_one():
    blocks = prompt_blocks("x", [{**IMG, "uri": "file:///tmp/a.png"}], Caps(images=True))
    assert blocks[1]["uri"] == "file:///tmp/a.png"


def test_no_image_block_when_the_agent_does_NOT_advertise_it():
    """An unadvertised block is rejected with -32602, so it must not be sent."""
    blocks = prompt_blocks("what is this", [IMG], Caps(images=False))
    # Two text blocks: the prompt, then the omission. No image block at all.
    assert [b["type"] for b in blocks] == ["text", "text"]
    assert blocks[0]["text"] == "what is this"
    assert "image omitted" in blocks[1]["text"]


def test_the_omission_names_the_file_and_the_reason():
    """[AFC-15] applied to the wire: the model must be told what it did not receive."""
    text = prompt_blocks("x", [IMG], Caps(images=False))[1]["text"]
    assert "chart.png" in text
    assert "image/png" in text
    assert "promptCapabilities.image" in text
    assert "guessing" in text


def test_several_images_become_one_omission_sentence_not_one_each():
    many = [{"data": "a", "mimeType": "image/png", "name": "a.png"},
            {"data": "b", "mimeType": "image/jpeg", "name": "b.jpg"}]
    blocks = prompt_blocks("x", many, Caps(images=False))
    assert [b["type"] for b in blocks] == ["text", "text"]
    assert "a.png" in blocks[1]["text"] and "b.jpg" in blocks[1]["text"]


def test_several_images_become_several_blocks_when_supported():
    many = [{"data": "a", "mimeType": "image/png", "name": "a.png"},
            {"data": "b", "mimeType": "image/jpeg", "name": "b.jpg"}]
    blocks = prompt_blocks("x", many, Caps(images=True))
    assert [b["type"] for b in blocks] == ["text", "image", "image"]
    assert blocks[2]["mimeType"] == "image/jpeg"


def test_unknown_capabilities_are_treated_as_no_images():
    """`None` is a runtime that has not been asked. Sending an unasked block is a protocol error, so the
    safe default is the omission — not a guess."""
    blocks = prompt_blocks("x", [IMG], None)
    assert [b["type"] for b in blocks] == ["text", "text"]
    assert "image omitted" in blocks[1]["text"]


def test_a_missing_mime_type_falls_back_to_png():
    blocks = prompt_blocks("x", [{"data": "abc"}], Caps(images=True))
    assert blocks[1]["mimeType"] == "image/png"
