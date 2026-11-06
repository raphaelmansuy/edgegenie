#!/bin/bash
cd "$(dirname "$0")"
while [ ! -f results_round3_done.log ]; do sleep 20; done
for T in t2 t3; do
  python3 run_exam.py --variant V4 --model gpt-oss-120b --missions all --parallel 2 --batch v4_gptoss_$T > results_R_$T.log 2>&1
  python3 cleanup_leftovers.py >> results_R_$T.log 2>&1
done
echo ALLDONE > results_round4_done.log
