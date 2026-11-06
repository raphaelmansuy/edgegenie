#!/bin/bash
# Did the run produce a final answer, or stop silently after tool calls?
set -u
cd "$HOME/proj" || exit 1
echo "--- raw log size ---"
wc -c e_case.log
echo "--- full stripped log ---"
sed -e 's/\x1b\[[0-9;]*m//g' e_case.log | grep -vE '^\s*$' | tail -60
