# Token savings, round 2 (fake model, measured)

## A6-3: prompt-prefix stability between consecutive follow-up turns

Measure: share of the next prompt that is byte-identical to the previous prompt (`conversation_turns.compose_follow_up_prompt`,
8-10 turns, changed-files list growing, 4 turns kept). Before = `HEAD`, after = this change.
Light = answers 600 chars, mid = 1500 + 2 team members, heavy = 3000 + 3 team members.

| workload | request | shared prefix before | after |
|---|---|---|---|
| light | normal | 9.3% | 44.1% |
| mid | normal | 8.2% | 31.3% |
| heavy | normal | 13.5% | 13.5% (the budget keeps only 1-2 turns, window moves every turn) |
| any | "ok" (3k budget, ~750 tokens) | 16.6-20.6% | 17.4-20.6% (too small to matter for a prompt cache) |

What changed: the oldest turn shown moves in steps of 2 (`WINDOW_STEP`), the char-budget cut also drops 2 at a time, the
changed-files list moved after the transcript and is budgeted by its cap (not its length), so it no longer moves the cut.
History size stays within the round-1 budgets (normal <= 9k chars, short <= 3k; tests unchanged and green).
Bench: `--only followup_long` prints `shared_prefix_ratio` per turn (fake answers are small, so it only moves at the turn
where the window slides: turn 6 20.7% -> 24.8%).

## A6-1 remainder: skill tool catalog

All skills preloaded and one has extra files: only `read_skill_file` is sent (no `activate_skill`).
Catalog chars per model call: 695 -> 435 (-37%). The bench `team` scenario has no skill files, so it already sent 0 skill tools.

## A6-4 / B4-H1: usage of failed calls

Fake CLI returning 5000 in + 800 out + $0.12 with `is_error` / exit 1: tracker tokens before 0, after 5800 (cost $0.12 known).
Timeout / idle kill (chat path): partial usage from assistant events is recorded, `cost_known=False`, cost not invented
(`cost_usd` sums known prices only; `summary`, `node_rollups`, `model_rollups`, `call_history` carry `cost_known`).
Codex: the same for a non-zero exit when `turn.completed` usage was streamed (a Codex timeout has no usage to read).
Each failed retry attempt records on its own (the provider records before raising).

## Observability

One INFO line per agent node run, logger `agentdev.run_summary`, JSON: session, node, model, tokens_in, tokens_out,
cache_read, cost_usd, cost_known, duration_s, status (ok/error/cancelled). No prompt text.
