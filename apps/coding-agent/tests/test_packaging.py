"""Deployment packaging: the things that made the first deployment crash.

These are not unit tests of behaviour; they are checks that the repository contains what the
Databricks App runtime actually reads. Each one corresponds to a real failure.
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
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
    """Walk the imports and fail if something is used but not declared.

    The tool server is a SEPARATE PROCESS the app spawns with `sys.executable`, so its imports are
    app runtime dependencies too. This walk used to cover `api/` only, and that blind spot shipped a
    `psycopg2` import in `tools/databricks_notebook_mcp.py` that nothing declared — the card's first
    data step raised ModuleNotFoundError on a deployed app (spec 013 [F1]).
    """
    import sys
    stdlib = set(sys.stdlib_module_names)
    declared = (APP / "requirements.txt").read_text().lower()
    alias = {"pydantic_settings": "pydantic-settings", "psycopg_pool": "psycopg-pool"}
    missing: set[str] = set()
    roots = [APP / "api", APP / "tools"]
    for root in roots:
        for py in root.rglob("*.py"):
            if ".venv" in py.parts or "__pycache__" in py.parts:
                continue
            # `kernel_runtime.py` is the code that runs on the compute, shipped as text. Its optional
            # imports (matplotlib) are the compute's, not the app's.
            if py.name == "kernel_runtime.py":
                continue
            # Parse actual imports. Notebook runner templates are string data executed remotely,
            # and optional serverless packages inside them are not app runtime dependencies.
            for node in ast.walk(ast.parse(py.read_text())):
                if isinstance(node, ast.Import):
                    modules = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    modules = [node.module.split(".")[0]]
                else:
                    continue
                for mod in modules:
                    if mod in stdlib or mod in ("api",) or mod.startswith("_"):
                        continue
                    name = alias.get(mod, mod).lower()
                    if name not in declared:
                        missing.add(mod)
    assert not missing, f"imported but not in requirements.txt: {sorted(missing)}"


def test_the_tool_server_uses_the_client_the_app_ships():
    """One Postgres client. `psycopg2` was imported by the tool server and declared nowhere; `psycopg`
    (v3) is in requirements.txt and is what the rest of the app uses (spec 013 [F1], [LB-3])."""
    req = (APP / "requirements.txt").read_text()
    assert re.search(r"^psycopg\b", req, re.M), "the app must declare psycopg (v3)"
    server = (APP / "tools" / "databricks_notebook_mcp.py").read_text()
    assert "import psycopg2" not in server and "psycopg2.connect" not in server


def test_exactly_one_tool_server_exists():
    """The app resolves `tools/` first and a deployment ships only that. A second copy under `mcp/`
    had drifted by 117 lines, so a fix there reached nobody (spec 013 [F8], [RB-9])."""
    repo = APP.parents[1]
    found = [p for p in repo.rglob("databricks_notebook_mcp.py")
             if ".venv" not in p.parts and "node_modules" not in p.parts]
    assert len(found) == 1, f"exactly one tool server must exist; found {[str(p) for p in found]}"


def test_exactly_one_copy_of_each_skill():
    """Four skills were duplicated byte for byte in `mcp/skills` and `tools/skills` (spec 013 [F9])."""
    repo = APP.parents[1]
    names: dict[str, list[Path]] = {}
    for p in repo.rglob("*.md"):
        if "skills" not in p.parts or ".venv" in p.parts or "node_modules" in p.parts:
            continue
        names.setdefault(p.name, []).append(p)
    doubled = {n: [str(x) for x in ps] for n, ps in names.items() if len(ps) > 1}
    assert not doubled, f"a skill exists in more than one place: {doubled}"


def test_the_lakebase_skill_teaches_the_app_resource_contract():
    """The skill is the agent's teaching surface, so it is tested like code (spec 013 [F7])."""
    text = (APP / "tools" / "skills" / "lakebase-postgres.md").read_text()
    for required in ("PGHOST", "LAKEBASE_ENDPOINT", "psycopg", "max − min"):
        assert required in text, f"the Lakebase skill must mention {required!r}"
    for forbidden in ("psycopg2", "instance_names", "read_write_dns"):
        assert forbidden not in text, f"the Lakebase skill must not teach {forbidden!r}"


def test_the_apps_skill_teaches_the_resource_that_lets_it_connect():
    text = (APP / "tools" / "skills" / "databricks-apps.md").read_text()
    for required in ("resources", "CAN_CONNECT_AND_CREATE", "git_repository", "0.0.0.0", "logz"):
        assert required in text, f"the Apps skill must mention {required!r}"
    assert "dbx_app_health" in text, "the skill must tell the agent how to prove the app works"


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


@pytest.mark.parametrize("version,accepted", [("1.18.19", True), ("1.18.18", False)])
def test_clean_build_initializes_the_agent_and_keeps_its_version_pin(tmp_path, version, accepted):
    """A fresh package wrapper fails until postinstall initializes its binary, as in Databricks."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(APP / "scripts/prepare-app.sh", scripts / "prepare-app.sh")
    for helper in ("check-run-identity.py", "install-databricks-cli.py"):
        (scripts / helper).write_text("")
    binaries = tmp_path / "fixture-bin"
    binaries.mkdir()
    npm = binaries / "npm"
    npm.write_text(f"#!{sys.executable}\n" + '''
import os, sys
from pathlib import Path
if "--prefix" in sys.argv:
    if "build" in sys.argv:
        Path("web/dist").mkdir(parents=True)
        Path("web/dist/index.html").write_text("built")
else:
    Path("node_modules/opencode-ai/bin").mkdir(parents=True)
    Path("node_modules/.bin").mkdir()
    Path("node_modules/opencode-ai/postinstall.mjs").write_text(
        "import fs from 'node:fs'; fs.writeFileSync('node_modules/opencode-ai/bin/ready', 'ready');")
    wrapper = Path("node_modules/.bin/opencode")
    wrapper.write_text("#!/usr/bin/env node\\n"
        "const fs=require('node:fs'); if(!fs.existsSync('node_modules/opencode-ai/bin/ready'))process.exit(7);"
        "console.log(process.env.FIXTURE_AGENT_VERSION);")
    wrapper.chmod(0o755)
''')
    npm.chmod(0o755)
    result = subprocess.run(["bash", str(scripts / "prepare-app.sh")], capture_output=True, text=True,
                            env={**os.environ, "PATH": f"{binaries}:{os.environ['PATH']}",
                                 "FIXTURE_AGENT_VERSION": version})
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr
    assert (tmp_path / "node_modules/opencode-ai/bin/ready").is_file()
    assert (tmp_path / "web/dist/index.html").is_file() is accepted


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
