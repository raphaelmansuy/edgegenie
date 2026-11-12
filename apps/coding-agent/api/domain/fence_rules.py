"""What an UNSET fence dimension means. One answer, in one place, used by every side.

The defect this closes. A session could be created without a schema or without a folder, and the two
runtimes disagreed about what that meant:

  * `api/domain/scope.py` answered **ASK** (a human must decide) — correct, and documented in a comment
    there for exactly this reason;
  * `tools/databricks_notebook_mcp.py` answered **allow** — `if not WRITE_SCHEMAS: return None`, and
    `if WRITE_PATHS and not any(...)` — which for an empty list is no check at all;
  * `api/adapters/mcp/registry.py` turned both cases into a **wildcard**: `"".rstrip("/") + "/"` is `"/"`,
    and every absolute path starts with `/`.

So a session created to read and analyse could write anywhere the signed-in user could. Measured before
this module existed: the app said `ask` for `/Users/victim/x.py` and the tool server said *in scope*.

**The rule, stated once.** Unset means **no write**. Never "any write". A dimension the caller did not
configure is a dimension with no permission, and the only safe reading of an empty allow-list is an
empty allow-list.

This module is PURE: no I/O, no environment, no clock. `registry.start` and `Scope.for_session` both call
it, so the app has one answer; `tools/databricks_notebook_mcp.py` carries a twelve-line mirror because it
runs in a separate process and cannot import this package ([RB-1]), and
`tests/test_fence_parity.py` holds the two to one table.

`[R-1]`, `[R-2]`. See specs/001-opengenie-assessment 10 §3.
"""

from __future__ import annotations

#: A dimension was not configured. Raised rather than returned because a caller that forgot to configure
#: a fence must not be able to ignore the answer and proceed — the failure has to be loud at the seam.
class Unset(ValueError):
    """A fence dimension has no value. The caller must refuse, never widen."""


def _clean(value: str | None) -> str:
    """Strip the spelling noise a path or schema arrives with: whitespace, backticks, quotes."""
    text = str(value or "").strip()
    # Strip any balanced run of quoting characters, then whitespace again. `\`a/b\`` and `"a/b"` are
    # the same path, and a fence that refuses one of them refuses a legitimate write.
    while len(text) >= 2 and text[0] == text[-1] and text[0] in "`\"'":
        text = text[1:-1].strip()
    return text


def is_unset(value: str | None) -> bool:
    """True when `value` is absent or carries no path/schema content.

    `/`, `//`, `  `, `""` and `None` are all unset. A folder of only slashes is a root, and a root is a
    wildcard: treating it as configured is the bug this module exists to prevent.
    """
    return _clean(value).strip(" .").strip("/") == ""


def writable_folder(folder: str | None) -> str:
    """The folder prefix a session may write into, as it is handed to the tool server.

    Returns `""` when there is no writable folder. **Empty is the contract**, not an exception: the
    registry passes `""` and the tool server's `_check_path_scope` refuses every path when it sees it.
    An exception here would make session creation fail for a read-only session, which is the wrong trade.

        "/Users/me/scratch"  -> "/Users/me/scratch/"   (a real prefix)
        "/"                  -> ""                     (a root is a wildcard, so: no folder)
        ""                   -> ""
        None                 -> ""

    The `rstrip("/") + "/"` form is applied ONLY to a value that survives `is_unset`, so the
    `"" + "/" == "/"` collision that produced the wildcard cannot recur.
    """
    if is_unset(folder):
        return ""
    return _clean(folder).rstrip("/") + "/"


def writable_schema(schema: str | None) -> str:
    """The `catalog.schema` a session may write into, or `""` when it has none.

    A schema needs at least two non-empty parts to be placeable. A bare `sales` is relative to whatever
    default catalog the warehouse holds, and the app does not control that — so a one-part value is
    treated as unset rather than guessed at, exactly as `scope._inside_schema` refuses a shorter target.
    `main.` has a trailing empty part and is the same kind of unprovable value.
    """
    text = _clean(schema)
    if not text:
        return ""
    parts = [p.strip().strip("`\"") for p in text.split(".")]
    if len(parts) < 2 or not all(parts):
        return ""
    return ".".join(parts).lower()


def refuse_reason(dimension: str) -> str:
    """The sentence a refusal uses, so two runtimes cannot phrase the same refusal differently."""
    if dimension == "schema":
        return ("write blocked: this session has no writable schema, so it cannot change tables. "
                "Choose a schema when you start a conversation.")
    if dimension == "folder":
        return ("write blocked: this session has no writable folder, so it cannot change files. "
                "Choose a working folder when you start a conversation.")
    return f"write blocked: no {dimension} is configured for this session"
