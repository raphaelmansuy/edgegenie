"""Lossless SOURCE editing: unchanged cell segments and separators stay byte-identical."""

import re
from .asset import WorkError, digest

SEPARATOR = re.compile(r"(?m)^(?:#|--|//) COMMAND -{2,}[^\r\n]*(?:\r?\n|$)")
HEADER = re.compile(r"\A(?:\ufeff)?(?:#|--|//) Databricks notebook source[^\r\n]*(?:\r?\n|$)")
MAX_SOURCE = 4 * 1024 * 1024


def cells(source: str) -> tuple[str, list[str], list[str]]:
    header = HEADER.match(source)
    head = header.group() if header else ""
    body = source[len(head) :]
    matches = list(SEPARATOR.finditer(body))
    starts = [0] + [m.end() for m in matches]
    ends = [m.start() for m in matches] + [len(body)]
    return head, [body[a:b] for a, b in zip(starts, ends)], [m.group() for m in matches]


def edit_cells(source: str, operations: list[dict], language="PYTHON") -> str:
    head, parts, separators = cells(source)
    sep = (
        separators[0]
        if separators
        else {"SQL": "--", "SCALA": "//"}.get(language, "#") + " COMMAND ----------\n"
    )
    for op in operations:
        action, index = op.get("op"), op.get("index")
        if type(index) is not int or not 0 <= index <= len(parts):
            raise WorkError("Cell index is outside this revision.", 422)
        if action != "insert_cell":
            if index >= len(parts) or not op.get("sha") or op["sha"] != digest(parts[index]):
                raise WorkError("Cell content changed after it was read. Nothing was written.")
        value = op.get("source", "")
        if not isinstance(value, str) or SEPARATOR.search(value) or HEADER.search(value):
            raise WorkError("A cell operation must contain one cell, without SOURCE markers.", 422)
        if action == "replace_cell":
            parts[index] = value
        elif action == "insert_cell":
            parts.insert(index, value)
            separators.insert(max(0, index - 1), sep)
        elif action == "delete_cell":
            parts.pop(index)
            if separators:
                separators.pop(min(index, len(separators) - 1))
        elif action == "move_cell":
            dest = op.get("to")
            if type(dest) is not int or not 0 <= dest < len(parts):
                raise WorkError("Move destination is outside this revision.", 422)
            parts.insert(dest, parts.pop(index))
        else:
            raise WorkError("Unsupported cell operation.", 422)
    # A separator must start on a new line. Existing bytes are retained unchanged.
    out = head
    for i, part in enumerate(parts):
        if i:
            if out and not out.endswith("\n"):
                out += "\n"
            out += separators[i - 1] if i - 1 < len(separators) else sep
        out += part
    return out


def edit_ranges(source: str, operations: list[dict]) -> str:
    result = source
    for op in operations:
        start, end = op.get("start"), op.get("end")
        if (
            op.get("op") != "replace_range"
            or type(start) is not int
            or type(end) is not int
            or not 0 <= start <= end <= len(result)
        ):
            raise WorkError("Use a valid, zero-based character range from the current revision.", 422)
        if op.get("sha") != digest(result[start:end]):
            raise WorkError("The replaced range changed. Nothing was written.")
        result = result[:start] + str(op.get("text", "")) + result[end:]
    return result


def operation_schema():
    """The tool contract is defined alongside the one interpreter of edit operations."""
    variants = []
    fields = {
        "op": {"type": "string"},
        "index": {"type": "integer", "minimum": 0},
        "sha": {"type": "string", "minLength": 64, "maxLength": 64},
        "source": {"type": "string"},
        "to": {"type": "integer", "minimum": 0},
        "start": {"type": "integer", "minimum": 0},
        "end": {"type": "integer", "minimum": 0},
        "text": {"type": "string"},
    }
    for name, required in (
        ("replace_cell", ("index", "sha", "source")),
        ("insert_cell", ("index", "source")),
        ("delete_cell", ("index", "sha")),
        ("move_cell", ("index", "sha", "to")),
        ("replace_range", ("start", "end", "sha", "text")),
    ):
        variants.append(
            {
                "type": "object",
                "properties": {
                    "op": {"type": "string", "enum": [name]},
                    **{k: fields[k] for k in required},
                },
                "required": ["op", *required],
                "additionalProperties": False,
            }
        )
    return {"oneOf": variants}
