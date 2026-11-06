# 0006. Parallel pure read-only tool calls in one model turn

Status: accepted as opt-in, flag stays OFF by default (2026-11-06): the real A/B (n=4) was inconclusive; see final.md section 11

## Context
`AgentNodeExecutor._execute_tool_batch` ran the tool calls of one model reply one after the other. A reply with 4
`search_in_files` / `read_file_segment` calls waited for the sum of their times. Only `delegate_task` (several in
one reply) already ran side by side (`_parallel_delegations`).

## Decision
- Whitelist `PARALLEL_READ_TOOLS`: `describe_available_files`, `list_directory`, `read_text_file_snippet`,
  `read_file_segment`, `search_in_files`. Not in it, so never parallel: every writer (`edit_file`, `multi_edit`,
  `save_file`, `apply_text_edits`, rename/copy/move/delete), `load_file` (registers an attachment), shell, MCP tools,
  skill tools, team tools (gates, plan, delegation), anything paid.
- Only NEIGHBOURING eligible calls form a run (2 or more). A read never moves across a write or a team call. A run
  starts when the loop reaches its first call, so the order of effects is the order of the model's calls.
- Bounded pool: `AGENTDEV_PARALLEL_READS_MAX` (default 4, at most 8). Each worker enters the cancel scope itself; the
  batch re-checks cancellation after the run. A failing call keeps its own error text; the others are unaffected.
  Results, log lines and events are produced in the original order at each call's turn.
- Skill `allowed-tools` still apply (a read not allowed is not prefetched and gets the normal refusal).
- `delegate_task` / `delegate_parallel`: the limit of 4 (`max_parallel`) stays and scheduling stays batch by batch.
  Dependency scheduling would need the model to declare dependencies between briefs; the YAML prompts
  (`software_company.yaml` batches 1-3) already encode the dependencies as batches, so nothing is changed.

## Consequences
Wall time of a read run is about the slowest call instead of the sum. Tests: `tests/test_parallel_reads.py`.
