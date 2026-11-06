#!/bin/bash
# usage: run_arm.sh <off|on> <rounds> ; one invocation = tasks a,b,c (3 real runs)
arm=$1; n=$2
if [ "$arm" = on ]; then v=1; else v=0; fi
export AGENTDEV_PARALLEL_READS=$v AGENTDEV_STRUCTURED_REPORT=$v AGENTDEV_CLI_MAX_OUTPUT=$v AGENTDEV_MEMBER_PROTOCOL_SYSTEM=$v AGENTDEV_NATIVE_TOOL_RESCUE=$v AGENTDEV_VERIFY_GATE=0
cd /d/Code/Tuyen/AgentDev/backend
for i in $(seq 1 $n); do
  uv run python -m scripts.bench_projects --real --workflow bugfix_team --tasks a,b,c --max-runs 3 --max-usd 0.3 --out docs/audit/ab-flags/$arm >> ../docs/audit/ab-flags/$arm.log 2>&1
done
