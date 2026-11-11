"""Which build is this? One answer, read from the `VERSION` file that ships with the app.

Why a file in `apps/coding-agent/` rather than a git tag or the repository root: the `prod` target
deploys from a Workspace folder that `scripts/sync-app-source.sh` fills with `git ls-files
apps/coding-agent`. A file outside the app folder never reaches that container, so it could describe a
version the running code does not have. This one is inside the deployed tree by construction.

Why it is not called `api/version.py`: `api/domain/version.py` already owns the word — it mints the
optimistic-concurrency token for a workspace object — and two modules named `version` one import away
from each other is how the wrong one gets imported. This module is about the BUILD.

The commit is optional. A deployment from a Workspace folder has no `.git`, and inventing a commit
there would be the exact failure `scripts/verify-deployed.sh` exists to catch: a build that claims an
identity it cannot support. Absent is said to be absent.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: `<app>/VERSION`, beside `app.yaml`. `api/` is one level down from the app root.
VERSION_FILE = Path(__file__).resolve().parents[1] / "VERSION"

#: The pages a reader wants after asking "which version is this?": the site, the source, the release.
DOCS_URL = "https://raphaelmansuy.github.io/opengenie/"
SOURCE_URL = "https://github.com/raphaelmansuy/opengenie"
RELEASES_URL = f"{SOURCE_URL}/releases"

_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def _read_version() -> str:
    """The version this build ships, or a stated `unknown`.

    `APP_VERSION` wins so a test can pin it, but the file is the source: an environment variable that
    disagrees with the tree is a deployment mistake, and `tests/test_version.py` asserts the file
    against `pyproject.toml` so the two cannot drift silently.
    """
    override = os.environ.get("APP_VERSION", "").strip()
    if override:
        return override
    try:
        text = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    return text if _SEMVER.match(text) else "unknown"


def _read_commit() -> str:
    """The commit the platform resolved, when the platform says. Empty when it does not.

    Databricks Apps sets `DATABRICKS_GIT_COMMIT` for a git-source deployment. It is read, never
    guessed: a short hash invented from a local checkout would name a revision the container may not
    hold.
    """
    for name in ("APP_GIT_COMMIT", "DATABRICKS_GIT_COMMIT"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


@dataclass(frozen=True, slots=True)
class Build:
    """What one running process is."""

    version: str
    commit: str
    docs: str = DOCS_URL
    source: str = SOURCE_URL
    releases: str = RELEASES_URL

    def to_dict(self, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {
            "version": self.version,
            "commit": self.commit,
            "docs": self.docs,
            "source": self.source,
            "releases": self.releases,
        }
        if extra:
            out.update(extra)
        return out


#: Read once per process. A version that changed under a running process would be a lie either way.
BUILD = Build(version=_read_version(), commit=_read_commit())


def short_commit(commit: str | None = None) -> str:
    """The first 7 characters, for a label a human reads."""
    value = commit if commit is not None else BUILD.commit
    return value[:7] if value else ""


def label(commit: str | None = None) -> str:
    """`v1.0.0` or `v1.0.0 (abc1234)` — one string, so every surface states it the same way."""
    head = f"v{BUILD.version}"
    short = short_commit(commit)
    return f"{head} ({short})" if short else head
