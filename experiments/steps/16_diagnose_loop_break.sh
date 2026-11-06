#!/bin/bash
# Why did Case C stop after the tool call? Re-run with debug logging and a
# deliberately small tool result to separate "result too big" from
# "post-tool turn rejected by the model/gateway".
set -u
export PATH="$HOME/.npm-global/bin:$PATH"
export DATABRICKS_TOKEN="$(cat /tmp/dbx_token.txt)"
cd "$HOME/proj" || exit 1

echo "===== C1: small result (describe table) ====="
rm -f c1b.log
timeout 200 opencode run --model dbx/system.ai.gpt-oss-120b --auto \
  "Call dbxnb_dbx_describe_table with full_name=samples.nyctaxi.trips. Then tell me the column names." \
  </dev/null >c1b.log 2>&1
echo "EXIT=$?"
sed -e 's/\x1b\[[0-9;]*m//g' c1b.log | grep -vE '^\s*$' | tail -20

echo "===== C2: big result (read notebook) with DEBUG ====="
rm -f c2b.log
timeout 240 opencode run --model dbx/system.ai.gpt-oss-120b --auto --print-logs --log-level DEBUG \
  "Call dbxnb_dbx_read_notebook with path=/Users/raphael.mansuy@gmail.com/databricks-toolbox/01-schema-document-generator. Then summarise the imports." \
  </dev/null >c2b.log 2>&1
echo "EXIT=$?"
echo "--- errors ---"
sed -e 's/\x1b\[[0-9;]*m//g' c2b.log | grep -iE "error|finish|step=|max_tokens|token" | grep -viE "http request|blob" | tail -20
echo "--- tail ---"
sed -e 's/\x1b\[[0-9;]*m//g' c2b.log | grep -vE '^\s*$' | tail -12
