# Codex native-tool failure, session resume, cold start (read-only investigation)

## 1. Codex and the "No such tool" failure
- Codex provider mode (`codex_cli_provider.py:166-254`) runs `codex exec --sandbox read-only --output-schema` with ONE model turn per
  call; host tools travel only as JSON `tool_calls` (enum of tool names, `tool_reply_schema` :68). Codex's own tools are not
  offered to the model in this mode, and there is no inner tool loop like `claude -p` with `--tools ""` where the model can
  call `delegate_parallel` as a native tool_use and get "No such tool". The failure class (final text with no tool_calls after
  inner retries) is therefore unlikely; the equivalent risk is Codex running a shell command (`command_execution`) inside
  the call: the `--json` stream exposes `item.started/completed` with `type: command_execution|mcp_tool_call`
  (`_native.py:231-277`, `CodexActivityReader`), but `_call_once` only reads usage + last `agent_message` (`_read_events` :119).
- Smallest equivalent change (only if observed): in `call_model` after `parse_tool_reply`, if `tool_calls` is empty and the
  stream has an `mcp_tool_call`/function item whose name is in `tool_specs`, recover it like `native_calls_of_listed_tools`.
  Not worth doing without a real observation; add a `lead_final` style log instead. Not verified with a real model.

## 2. Session resume
- Claude 2.1.318 (`claude --help`): `--resume <id>`, `--session-id <uuid>`, `-c`, `--fork-session`, `--no-session-persistence`,
  `--input-format stream-json`. Codex 0.166: `codex exec resume [SESSION_ID|--last] [PROMPT]`, `codex exec fork`; the provider
  currently passes `--ephemeral` (`codex_cli_provider.py:55`), which disables persistence.
- Already in the code: provider-mode tool loops reuse ONE Claude session per agent run (`claude_cli_provider.py:199-230`,
  `CliRunState`, flag `AGENTDEV_CLI_SESSION_REUSE`, default ON, session files removed by `delete_claude_session_files` :98 at
  `close()`). Only NATIVE members (`_call_native` :409, `--no-session-persistence` :435) start cold on every delegation; Codex has
  no reuse at all.
- Design for native members (Claude first):
  - Key: (run_id, member_id, resolved workspace path); store `session_id` (uuid made by us, passed via `--session-id`) +
    `sha256(system preamble + tools + model + effort)` + `last_end_ts`. Reuse only if workspace and hash equal.
  - Resume call: `--resume <id>` with only the new task prompt plus a "files changed since your last turn" note built from
    `changed_files_note` of the other members (or git status diff vs. the member's last snapshot).
  - Cleanup: at run end (and on cancel) delete `~/.claude/projects/<slug>/<id>.jsonl` like `delete_claude_session_files`; TTL
    sweep at server start for leftovers; use a per-run `CLAUDE_CONFIG_DIR`? (rejected: breaks login) so deletion is the way.
  - Fallback: any `CliProviderError` on resume -> discard, run fresh (same pattern as :214-218).
  - Cost: resumed turns read the earlier transcript from prompt cache (about 10 % of input price) but the context grows; cap by
    max resumes per member (e.g. 4) or by cumulative input tokens, then start fresh. Saves re-exploration (often 5-10 calls).
  - Risks: stale file contents in context (mitigated by the note, and the model re-reads), cost accounting (`_apply_session_cost`
    pattern for running totals), session leak into user's claude history if cleanup fails, parallel delegations to the same
    member must not share a session (lock or fresh).
- Files: `providers/claude_cli_provider.py`, `providers/_cli_common.py` (a run-scoped `NativeSessionStore`), `team.py`
  (member delegation passes run/member id), `runtime/node/executor/agent_executor.py` (close at run end),
  tests in `tests/test_cli_providers.py` (fake CLI: first call `--session-id`, second `--resume`, hash change -> fresh, resume
  error -> fresh, cleanup at close), `tests/test_team*.py`.

## 3. Cold start
- Data (24 real Haiku runs, `docs/audit/bench-projects-*.json`): mean wall/model_calls = 10.1 s; linear fit wall = 1.1 s +
  8.6 s x calls. Calls include model latency, so pure spawn overhead is not separable from these files; `storage/logs/server.log`
  has only e2e fake runs (median 3.7 s), so no real `duration_s` data to split it. Needs one instrumented run (spawn to first
  stream event) to measure.
- Options: (a) native members for bugfix_team/software_company roles: fewer spawns (one agent loop per delegation), but loses
  JSON tool protocol/budget control; (b) long-lived `--input-format stream-json` process per agent: removes spawn + system
  prompt re-read, but large rewrite of `run_cli` (watchdog, cancel, process registry, schema per turn) and fragile on Windows;
  (c) resume: ALREADY on for provider tool loops, so remaining gain is only the native-member case (section 2).
- Recommendation: option (c) extended to native members (section 2) plus a one-off timing instrumentation of spawn latency;
  decide on (b) only if spawn is measured above about 2 s per call.
