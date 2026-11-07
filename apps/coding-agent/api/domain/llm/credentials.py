"""Credential shape validation. One validator per kind, all pure.

A malformed key is refused at entry rather than at the first turn (K1–K4 in 07, E-10 in 10). For a
service-account JSON that means genuinely parsing the thing: `type`, `project_id`, `client_email`,
and a `private_key` that parses as RSA. A pasted blob that merely *looks* like JSON is exactly the
failure "Test connection" exists to catch before it is stored.

Nothing here logs, stores or returns the plaintext. `CredentialParsed` carries only derived metadata.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from .model import CredentialKind

_PROJECT = re.compile(r"^[a-z0-9][a-z0-9\-]{4,60}$")


class CredentialError(ValueError):
    """A key that cannot be stored. The message names the field, so the form can point at it."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


@dataclass(frozen=True, slots=True)
class CredentialParsed:
    """What may be shown about a stored secret, and nothing more.

    `last4` is display only; `fingerprint` lets the app answer "the user pasted the same key again"
    without decrypting; `project_hint` lets the settings screen say "project mobioos-506015".
    """

    kind: CredentialKind
    last4: str
    fingerprint: str
    project_hint: str = ""
    #: The value to hand a child process. The **only** field carrying plaintext.
    secret: str = ""

    def public(self) -> dict[str, str]:
        """The subset an API may return. Deliberately a method, so leaking is a visible edit."""
        return {
            "kind": self.kind.value,
            "last4": self.last4,
            "fingerprint": self.fingerprint,
            "projectHint": self.project_hint,
        }


def fingerprint(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]


def _last4(secret: str, project: str = "") -> str:
    """The last four characters a person can recognise. For a JSON key, the project is the identity."""
    if project:
        return fingerprint(secret)[:4]
    tail = re.sub(r"\s+", "", secret)[-4:]
    return tail if len(tail) == 4 else fingerprint(secret)[:4]


def validate(kind: CredentialKind, raw: str) -> CredentialParsed:
    """Validate and derive metadata. Raises `CredentialError` naming the failing field."""
    value = (raw or "").strip()
    if not value:
        raise CredentialError("secret", "the key is empty")
    if kind is CredentialKind.SERVICE_ACCOUNT_JSON:
        return _service_account(value)
    if kind is CredentialKind.API_KEY:
        return _api_key(value)
    if kind is CredentialKind.ACCESS_TOKEN:
        return _access_token(value)
    # CredentialKind.NONE means the workspace token covers the model; there is nothing to store.
    raise CredentialError("kind", f"{kind.value} is not a storable credential kind")


def _api_key(value: str) -> CredentialParsed:
    # A key is copied and pasted, so surrounding whitespace is trimmed (a newline from a copy is
    # common). Whitespace *inside* the key is a different value, not a tidier version of this one:
    # silently stripping it stores a key the user never had, and the first turn fails with a 401.
    if re.search(r"\s", value.strip()):
        raise CredentialError("secret", "an API key has no spaces; check what was pasted")
    compact = value.strip()
    if len(compact) < 20:
        raise CredentialError("secret", "an API key is at least 20 characters")
    if not re.fullmatch(r"[A-Za-z0-9_\-.:+/=]+", compact):
        raise CredentialError("secret", "an API key has no spaces and no quotes")
    return CredentialParsed(CredentialKind.API_KEY, compact[-4:], fingerprint(compact), secret=compact)


def _access_token(value: str) -> CredentialParsed:
    if re.search(r"\s", value.strip()):
        raise CredentialError("secret", "an access token has no spaces; check what was pasted")
    compact = value.strip()
    if len(compact) < 20:
        raise CredentialError("secret", "an access token is at least 20 characters")
    return CredentialParsed(CredentialKind.ACCESS_TOKEN, compact[-4:], fingerprint(compact), secret=compact)


def with_project(kind: CredentialKind, raw: str, project: str) -> str:
    """Fill `project_id` into a service-account key that lacks it, from an explicit project.

    A key downloaded from the console carries `project_id`; one cached by `gcloud` may not. The
    project a key bills to is a fact the user can state, so we accept it beside the key rather than
    reject a valid identity. An existing `project_id` always wins: it is part of the key.
    """
    project = (project or "").strip()
    if kind is not CredentialKind.SERVICE_ACCOUNT_JSON or not project:
        return raw
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if not isinstance(data, dict) or data.get("project_id"):
        return raw
    return json.dumps({**data, "project_id": project})


def _service_account(value: str) -> CredentialParsed:
    try:
        data: Any = json.loads(value)
    except json.JSONDecodeError as exc:
        raise CredentialError("secret", f"not valid JSON: {exc.msg} at line {exc.lineno}") from exc
    if not isinstance(data, dict):
        raise CredentialError("secret", "a service-account key is a JSON object")
    if data.get("type") != "service_account":
        raise CredentialError("type", f'type must be "service_account", not {data.get("type")!r}')
    project = str(data.get("project_id") or "")
    if not _PROJECT.match(project):
        raise CredentialError("project_id", "project_id is missing or not a GCP project id")
    email = str(data.get("client_email") or "")
    if "@" not in email or ".iam.gserviceaccount.com" not in email:
        raise CredentialError("client_email", "client_email is not a service-account address")
    pem = str(data.get("private_key") or "")
    if not pem.startswith("-----BEGIN"):
        raise CredentialError("private_key", "private_key is not a PEM block")
    _assert_rsa(pem)
    return CredentialParsed(CredentialKind.SERVICE_ACCOUNT_JSON, _last4(value, project),
                            fingerprint(value), project_hint=project, secret=value)


def _assert_rsa(pem: str) -> None:
    """Prove the PEM parses as a usable key, without keeping the key object.

    `cryptography` is a pinned dependency (09 P1). If it is absent the validation degrades to a
    structural check rather than failing the request: a deployment with no `cryptography` also has no
    vault, and the vault is what refuses first.
    """
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
    except ImportError:  # pragma: no cover - the app always ships cryptography
        if "PRIVATE KEY-----" not in pem:
            raise CredentialError("private_key", "private_key is not a PEM block") from None
        return
    try:
        load_pem_private_key(pem.encode("utf-8"), password=None)
    except (ValueError, TypeError) as exc:
        raise CredentialError("private_key", f"private_key does not parse: {exc}") from exc
