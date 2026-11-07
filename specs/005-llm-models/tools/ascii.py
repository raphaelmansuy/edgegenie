#!/usr/bin/env python3
"""ASCII drawing primitives shared by the spec diagram generators.

Every box measures its own content, so a border cannot drift: alignment is a property of the
construction rather than of the author's eye. `apps/coding-agent/web/scripts/verify-spec-ascii.mjs`
parses the output and fails when the property is broken.

Widths: this text is ASCII plus box drawing plus a few symbols, all single-cell in a terminal, so
`len()` is the display width. Wide glyphs are deliberately not used; if one is ever needed, `cell()`
is the one place to teach.
"""
from __future__ import annotations

H, V = "─", "│"
TL, TR, BL, BR = "┌", "┐", "└", "┘"
LT, RT, TT, BT = "├", "┤", "┬", "┴"
ARROW_D, ARROW_R = "▼", "▶"


def cell(s: str) -> int:
    return len(s)


class Box:
    """A rectangle that measures its content.

    A line is either text, `None` (a horizontal rule), or a nested `Box` (drawn inset).
    """

    def __init__(self, title: str = "", right: str = "", pad: int = 2, min_w: int = 20) -> None:
        self.title, self.right, self.pad, self.min_w = title, right, pad, min_w
        self.lines: list[str | None | Box] = []

    def line(self, text: str = "") -> "Box":
        self.lines.append(text)
        return self

    def rule(self) -> "Box":
        self.lines.append(None)
        return self

    def add(self, box: "Box") -> "Box":
        self.lines.append(box)
        return self

    def _body_width(self) -> int:
        w = 0
        for item in self.lines:
            if item is None:
                continue
            if isinstance(item, Box):
                w = max(w, item.inner + self.pad * 2)
            else:
                w = max(w, cell(item) + self.pad * 2)
        return w

    def _head_width(self) -> int:
        left = cell(f" {self.title} ") if self.title else 0
        right = cell(f" {self.right} ") if self.right else 0
        gap = 4 if (self.title and self.right) else 2
        return left + right + gap

    @property
    def inner(self) -> int:
        return max(self._body_width(), self._head_width(), self.min_w)

    def render(self, indent: int = 0) -> list[str]:
        w = self.inner
        pre = " " * indent
        out = [pre + TL + H * w + TR]
        if self.title or self.right:
            left = f" {self.title} " if self.title else ""
            right = f" {self.right} " if self.right else ""
            out.append(pre + V + left + " " * max(w - cell(left) - cell(right), 0) + right + V)
            out.append(pre + LT + H * w + RT)
        for item in self.lines:
            if item is None:
                out.append(pre + LT + H * w + RT)
            elif isinstance(item, Box):
                for sub in item.render(indent=0):
                    body = " " * self.pad + sub
                    out.append(pre + V + body + " " * max(w - cell(body), 0) + V)
            else:
                body = " " * self.pad + item
                out.append(pre + V + body + " " * max(w - cell(body), 0) + V)
        out.append(pre + BL + H * w + BR)
        return out


def uniform(boxes: list[Box]) -> list[Box]:
    """Give several boxes one shared width, so a vertical stack reads as a single column."""
    w = max(b.inner for b in boxes)
    for b in boxes:
        b.min_w = w
    return boxes


def stack(boxes: list[Box], links: list[str], indent: int = 0, center: bool = False) -> list[str]:
    """Boxes in a column, with a labelled connector between each pair.

    The connector sits on the boxes' shared centre column and its label starts one space right of the
    vertical, so a label can never collide with a border.
    """
    uniform(boxes)
    w = max(b.inner for b in boxes)
    mid = indent + (w // 2 if not center else w // 2)
    out: list[str] = []
    for i, b in enumerate(boxes):
        out.extend(b.render(indent=indent))
        if i == len(boxes) - 1:
            break
        label = links[i] if i < len(links) else ""
        out.append(" " * mid + V + (f" {label}" if label else ""))
        out.append(" " * mid + ARROW_D)
    return out
