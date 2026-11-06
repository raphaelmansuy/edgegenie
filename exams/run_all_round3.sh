#!/bin/bash
cd "$(dirname "$0")"
while [ ! -f results_round2_done.log ]; do sleep 20; done
for V in V1 V4 V5 V6; do
  L=$(echo $V | tr A-Z a-z)
  python3 run_exam.py --variant $V --model gemini-3.8-flash --missions held --parallel 2 --batch heldout_${L}_gemini > results_HG_${V}.log 2>&1
  python3 cleanup_leftovers.py >> results_HG_${V}.log 2>&1
done
# GitHub Copilot CLI (BYOK through the AI Gateway): dev set + held-out on V4
python3 run_exam.py --agent copilot --variant V4 --model gpt-oss-120b --missions M1 --parallel 1 --batch copilot_smoke > results_C_smoke.log 2>&1
python3 cleanup_leftovers.py >> results_C_smoke.log 2>&1
python3 run_exam.py --agent copilot --variant V4 --model gpt-oss-120b --missions all --parallel 2 --batch copilot_v4_gptoss > results_C_V4.log 2>&1
python3 cleanup_leftovers.py >> results_C_V4.log 2>&1
python3 run_exam.py --agent copilot --variant V4 --model gpt-oss-120b --missions held --parallel 2 --batch copilot_heldout_v4_gptoss > results_C_H.log 2>&1
python3 cleanup_leftovers.py >> results_C_H.log 2>&1
echo ALLDONE > results_round3_done.log
