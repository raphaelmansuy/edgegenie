# OpenGenie coding agent — the deployment surface.
#
#   make                       what can I do? (this is the default, on purpose)
#   make doctor                is this machine able to deploy at all?
#   make dev                   run it locally, fake agent, for UI work
#   make dev-real              run it locally against the REAL agent and a real model
#   make check                 the whole gate: types + unit tests (no network, no cloud)
#   make deploy ENV=dev        provision -> deploy -> VERIFY, against the dev workspace
#   make deploy ENV=prod       the same, against the live workspace
#   make verify ENV=dev        is the deployment serving the code in this checkout?
#   make logs ENV=dev          the app's own logs
#
# ENV selects a workspace. Where each one points, and HOW the source reaches it, is declared in
# scripts/env.sh and nowhere else: the two workspaces disagree about whether an app may deploy from a
# Workspace folder or only from git, so the transport cannot be a flag at a call site.
#
# Why this file exists. On 2026-11-09 the app reported "App started successfully" three times in a row
# while serving none of the work that had been written: no attach menu, no blob route, no vision field.
# Each cause was invisible to the deploy command itself, and each is now a step in `deploy`:
#
#   1. the app deploys from a WORKSPACE FOLDER, not from git, so `git push` changed nothing      -> sync
#   2. the front-end build skipped itself when dist/ already existed, so a cached bundle shipped -> prepare-app.sh always builds
#   3. SUCCEEDED means "the process started", NOT "it is running your code"                      -> verify probes the live URL
#
# So `deploy` is provision + sync + deploy + verify, and `verify` fails loudly when the live app lacks
# what this checkout has. A deployment nobody probed is a guess.

SHELL := /bin/bash
.DEFAULT_GOAL := help
.PHONY: help doctor setup dev dev-real shell-pg check types unit audits vision \
        long-running
.PHONY: sync deploy-only deploy verify status url logs stop start clean clean-all \
        provision provision-lakebase provision-secrets

APP        := coding-agent
APP_DIR    := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
REPO       := $(abspath $(APP_DIR)/../..)
PY         := $(APP_DIR)/.venv/bin/python
WEB        := $(APP_DIR)/web
PORT       ?= 8062
REAL_PORT  ?= 8071

# Which workspace. `dev` is the deployment/experiment workspace; `prod` is the live one. Both the
# host and the transport come from scripts/env.sh, so this variable cannot put the two out of step.
ENV        ?= prod
SCRIPTS    := $(APP_DIR)/scripts

# A shell fragment that loads an environment into a recipe's shell. Every deployment recipe starts
# with it, so no recipe can run against an environment it did not resolve.
ENVSH      := . "$(SCRIPTS)/env.sh" "$(ENV)" &&

# Help is generated from the `##` comments, so it cannot fall out of step with the targets.
help: ## Show this help
	@printf '\n\033[1mOpenGenie coding agent\033[0m — deployment and development\n\n'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf '\n\033[2m  deploy = provision + sync + deploy + verify. SUCCEEDED alone does not mean your code is live.\033[0m\n'
	@printf '\033[2m  ENV selects the workspace (dev or prod); scripts/env.sh says where each one is.\033[0m\n\n'

# ---------------------------------------------------------------- is this machine ready
doctor: ## Check the toolchain, the credentials, and the source the app will build
	@printf '\033[1m1. tools\033[0m\n'
	@for t in databricks python3 node npm git make; do \
	  if command -v $$t >/dev/null; then printf '  ok      %-11s %s\n' "$$t" "$$(command -v $$t)"; \
	  else printf '  \033[31mMISSING\033[0m %s\n' "$$t"; fi; done
	@printf '\033[1m2. the app itself\033[0m\n'
	@test -x $(PY) && printf '  ok      venv\n' || printf '  \033[31mMISSING\033[0m .venv — run: make setup\n'
	@test -d $(WEB)/node_modules && printf '  ok      web deps\n' || printf '  \033[33mabsent\033[0m web/node_modules — run: make setup\n'
	@printf '\033[1m3. the environment (ENV=%s)\033[0m\n' "$(ENV)"
	@$(ENVSH) printf '  host    %s\n  app     %s\n  source  %s\n' "$$DATABRICKS_HOST" "$$APP_NAME" "$$DEPLOY_SOURCE"
	@$(ENVSH) databricks current-user me -o json 2>/dev/null | $(PY) -c 'import json,sys;print("  ok      signed in as", json.load(sys.stdin).get("userName"))' \
	  || printf '  \033[31mFAIL\033[0m    cannot authenticate — export DATABRICKS_TOKEN, or databricks auth login --host $$DATABRICKS_HOST\n'
	@printf '\033[1m4. what is deployed\033[0m\n'
	@$(ENVSH) databricks apps get "$$APP_NAME" -o json 2>/dev/null | $(PY) -c 'import json,sys;\
d=json.load(sys.stdin); dp=d.get("active_deployment") or {}; st=dp.get("status") or {};\
print("  ok      %s | compute %s | deployment %s | app %s" % (d["name"], (d.get("compute_status") or {}).get("state"), st.get("state"), (d.get("app_status") or {}).get("state")))' \
	  || printf '  \033[33mabsent\033[0m  the app is not created — run: make deploy ENV=%s\n' "$(ENV)"
	@printf '\033[1m5. does the deployed source match this checkout?\033[0m\n'
	@$(ENVSH) if [ "$$DEPLOY_SOURCE" = "git" ]; then \
	  local_head=$$(git -C "$(REPO)" rev-parse HEAD); \
	  remote_head=$$(git -C "$(REPO)" ls-remote "$$DEPLOY_GIT_URL" "refs/heads/$$DEPLOY_GIT_BRANCH" | cut -f1); \
	  if [ "$$local_head" = "$$remote_head" ]; then \
	    printf '  ok      HEAD is %s on the remote\n' "$$DEPLOY_GIT_BRANCH"; \
	  else printf '  \033[33mpush\033[0m    HEAD (%s) != remote %s (%s) — the remote is what will build\n' "$$local_head" "$$DEPLOY_GIT_BRANCH" "$$remote_head"; fi; \
	else \
	  for probe in api/domain/blob.py api/adapters/acp/blocks.py web/scripts/vision-e2e.mjs; do \
	    if databricks workspace list "$$DEPLOY_WS_SRC/$$(dirname $$probe)" 2>/dev/null | grep -q "$$(basename $$probe)"; then \
	      printf '  ok      %s\n' "$$probe"; \
	    else printf '  \033[33mstale\033[0m   %s — the next deploy would sync it\n' "$$probe"; fi; \
	  done; \
	fi

# ---------------------------------------------------------------- local development
setup: ## Install what is needed to run and test locally
	@test -d $(APP_DIR)/.venv || python3 -m venv $(APP_DIR)/.venv
	@$(APP_DIR)/.venv/bin/pip install -q -U pip
	@$(APP_DIR)/.venv/bin/pip install -q -r $(APP_DIR)/requirements.txt
	@$(APP_DIR)/.venv/bin/pip install -q pytest pytest-asyncio pytest-xdist 2>/dev/null || true
	@npm --prefix $(WEB) install --no-audit --no-fund
	@printf '  ready. Next: make dev\n'

dev: ## Run locally with the FAKE agent (deterministic, no model calls) on PORT=$(PORT)
	@printf '  http://127.0.0.1:$(PORT)   fake agent — scripted scenarios\n'
	@$(ENVSH) cd $(APP_DIR) && ./scripts/dev-token.sh $(PORT)

dev-real: ## Run locally against the REAL agent and a real model on REAL_PORT=$(REAL_PORT)
	@printf '  http://127.0.0.1:$(REAL_PORT)   real opencode + a serving endpoint — vision works here\n'
	@# The token is whichever credential this environment uses: a PAT when one is exported, otherwise
	@# an OAuth login. `databricks auth token` only answers for the latter, so a PAT is preferred here.
	@$(ENVSH) cd $(APP_DIR) && \
	  DATABRICKS_HOST="$$DATABRICKS_HOST" \
	  APP_AGENT_MODE=stdio \
	  APP_AGENT_CWD=$$(mktemp -d /tmp/agent-real-XXXXXX) \
	  APP_BLOB_DIR=$$(mktemp -d /tmp/blobs-real-XXXXXX) \
	  APP_DEV_TOKEN="$${DATABRICKS_TOKEN:-$$(databricks auth token --host "$$DATABRICKS_HOST" -o json | $(PY) -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')}" \
	  $(PY) -m uvicorn api.main:app --host 127.0.0.1 --port $(REAL_PORT) --log-level warning

shell-pg: ## A throwaway Postgres for the migration tests
	@cd $(APP_DIR) && ./scripts/pg-test.sh start

# ---------------------------------------------------------------- the gate
check: types unit ## Everything that must pass before a deploy (no cloud, no network)
	@printf '\n\033[1mcheck: all green\033[0m\n'

types: ## TypeScript, and no Python that fails to import
	@printf '\033[1mtsc\033[0m\n'
	@cd $(WEB) && npx tsc -b --noEmit && printf '  ok      no type errors\n'

unit: ## pytest + vitest
	@printf '\033[1mpytest\033[0m\n'
	@cd $(APP_DIR) && $(PY) -m pytest tests -q 2>&1 | tail -2
	@printf '\033[1mvitest\033[0m\n'
	@cd $(WEB) && npx vitest run 2>&1 | grep -E 'Test Files|Tests '

audits: ## Accessibility, overflow and layout shift, against a running app on PORT
	@printf '\033[1maudits against http://127.0.0.1:$(PORT)\033[0m\n'
	@cd $(WEB) && \
	  APP_URL=http://127.0.0.1:$(PORT) node scripts/a11y-audit.mjs 2>&1 | grep TOTAL; \
	  for w in 1480 1180 900; do APP_URL=http://127.0.0.1:$(PORT) WIDTHS=$$w node scripts/overflow-audit.mjs 2>&1 | grep TOTAL; done; \
	  APP_URL=http://127.0.0.1:$(PORT) node scripts/cls-audit.mjs 2>&1 | tail -1

vision: ## Prove the model can READ an image (needs dev-real on REAL_PORT)
	@cd $(WEB) && APP_URL=http://127.0.0.1:$(REAL_PORT) node scripts/vision-e2e.mjs

# ---------------------------------------------------------------- deployment
# Everything below reads its workspace and its transport from scripts/env.sh, so `make deploy ENV=dev`
# and `make deploy ENV=prod` take genuinely different paths without any target knowing which is which.
provision: provision-secrets provision-lakebase ## Prepare the two things an app cannot create for itself
	@printf '\n\033[1mprovisioned\033[0m — %s is ready for a deploy\n' "$(ENV)"

provision-secrets: ## Create the secret scope and its two secrets (idempotent; never overwrites)
	@$(ENVSH) "$(SCRIPTS)/provision-secrets.sh" "$(ENV)"

provision-lakebase: ## Create the Lakebase project and the app role's CONNECT/CREATE privileges
	@$(ENVSH) "$(SCRIPTS)/provision-lakebase.sh" "$(ENV)"

sync: ## (prod only) Copy the TRACKED files into the workspace folder the app deploys from
	@$(ENVSH) if [ "$$DEPLOY_SOURCE" != "workspace" ]; then \
	  printf '\033[33msync\033[0m skipped: %s deploys from git, so the source is the committed tree\n' "$(ENV)"; \
	else \
	  printf '\033[1msync\033[0m    git ls-files -> %s\n' "$$DEPLOY_WS_SRC"; \
	  "$(SCRIPTS)/sync-app-source.sh" "$$DEPLOY_WS_SRC"; \
	fi

deploy-only: ## Deploy the current source and wait until the app is RUNNING (does not verify)
	@$(ENVSH) printf '\033[1mdeploy\033[0m  %s -> %s (%s)\n' "$$APP_NAME" "$$DATABRICKS_HOST" "$$DEPLOY_SOURCE"
	@# The CLI waits by default. `--wait` is not a flag: it prints help and exits non-zero, and piping
	@# that help through `tail` used to hide the failure (tail exits 0), so make reported success for a
	@# deploy that never started. pipefail keeps the CLI's exit code, and SUCCEEDED must appear.
	@$(ENVSH) log=$$(mktemp); \
	  set -o pipefail; \
	  if [ "$$DEPLOY_SOURCE" = "git" ]; then \
	    databricks apps deploy "$$APP_NAME" --git-branch "$$DEPLOY_GIT_BRANCH" \
	      --git-source-code-path "$$DEPLOY_GIT_PATH" --auto-approve 2>&1 | tee "$$log" | tail -30; \
	  else \
	    databricks apps deploy "$$APP_NAME" --source-code-path "$$DEPLOY_WS_SRC" --auto-approve 2>&1 | tee "$$log" | tail -30; \
	  fi; \
	  code=$$?; \
	  if [ $$code -ne 0 ] || ! grep -q SUCCEEDED "$$log"; then \
	    printf '\033[31mdeploy failed\033[0m (exit %s). The lines above are the reason.\n' "$$code"; \
	    rm -f "$$log"; exit 1; \
	  fi; \
	  rm -f "$$log"

deploy: provision sync deploy-only verify ## provision -> sync -> deploy -> verify the LIVE url

verify: ## Is the LIVE app serving THIS checkout? Fails when it is not.
	@$(ENVSH) "$(SCRIPTS)/verify-deployed.sh"

status: ## What is deployed right now
	@$(ENVSH) databricks apps get "$$APP_NAME" -o json 2>/dev/null | $(PY) -c 'import json,sys;\
d=json.load(sys.stdin); dp=d.get("active_deployment") or {}; st=dp.get("status") or {};\
print("  app        ", d["name"]);\
print("  compute    ", (d.get("compute_status") or {}).get("state"));\
print("  app status ", (d.get("app_status") or {}).get("state"));\
print("  deployment ", dp.get("deployment_id"));\
print("  created    ", dp.get("create_time"));\
print("  status     ", st.get("state"), "-", (st.get("message") or "")[:60]);\
print("  url        ", d.get("url"))'

url: ## Print the deployed URL
	@$(ENVSH) databricks apps get "$$APP_NAME" -o json 2>/dev/null | $(PY) -c 'import json,sys;print(json.load(sys.stdin).get("url",""))'

logs: ## The app's own logs (needs an OAuth login; a PAT is refused by the logs API)
	@$(ENVSH) databricks apps logs "$$APP_NAME" --tail-lines 120 2>&1 | tail -120

stop: ## Stop the deployed app
	@$(ENVSH) databricks apps stop "$$APP_NAME" >/dev/null && printf '  stopped %s on %s\n' "$$APP_NAME" "$$DATABRICKS_HOST"

start: ## Start the deployed app
	@$(ENVSH) databricks apps start "$$APP_NAME" >/dev/null && printf '  started %s on %s\n' "$$APP_NAME" "$$DATABRICKS_HOST"

clean: ## Remove local build output
	@rm -rf $(WEB)/dist && printf '  removed web/dist\n'

clean-all: clean ## ...and node_modules and caches
	@rm -rf $(WEB)/node_modules $(APP_DIR)/.pytest_cache $(APP_DIR)/.ruff_cache
	@printf '  removed node_modules and caches\n'

# Spec 010: disposable local server + deterministic browser disconnect/recovery evidence.
long-running: ## Verify durable sessions and save browser evidence in specs/010-long-running
	@cd $(WEB) && npm run build && npm run e2e:long-running
