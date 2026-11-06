# 0008. Token backlog: max_tokens, member protocol in the system prompt, skill catalog

Status: accepted as opt-in, flag stays OFF by default (2026-11-06): the real A/B (n=4) was inconclusive; see final.md section 11

## A6-1 skill catalog
Already fixed in round 2 (`token-savings-round2.md`: 695 -> 435 chars per call). Nothing left to do.

## A6-5 `max_tokens` had no effect with the CLI
`params.max_tokens` in YAML was passed to no CLI. Checked with one real Haiku call: the Claude CLI honours the env
var `CLAUDE_CODE_MAX_OUTPUT_TOKENS` (a call with 60 produced an iteration of exactly 60 output tokens).
Decision: with `AGENTDEV_CLI_MAX_OUTPUT` on, `params.max_tokens` (>= 1000, capped at 64000) is passed as that env var
to every Claude CLI call of the node (`_cli_common.max_output_env`, `run_cli(extra_env=)`). Codex has no equivalent
flag: for Codex `max_tokens` stays ignored (documented). The run-wide budget `run_limits.max_tokens` is separate and unchanged.
Risk: a too small cap cuts an answer mid-way, so a flag, and values below 1000 are ignored.

## A6-7 MEMBER_PROTOCOL in the cacheable prefix
`MEMBER_PROTOCOL` (~1.2k chars) was the first part of every brief (the user message), so it was never part of the
cached system prefix. With `AGENTDEV_MEMBER_PROTOCOL_SYSTEM` on, a plain member (not a lead, inside a delegation) gets
it in its system prompt right after its profile, with a lead-independent text ("the lead named in the task header";
the brief keeps `# Task from <lead>`), and the brief omits it. Same total chars, only moved.
