#!/bin/bash
cd "$(dirname "$0")"
while [ ! -f results_round4_done.log ]; do sleep 20; done
python3 run_exam.py --agent copilot --variant V4 --model gpt-oss-120b --missions all --parallel 2 --batch copilot_shim_v4_gptoss > results_S_V4.log 2>&1
python3 cleanup_leftovers.py >> results_S_V4.log 2>&1
python3 run_exam.py --agent copilot --variant V4 --model gpt-oss-120b --missions held --parallel 2 --batch copilot_shim_heldout_v4_gptoss > results_S_H.log 2>&1
python3 cleanup_leftovers.py >> results_S_H.log 2>&1
python3 run_exam.py --agent copilot --variant V6 --model gpt-oss-120b --missions all --parallel 2 --batch copilot_shim_v6_gptoss > results_S_V6.log 2>&1
python3 cleanup_leftovers.py >> results_S_V6.log 2>&1
echo ALLDONE > results_round5_done.log
