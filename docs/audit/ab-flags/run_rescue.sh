#!/bin/bash
export AGENTDEV_PARALLEL_READS=0 AGENTDEV_STRUCTURED_REPORT=0 AGENTDEV_CLI_MAX_OUTPUT=0 AGENTDEV_MEMBER_PROTOCOL_SYSTEM=0 AGENTDEV_NATIVE_TOOL_RESCUE=1 AGENTDEV_VERIFY_GATE=0
cd /d/Code/Tuyen/AgentDev/backend
for i in 1 2; do
  uv run python -m scripts.bench_projects --real --workflow bugfix_team --tasks a,b,c --max-runs 3 --max-usd 0.2 --out docs/audit/ab-flags/rescue >> ../docs/audit/ab-flags/rescue.log 2>&1 &
  wait
done
