#!/bin/bash
cd "$(dirname "$0")"
for V in V4 V5 V6; do
  L=$(echo $V | tr A-Z a-z)
  python3 run_exam.py --variant $V --missions all --parallel 2 --batch ${L}_gptoss > results_${V}.log 2>&1
  python3 cleanup_leftovers.py >> results_${V}.log 2>&1
done
echo ALLDONE > results_alldone.log
