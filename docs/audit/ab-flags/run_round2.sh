#!/bin/bash
# Section 14 A/B: arms rescue2 (NATIVE_TOOL_RESCUE only), reads (PARALLEL_READS only), off2 (all 0, drift check).
# usage: run_round2.sh <rounds> <off_rounds>; each round runs the arms concurrently, tasks a,b,c (3 real runs per arm).
base="AGENTDEV_STRUCTURED_REPORT=0 AGENTDEV_CLI_MAX_OUTPUT=0 AGENTDEV_MEMBER_PROTOCOL_SYSTEM=0 AGENTDEV_VERIFY_GATE=0"
cd /d/Code/Tuyen/AgentDev/backend
out=../docs/audit/ab-flags
arm() { # name reads rescue
  env $base AGENTDEV_PARALLEL_READS=$2 AGENTDEV_NATIVE_TOOL_RESCUE=$3 uv run python -m scripts.bench_projects --real \
    --workflow bugfix_team --tasks a,b,c --max-runs 3 --max-usd 0.25 --out docs/audit/ab-flags/$1 >> $out/$1.log 2>&1
}
for i in $(seq 1 $1); do
  arm rescue2 0 1 &
  arm reads 1 0 &
  if [ $i -le $2 ]; then arm off2 0 0 & fi
  wait
done
