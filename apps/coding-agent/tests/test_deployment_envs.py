"""Deployment process: the two workspaces, and the invariant that keeps one from breaking the other.

These are not tests of the app. They are tests of the DEPLOYMENT CONFIGURATION, because on
2026-11-10 the app was deployed to a second workspace and the expensive risks were all in the
configuration, not the code:

  * the two workspaces disagree about whether an app may deploy from a Workspace folder or only
    from git — a difference no CLI flag can bridge;
  * `apps update` is a FULL REPLACEMENT, so a request that forgets `user_api_scopes` silently
    drops them and every workspace pane then 403s;
  * a bundle target's `workspace.host` OVERRIDES $DATABRICKS_HOST, so a stray host in
    databricks.yml makes an operator deploy to a workspace they did not name.

A test is the cheap place to hold those invariants. Each one below is a defect that was either
observed or is one edit away.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
SCRIPTS = APP / "scripts"

#: The scopes `apps update` must receive EVERY time. A full-replacement call that omits one clears it.
REQUIRED_SCOPES = {
    "sql", "files", "model-serving", "ai-gateway", "genie",
    "workspace.workspace", "catalog.catalogs:read", "catalog.schemas:read",
    "catalog.tables:read",
}


# ---------------------------------------------------------------- the bundle
def test_the_bundle_declares_both_workspaces_as_targets():
    """`dev` is the deployment workspace and `prod` is the live one. Both must exist, or a deploy
    silently falls back to whichever target is `default`."""
    bundle = yaml.safe_load((REPO / "databricks.yml").read_text())
    assert set(bundle["targets"]) >= {"dev", "prod"}, bundle["targets"].keys()
    assert bundle["targets"]["dev"].get("default") is True


def test_no_bundle_target_sets_a_workspace_host():
    """A host in `targets.*.workspace.host` is resolved BEFORE $DATABRICKS_HOST, so it wins — silently.

    Measured: with a literal host in the target and $DATABRICKS_HOST pointing at a bogus host,
    `databricks apps list` still answered from the target's workspace. An operator who exported the
    wrong host would deploy to the right one and never learn it. The host lives in scripts/env.sh,
    which asserts the identity it finds.
    """
    bundle = yaml.safe_load((REPO / "databricks.yml").read_text())
    for name, target in (bundle.get("targets") or {}).items():
        host = ((target or {}).get("workspace") or {}).get("host")
        assert not host, (
            f"target '{name}' sets workspace.host={host!r}; it would override DATABRICKS_HOST. "
            "Keep hosts in scripts/env.sh instead.")


def test_only_the_dev_target_declares_a_git_repository():
    """The dev workspace refuses any app without one; the prod workspace has always deployed from a
    Workspace folder. Adding a git repository to prod would change how production deploys, which is
    not a side effect a dev bring-up is allowed to have."""
    bundle = yaml.safe_load((REPO / "databricks.yml").read_text())
    target = (bundle["targets"]["dev"]["resources"]["apps"]["coding-agent"])
    assert target["git_repository"]["provider"] == "gitHub"
    assert target["git_repository"]["url"].endswith("/opengenie")

    prod = bundle["targets"]["prod"]
    assert "git_repository" not in yaml.safe_dump(prod), (
        "prod must keep deploying from its Workspace folder; a git_repository there changes it")


def test_the_bundle_requests_every_scope_the_app_needs():
    bundle = yaml.safe_load((REPO / "databricks.yml").read_text())
    declared = set(bundle["resources"]["apps"]["coding-agent"]["user_api_scopes"])
    assert REQUIRED_SCOPES <= declared, f"missing from databricks.yml: {REQUIRED_SCOPES - declared}"


# ---------------------------------------------------------------- the one app body
def test_the_scope_list_lives_in_exactly_one_place():
    """`apps update` replaces the whole spec. Two lists would eventually disagree, and the loser is
    every user of the Files and Catalog panes. So the list is declared once, in env.sh, and both the
    script that GRANTS it and the script that CHECKS it read it from there."""
    offenders = []
    for script in SCRIPTS.glob("*.sh"):
        if script.name == "env.sh":
            continue
        if "catalog.tables:read" in script.read_text():
            offenders.append(script.name)
    assert not offenders, (
        f"{offenders} re-list the scopes; they must read DEPLOY_REQUIRED_SCOPES from scripts/env.sh")


def test_the_scope_lists_source_and_check_the_same_set():
    """A verification that checks a different set than the deploy requests either fails forever or,
    worse, passes while a scope is missing."""
    env = (SCRIPTS / "env.sh").read_text()
    declared = re.search(r"DEPLOY_REQUIRED_SCOPES=\((.*?)\)", env, re.S)
    assert declared, "scripts/env.sh must declare DEPLOY_REQUIRED_SCOPES"
    scopes = set(declared.group(1).split())
    assert scopes == REQUIRED_SCOPES, (
        f"env.sh is missing {REQUIRED_SCOPES - scopes}; env.sh has extra {scopes - REQUIRED_SCOPES}")

    # Both consumers must actually use it rather than keeping a copy.
    assert "DEPLOY_REQUIRED_SCOPES" in (SCRIPTS / "deploy.sh").read_text()
    assert "DEPLOY_REQUIRED_SCOPES_CSV" in (SCRIPTS / "verify-deployed.sh").read_text()


# ---------------------------------------------------------------- the environments
def test_every_environment_resolves_a_host_and_a_transport():
    """Both environments must declare a host and a transport. A missing transport is how a deploy
    ends up guessing, and the two workspaces do not accept the same answer."""
    env = (SCRIPTS / "env.sh").read_text()
    for name in ("dev", "prod"):
        assert re.search(rf"^\s*{name}\)", env, re.M), f"env.sh has no '{name}' branch"

    # A host, and a transport, for each: the assertion is structural because sourcing env.sh would
    # mutate this process's environment.
    assert env.count("DEPLOY_HOST=") == 2
    assert env.count("DEPLOY_SOURCE=") == 2


def test_the_dev_workspace_uses_git_and_prod_uses_a_workspace_folder():
    """This is the measured platform difference, not a preference. If it is ever flipped, the deploy
    to that workspace fails with 'Apps in this workspace can only be deployed from Git' — or, worse,
    prod ships a snapshot nobody synced."""
    env = (SCRIPTS / "env.sh").read_text()
    dev = env.split("dev)")[1].split("prod)")[0]
    prod = env.split("prod)")[1]

    assert 'DEPLOY_SOURCE="git"' in dev
    assert 'DEPLOY_SOURCE="workspace"' in prod
    # prod's folder must be named, or sync-app-source has nowhere to write.
    assert "/Workspace/Users/" in prod


def test_no_script_hard_codes_a_workspace_host():
    """Two workspaces means every hard-coded host is a bug waiting: the last one to be written wins,
    and a deploy lands somewhere nobody chose. The hosts belong in env.sh alone."""
    offenders = []
    for script in SCRIPTS.glob("*.sh"):
        if script.name == "env.sh":
            continue
        if re.search(r"dbc-[0-9a-f-]+\.cloud\.databricks\.com", script.read_text()):
            offenders.append(script.name)
    assert not offenders, f"these hard-code a workspace host instead of sourcing env.sh: {offenders}"


def test_the_makefile_never_hard_codes_a_workspace_host():
    """The Makefile used to `export DATABRICKS_HOST ?= https://dbc-...`. That was fine with one
    workspace and is a live hazard with two: `?=` means the default silently wins whenever the
    variable is unset, and nothing in the output says which workspace was used."""
    makefile = (APP / "Makefile").read_text()
    assert not re.search(r"dbc-[0-9a-f-]+\.cloud\.databricks\.com", makefile), (
        "the Makefile names a host; ENV + scripts/env.sh must decide it")


# ---------------------------------------------------------------- the notebook guard
def test_no_python_source_looks_like_a_databricks_notebook():
    """A line beginning with the notebook header turns a .py into a notebook when the app is
    deployed: the '.py' is dropped and the import fails at boot. This took the app down once.

    Deployment notebooks that must carry the header are stored as `.notebook` for that reason.
    """
    header = re.compile(r"^\s*(?:#|--|//)\s*Databricks notebook source", re.M)
    offenders = [
        str(p.relative_to(APP))
        for p in APP.rglob("*.py")
        if ".venv" not in p.parts and "node_modules" not in p.parts and header.search(p.read_text("utf-8"))
    ]
    assert not offenders, f"these would deploy as notebooks, not modules: {offenders}"


def test_the_deployment_notebooks_are_not_python_modules():
    """The ones that DO need the header live beside the scripts, and are excluded from packaging by
    their extension. If one is renamed back to `.py`, the app breaks at boot."""
    for name in ("lakebase_grants", "app_health_probe"):
        path = SCRIPTS / f"{name}.notebook"
        assert path.exists(), f"scripts/{name}.notebook is missing"
        assert "Databricks notebook source" in path.read_text()


@pytest.mark.parametrize("script", ["env.sh", "deploy.sh", "provision-lakebase.sh",
                                    "provision-secrets.sh", "verify-deployed.sh"])
def test_deployment_scripts_parsing(script):
    """`bash -n` parses without running: a syntax error in a deploy script is discovered at deploy
    time otherwise, halfway through a provisioning run."""
    path = SCRIPTS / script
    assert path.exists(), f"scripts/{script} is missing"
    result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, f"scripts/{script} has a syntax error:\n{result.stderr}"


def test_the_reference_app_body_points_at_this_repository():
    """`app.create.json` told `apps create` to build from `raphaelmansuy/edgegenie` — a different
    repository — so an app created from it would have run code nobody here wrote. deploy.sh builds
    the body itself and this file is reference, but a wrong repository in the repository is a trap
    regardless of who reads it."""
    body = json.loads((APP / "app.create.json").read_text())
    url = body["git_repository"]["url"]
    assert url.endswith("/opengenie"), f"app.create.json builds from {url}, not this repository"
    assert body["source_code_path"] == "apps/coding-agent"


def test_the_deploy_script_and_the_reference_body_agree_on_the_repository():
    """Two places name the repository. If they differ, a deploy and a create disagree about what
    code the app runs."""
    env = (SCRIPTS / "env.sh").read_text()
    declared = re.search(r'DEPLOY_GIT_URL="([^"]+)"', env)
    assert declared, "scripts/env.sh must declare DEPLOY_GIT_URL for the git-transport workspace"
    reference = json.loads((APP / "app.create.json").read_text())["git_repository"]["url"]
    assert declared.group(1) == reference, (
        f"env.sh says {declared.group(1)}, app.create.json says {reference}")


# ---------------------------------------------------------------- credentials
def test_the_credential_shorthand_is_gitignored():
    """A FILE named `.venv` in the repo root held a plaintext Databricks PAT. `.gitignore` listed
    `.venv/` — a DIRECTORY pattern, which does not match a file of that name — so a `git add -A`
    would have committed a live token. Both spellings must stay ignored."""
    for path in (REPO / ".venv", APP / ".venv"):
        result = subprocess.run(["git", "check-ignore", "-q", str(path)],
                                cwd=REPO, capture_output=True)
        assert result.returncode == 0, (
            f"{path} is not gitignored; a `.venv` holding a token would be committed")


def test_no_credential_is_committed_in_the_scripts():
    """A token in a deploy script is a token in the repository's history, forever."""
    pattern = re.compile(r"dapi[0-9a-f]{32}")
    offenders = [p.name for p in SCRIPTS.rglob("*")
                 if p.is_file() and pattern.search(p.read_text(errors="ignore"))]
    assert not offenders, f"these contain what looks like a Databricks PAT: {offenders}"
