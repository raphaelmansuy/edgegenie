#!/usr/bin/env bash
# The one place that says WHERE a deployment goes and HOW its code reaches the workspace.
#
#   source scripts/env.sh dev     # or: prod
#
# Why this file exists. The deployment scripts used to hard-code one workspace, one app name and
# one transport (a Workspace folder). That was true for exactly one environment. A second
# workspace turned out to differ in a way no flag could paper over:
#
#   prod  dbc-1e111e44-3334  accepts a Workspace-folder source. `apps deploy` ships the working tree.
#   dev   dbc-cb61f1e1-bd8e  accepts ONLY git. `apps create` refuses without `git_repository` and
#                            `apps deploy` refuses a Workspace path ("Apps in this workspace can only
#                            be deployed from Git").
#
# So the transport is a property of the workspace, not a preference. It is declared here, once, and
# every script reads it. Guessing it at a call site is how a deploy ships a snapshot nobody meant.
#
# Also fixed here: a bundle target's `workspace.host` OVERRIDES $DATABRICKS_HOST, silently. Measured:
# with `workspace.host` set and $DATABRICKS_HOST pointing at a bogus host, `databricks apps list`
# still answered from the target's workspace. That is why every script asserts the workspace identity
# before it writes, and why the host is passed by this file rather than inferred.

# shellcheck shell=bash

deploy_env_name="${1:-${APP_ENV_NAME:-prod}}"

case "$deploy_env_name" in
  dev)
    # The development workspace: experiments, first deploys, anything not yet worth a rollout.
    DEPLOY_HOST="https://dbc-cb61f1e1-bd8e.cloud.databricks.com"
    DEPLOY_APP="coding-agent"
    # This workspace only deploys from git, so the source is a COMMITTED tree, not the working copy.
    DEPLOY_SOURCE="git"
    DEPLOY_GIT_URL="https://github.com/raphaelmansuy/opengenie"
    DEPLOY_GIT_BRANCH="main"
    DEPLOY_GIT_PATH="apps/coding-agent"
    DEPLOY_WS_SRC=""
    DEPLOY_BUNDLE_TARGET="dev"
    # Lakebase is not reachable from a laptop here (the endpoint resolves to a private-link
    # ingress that times out). SQL that must run against it runs as an in-workspace job instead.
    DEPLOY_LAKEBASE_DIRECT="no"
    ;;
  prod)
    # The live workspace. Unchanged on purpose: same host, same app, same folder the app has always
    # deployed from. Nothing about this environment's mechanism moved during the dev bring-up.
    DEPLOY_HOST="https://dbc-1e111e44-3334.cloud.databricks.com"
    DEPLOY_APP="coding-agent"
    # This workspace accepts a Workspace folder, and the app is created without a git repository.
    DEPLOY_SOURCE="workspace"
    DEPLOY_GIT_URL=""
    DEPLOY_GIT_BRANCH=""
    DEPLOY_GIT_PATH=""
    DEPLOY_WS_SRC="/Workspace/Users/raphael.mansuy@gmail.com/coding-agent"
    DEPLOY_BUNDLE_TARGET="prod"
    DEPLOY_LAKEBASE_DIRECT="yes"
    ;;
  *)
    printf '\033[31mSTOP: unknown environment %q. Use dev or prod.\033[0m\n' "$deploy_env_name" >&2
    return 1 2>/dev/null || exit 1
    ;;
esac

export APP_ENV_NAME="$deploy_env_name"
export APP_NAME="$DEPLOY_APP"
export DATABRICKS_HOST="$DEPLOY_HOST"

# A token is the credential; a stale profile is not. Clearing the profile variables is what makes
# $DATABRICKS_TOKEN authoritative, so a script cannot read someone else's cached login.
unset DATABRICKS_CONFIG_PROFILE DATABRICKS_CONFIG_FILE

# Everything shared by both environments. A project name is per-workspace, so the SAME name in two
# workspaces is two independent databases — which is why app.yaml needs no per-environment edit.
export DEPLOY_LAKEBASE_PROJECT="${DEPLOY_LAKEBASE_PROJECT:-coding-agent-llm}"
export DEPLOY_LAKEBASE_BRANCH="${DEPLOY_LAKEBASE_BRANCH:-production}"
export DEPLOY_LAKEBASE_ENDPOINT="projects/${DEPLOY_LAKEBASE_PROJECT}/branches/${DEPLOY_LAKEBASE_BRANCH}/endpoints/primary"
export DEPLOY_SECRET_SCOPE="${DEPLOY_SECRET_SCOPE:-coding-agent-llm}"

# The user-authorization scopes the app must hold, in ONE place.
#
# `apps update` is a FULL REPLACEMENT: a call that omits a scope clears it, and the Files and Catalog
# panes then answer 403 for every user. That happened. The list is declared here so the script that
# GRANTS it (deploy.sh) and the script that CHECKS it (verify-deployed.sh) cannot drift apart — a
# verification that checks a different set than the deploy requests fails forever, or passes wrongly.
DEPLOY_REQUIRED_SCOPES=(sql files model-serving ai-gateway genie workspace.workspace
                        catalog.catalogs:read catalog.schemas:read catalog.tables:read
                        postgres apps)
export DEPLOY_REQUIRED_SCOPES_CSV="${DEPLOY_REQUIRED_SCOPES[*]}"
# Spec 013 [RB-2]: the two object types the Data tab manages are behind their own scopes. Granting
# them is declared HERE, beside the others, because `apps update` is a full replacement: a list that
# omits a scope clears it, and the Data tab then answers 403 for every user.

# The identity every script must find when it asks the workspace who it is talking to.
# A deploy that lands in the wrong workspace is not a bad deployment, it is the wrong product.
require_workspace_identity() {
  command -v databricks >/dev/null || { printf '\033[31mSTOP: the databricks CLI is not installed\033[0m\n' >&2; return 1; }
  [ -n "${DATABRICKS_TOKEN:-}" ] || { printf '\033[31mSTOP: set DATABRICKS_TOKEN\033[0m\n' >&2; return 1; }

  local resolved
  resolved="$(databricks current-user me -o json 2>/dev/null | python3 -c '
import json,sys
try: print(json.load(sys.stdin)["userName"])
except Exception: print("")' 2>/dev/null)"
  if [ -z "$resolved" ]; then
    printf '\033[31mSTOP: cannot authenticate to %s with this token\033[0m\n' "$DATABRICKS_HOST" >&2
    return 1
  fi
  if [ -n "${DEPLOY_EXPECT_USER:-}" ] && [ "$resolved" != "$DEPLOY_EXPECT_USER" ]; then
    printf '\033[31mSTOP: %s answers as %s, expected %s\033[0m\n' \
      "$DATABRICKS_HOST" "$resolved" "$DEPLOY_EXPECT_USER" >&2
    return 1
  fi
  printf '  workspace  %s\n  identity   %s\n  app        %s\n  source     %s\n' \
    "$DATABRICKS_HOST" "$resolved" "$APP_NAME" "$DEPLOY_SOURCE"
  return 0
}
