"""Deployment packaging: the things that made the first deployment crash.

These are not unit tests of behaviour; they are checks that the repository contains what the
Databricks App runtime actually reads. Each one corresponds to a real failure.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

APP = Path(__file__).resolve().parents[1]


def test_requirements_txt_exists_with_the_runtime_dependencies():
    """The app crashed with ModuleNotFoundError: No module named 'pydantic_settings'.
    The platform installs from requirements.txt; a pyproject.toml without uv.lock installs nothing."""
    req = (APP / "requirements.txt").read_text()
    for pkg in ("fastapi", "uvicorn", "pydantic", "pydantic-settings", "httpx"):
        assert re.search(rf"^{re.escape(pkg)}(\[|\=\=)", req, re.M), f"{pkg} missing from requirements.txt"


def test_every_runtime_import_is_declared():
    """Walk the imports and fail if something is used but not declared."""
    import sys
    stdlib = set(sys.stdlib_module_names)
    declared = (APP / "requirements.txt").read_text().lower()
    alias = {"pydantic_settings": "pydantic-settings", "psycopg_pool": "psycopg-pool"}
    missing: set[str] = set()
    for py in (APP / "api").rglob("*.py"):
        for line in py.read_text().splitlines():
            m = re.match(r"\s*(?:from|import)\s+([a-zA-Z_][\w]*)", line)
            if not m:
                continue
            mod = m.group(1)
            if mod in stdlib or mod in ("api",) or mod.startswith("_"):
                continue
            name = alias.get(mod, mod).lower()
            if name not in declared:
                missing.add(mod)
    assert not missing, f"imported but not in requirements.txt: {sorted(missing)}"


def test_app_yaml_is_valid_and_has_no_shell():
    conf = yaml.safe_load((APP / "app.yaml").read_text())
    assert isinstance(conf["command"], list), "command must be an array, not a shell string"
    assert "sh" not in conf["command"] and "-c" not in conf["command"]
    assert any(str(a).startswith("--") for a in conf["command"]), "flags belong in the array"
    env = {e["name"] for e in conf.get("env", [])}
    assert "APP_REQUIRE_FORWARDED_USER" in env, "the app must fail closed on identity in production"


def test_the_build_hook_produces_the_web_bundle():
    """Without web/dist the app serves the API and no UI, which is what the first deployment did."""
    pkg = json.loads((APP / "package.json").read_text())
    assert "build" in pkg["scripts"]
    hook = (APP / "scripts" / "prepare-app.sh").read_text()
    assert "web/dist" in hook
    assert "opencode" in hook, "the agent binary is installed by the build hook, not by the platform"


def test_the_agent_is_a_declared_dependency():
    """opencode ships as an npm package; nothing else installs it in the app image."""
    pkg = json.loads((APP / "package.json").read_text())
    assert any("opencode" in name for name in pkg.get("dependencies", {}))


@pytest.mark.parametrize("path", ["api/main.py", "api/config.py", "app.yaml", "requirements.txt",
                                  "package.json", "scripts/prepare-app.sh"])
def test_files_the_runtime_needs_are_present(path):
    assert (APP / path).exists(), f"{path} is needed by the deployed app"


def test_no_python_source_looks_like_a_databricks_notebook():
    """A line that starts with the notebook header turns the file into a notebook when the app is
    deployed: the ".py" is dropped and the import fails at boot. This took the app down once."""
    import re

    header = re.compile(r"^\s*(?:#|--|//)\s*Databricks notebook source", re.M)
    root = Path(__file__).resolve().parents[1]
    offenders = [
        str(p.relative_to(root))
        for p in root.rglob("*.py")
        if ".venv" not in p.parts and "node_modules" not in p.parts and header.search(p.read_text("utf-8"))
    ]
    assert not offenders, f"these would deploy as notebooks, not modules: {offenders}"
