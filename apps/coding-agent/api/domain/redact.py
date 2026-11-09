"""Redaction, at the source. One regex set, used by every sink.

A provider key is the strongest secret this app holds, and four formats of it now exist. The rule
(06 §Redaction) is *redact on the way in to any sink* — event store, log line, error detail, export
— so a sink that forgot to call the filter cannot leak. The patterns are the specification in
06's table; `tests/test_llm_secrets.py` generates its scan from `SECRET_PATTERNS`.

Pure: no I/O.
"""

from __future__ import annotations

import re

#: Every format that will now exist, plus the generic bearer an echoed header carries.
#: Order matters only in that a more specific pattern must come before a broader one
#: (`sk-ant-…` before `sk-…`, because the latter is a substring class of the former).
SECRET_PATTERNS: tuple[str, ...] = (
    r"dapi[a-f0-9]{32}",
    r"sk-ant-[A-Za-z0-9_\-]{20,}",
    r"sk-[A-Za-z0-9_\-]{20,}",
    r"AIza[0-9A-Za-z_\-]{35}",
    r"ya29\.[0-9A-Za-z_\-]{20,}",
    r"-----BEGIN (RSA )?PRIVATE KEY-----.*?-----END (RSA )?PRIVATE KEY-----",
    r"Bearer [A-Za-z0-9._\-]{20,}",
)

_COMPILED = tuple(re.compile(p, re.S) for p in SECRET_PATTERNS)

#: Human labels, so the transcript can say what it removed without echoing the secret.
LABELS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"dapi[a-f0-9]{32}"), "databricks token"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "anthropic key"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "openai key"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{35}"), "google api key"),
    (re.compile(r"ya29\.[0-9A-Za-z_\-]{20,}"), "google access token"),
    (re.compile(r"-----BEGIN (RSA )?PRIVATE KEY-----.*?-----END (RSA )?PRIVATE KEY-----", re.S), "private key"),
    (re.compile(r"Bearer [A-Za-z0-9._\-]{20,}"), "bearer token"),
)


def redact(text: str) -> str:
    """Replace every secret-shaped run with a labelled placeholder. Idempotent."""
    out = text or ""
    for pattern in _COMPILED:
        out = pattern.sub("[redacted]", out)
    return out


def redact_labelled(text: str) -> str:
    """Like `redact`, but the placeholder names the format: `[redacted: openai key]`.

    Used where a person will read the result and knowing *what* was removed is useful — the event
    stream for a prompt someone pasted a key into (E-8/S12).
    """
    out = text or ""
    for pattern, label in LABELS:
        out = pattern.sub(f"[redacted: {label}]", out)
    return out


def contains_secret(text: str) -> bool:
    """True when anything in `text` looks like a secret. Used by the response-scan test."""
    raw = text or ""
    return any(p.search(raw) for p in _COMPILED)


def token_scopes(token: str | None) -> list[str]:
    """The OAuth scope names inside an access token, or [] when it is not a readable JWT.

    A diagnostic, not an authority: the claim is read without verifying the signature, which is fine
    for *showing* a user what their own token carries and wrong for deciding anything. Only the scope
    NAMES leave this function; the token itself, and every other claim, are dropped.
    """
    import base64
    import json

    parts = (token or "").split(".")
    if len(parts) != 3:
        return []
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, TypeError):
        return []
    raw = claims.get("scope", claims.get("scp", [])) if isinstance(claims, dict) else []
    names = raw.split() if isinstance(raw, str) else [str(x) for x in raw] if isinstance(raw, list) else []
    return sorted({n for n in names if n})


def redact_value(value):
    """Redact recognized secret formats in structured journal data without serializing JSON text."""
    if isinstance(value, str):
        return redact_labelled(value)
    if isinstance(value, dict):
        return {key: redact_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(item) for item in value]
    return value
