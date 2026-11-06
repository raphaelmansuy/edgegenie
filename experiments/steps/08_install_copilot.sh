#!/bin/bash
# Install GitHub Copilot CLI inside the Databricks sandbox (user prefix).
set -u
export PATH="$HOME/.npm-global/bin:$PATH"
npm config set prefix "$HOME/.npm-global" >/dev/null 2>&1
npm install -g --allow-scripts=@github/copilot @github/copilot 2>&1 | tail -6
echo "EXIT=$?"
which copilot
copilot --version 2>&1 | head -3
