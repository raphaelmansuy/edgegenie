#!/bin/bash
# Does the explicit no-match hint let the agent self-recover?
# Deliberately give it a pattern that will not match, and see whether it retries
# with a better pattern instead of concluding "no imports".
set -u
export PATH="$HOME/.npm-global/bin:$PATH"
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
cd "$HOME/proj" || exit 1
rm -f rec.log
timeout 240 opencode run --model px/system.ai.gpt-oss-120b --auto \
  "Call dbxnb_dbx_grep_notebook once with pattern 'IMPORT_STATEMENT' on /Users/raphael.mansuy@gmail.com/databricks-toolbox/01-schema-document-generator. If it reports no matches, recover on your own and still answer: which libraries does the notebook import?" \
  </dev/null >rec.log 2>&1
echo "EXIT=$?"
sed -e 's/\x1b\[[0-9;]*m//g' rec.log | grep -vE '^\s*$' | tail -25
