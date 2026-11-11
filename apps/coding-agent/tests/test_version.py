"""The version this app states, checked against the file every surface reads.

Why these tests exist. A version is the one fact that is wrong by default: it is typed once, in one
file, and every other place that repeats it drifts silently. `apps/coding-agent/VERSION` is the source;
`pyproject.toml`, the front-end build and the site footer are readers. This file makes the readers
agree or fails.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import buildinfo
from api.config import Settings
from api.main import build

APP = Path(__file__).resolve().parents[1]


def _client() -> TestClient:
    return TestClient(build(Settings(
        agent_mode="fake",
        agent_command=f"{sys.executable} -m api.adapters.fake.agent notebook 0",
        allowed_models=["fake/model-a"],
        default_model="fake/model-a",
        dev_user="tester@example.com",
    )))


def test_the_version_file_exists_and_is_semver():
    """A missing `VERSION` must be a test failure, not a page that says `unknown`."""
    text = (APP / "VERSION").read_text(encoding="utf-8").strip()
    assert re.match(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$", text), (
        f"VERSION holds {text!r}, which is not a semantic version"
    )
    assert text == "1.0.0", f"VERSION moved to {text}; update the tag and the release notes with it"


def test_the_python_package_version_is_the_file():
    """`pyproject.toml` is what a wheel or a `pip install` would report. It must not disagree."""
    pyproject = (APP / "pyproject.toml").read_text(encoding="utf-8")
    stated = re.search(r'^version = "([^"]+)"', pyproject, re.M)
    assert stated, "pyproject.toml has no [project] version"
    assert stated.group(1) == buildinfo.BUILD.version, (
        f"pyproject says {stated.group(1)}, VERSION says {buildinfo.BUILD.version}"
    )


def test_the_web_package_version_matches_too():
    """The front-end package is part of the same release, even though nothing installs it."""
    web = (APP / "web" / "package.json").read_text(encoding="utf-8")
    stated = re.search(r'"version": "([^"]+)"', web)
    if stated:
        assert stated.group(1) == buildinfo.BUILD.version, (
            f"web/package.json says {stated.group(1)}, VERSION says {buildinfo.BUILD.version}"
        )


@pytest.mark.parametrize("raw,expected", [
    ("1.0.0", "1.0.0"),
    ("0.1.0", "0.1.0"),
    ("2.3.4-rc.1", "2.3.4-rc.1"),
    ("1.0.0+build.5", "1.0.0+build.5"),
])
def test_the_environment_can_pin_a_version(raw, expected, monkeypatch):
    """`APP_VERSION` exists so a test or a preview can state a version it chooses."""
    monkeypatch.setenv("APP_VERSION", raw)
    assert buildinfo._read_version() == expected


def test_a_malformed_version_is_stated_as_unknown(monkeypatch):
    """`unknown` is an honest answer; a number invented from a bad file is not."""
    monkeypatch.setenv("APP_VERSION", "")
    monkeypatch.setattr(buildinfo, "VERSION_FILE", Path("/nonexistent/VERSION"))
    assert buildinfo._read_version() == "unknown"


def test_a_commit_is_read_from_the_platform_never_guessed(monkeypatch):
    """A Workspace-folder deployment has no `.git`; empty is the answer there."""
    for name in ("APP_GIT_COMMIT", "DATABRICKS_GIT_COMMIT"):
        monkeypatch.delenv(name, raising=False)
    assert buildinfo._read_commit() == ""
    monkeypatch.setenv("DATABRICKS_GIT_COMMIT", "d5efcfd10b7f69428923365111bf9b84b4747c80")
    assert buildinfo._read_commit().startswith("d5efcfd")


def test_the_label_shortens_the_commit():
    """One label shape, so the bar, the menu and the home panel cannot state it three ways."""
    assert buildinfo.label.__doc__ is not None
    assert buildinfo.short_commit("d5efcfd10b7f69428923365111bf9b84b4747c80") == "d5efcfd"
    assert buildinfo.short_commit("") == ""


def test_the_version_route_answers_what_the_file_says():
    """The route the deployment verifier reads. `/api/health` cannot do this job: it is `{ok: true}`
    for every build ever deployed."""
    with _client() as c:
        body = c.get("/api/version").json()
    assert body["version"] == buildinfo.BUILD.version
    assert body["version"] != "unknown"
    assert body["agentMode"] == "fake"
    # The three links a reader wants after "which version": docs, source, the history of changes.
    assert body["docs"] == "https://raphaelmansuy.github.io/opengenie/"
    assert body["source"] == "https://github.com/raphaelmansuy/opengenie"
    assert body["releases"] == "https://github.com/raphaelmansuy/opengenie/releases"
    # Present and possibly empty. Present, because a client reads it without checking for a key.
    assert "commit" in body


def test_the_version_route_needs_no_identity_beyond_the_proxy():
    """It is public information — the same facts the page prints — so it must not 401 in a fake build
    that never configured an identity, which is what a verifier without a user token would see."""
    with _client() as c:
        assert c.get("/api/version").status_code == 200
