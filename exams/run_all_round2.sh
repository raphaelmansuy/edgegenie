#!/bin/bash
cd "$(dirname "$0")"
for V in V5 V6 V4; do
  L=$(echo $V | tr A-Z a-z)
  python3 run_exam.py --variant $V --model gemini-3.8-flash --missions all --parallel 2 --batch ${L}_gemini > results_G_${V}.log 2>&1
  python3 cleanup_leftovers.py >> results_G_${V}.log 2>&1
done
for V in V1 V4 V5 V6; do
  L=$(echo $V | tr A-Z a-z)
  python3 run_exam.py --variant $V --model gpt-oss-120b --missions held --parallel 2 --batch heldout_${L}_gptoss > results_H_${V}.log 2>&1
  python3 cleanup_leftovers.py >> results_H_${V}.log 2>&1
done
echo ALLDONE > results_round2_done.log
