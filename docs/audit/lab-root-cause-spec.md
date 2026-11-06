# Lab root cause: workflow vs platform errors (spec + plan, 2026-11-06)

Branch `feat/lab-root-cause` (worktree `../AgentDev-lab`). Nothing is committed without the user's approval.

## Problem
`build_fix_brief` always asks the workflow assistant to find the root cause "in the workflow". Account errors,
429s, missing tools, engine bugs, vague criteria and a flaky judge all become workflow fixes, so the assistant
edits workflows that are fine (sometimes making them worse).

## Goal
Each Lab finding names the layer that caused it. Only `workflow` findings ask for a workflow fix. Platform
findings become an evidence report for a human / a developer agent (branch + PR), never a live code change.
Changing AgentDev source is only prepared after the user clicks an explicit button AND types the password.

## Contract (backward compatible: fields are only added)
Job (`GET /api/lab/jobs/{id}`):
- `findings[].layer`: `workflow | platform | environment | scenario`; `findings[].error_kind` (optional).
- `results[].error_kind`: structured kind of a run error (see below), absent on old jobs.
- `layers`: `{workflow, platform, environment, scenario}` counts of findings (interrupted excluded).
- `needs_workflow_fix`: bool. `fix_brief` is `""` when false.
- `platform_report`: markdown (`""` when no platform finding): scenario, error, node/tool trace, repro steps.
- `environment_hints`: `[{code, detail, fix, scenario}]` (deduplicated).
- Rerun jobs: `rerun_of` (source job id), `rerun_compare` `{before, after, flags}` (`flags` = `compare_baseline`).

`error_kind` values (from exception classes, never from text when the class is known):
`timeout` (Lab watchdog, `LabRunTimeoutError`), `loop_limit` (cycle safety limit, `details.kind`),
`budget_limit` (`BudgetExceededError`), `quota` (`QuotaExceededError`), `cli` (`CliProviderError`: missing CLI,
not logged in), `provider_timeout` (`CliTimeoutError`), `model_call` (`ModelCallError`: model failed after
retries, e.g. 429), `os_error`, `engine_exception` (a Python bug type such as AttributeError/TypeError/KeyError
anywhere in the cause chain), `workflow_error` (other `WorkflowExecutionError` / config errors),
`interrupted`, `unknown`. Old jobs (no `error_kind`) fall back to ONE commented string table in `lab_diagnosis.py`.

Layer of each finding:
- environment: quota, cli, provider_timeout, model_call, os_error, judge unavailable, 429 / rate-limit text.
- platform: engine_exception, tool evidence with `error_code` `TOOL_NOT_FOUND` / `TOOL_NOT_ALLOWED`, or a tool
  that raised a Python bug type (`exception_type`), unknown errors (suspected platform).
- scenario: `judge_flaky` (repeats of one scenario disagree), `criteria_missing`, `criteria_vague`; quality
  findings of a flaky scenario move to `scenario`.
- workflow: loop, overkill, over_budget, wrong_final_node, quality, budget_limit, timeout, loop_limit,
  workflow_error, regression, no_answer (empty final answer).
- An over-time finding of a run whose error is environment/platform takes that layer (429 retries are slow).

Engine additions (structured, no behaviour change): tool-call log details carry `error_code` / `exception_type`;
the cycle safety-limit error carries `details.kind = "loop_limit"`; `_tool_evidence` copies them; error runs keep
their evidence.

New endpoints (`/api/lab`):
- `GET /jobs/{id}/rerun-failed/estimate` -> `{scenarios: [index], runs, estimate_usd|null, cost_known}`.
- `POST /jobs/{id}/rerun-failed` `{confirm: true}` -> 202 new job (failed scenarios only, current YAML,
  same repeats, `rerun_of`). 409 `nothing_to_rerun`. Paid gates stay refused by the Lab's auto-answer channel.
- `GET /platform-fix/info` -> `{enabled, forbidden: [...], gates: [...], steps: [...]}` (what will happen).
- `POST /jobs/{id}/platform-fix` `{password, confirm: true}` -> `{branch, worktree, brief_file, actions,
  next_steps}`. 400 `confirm_required`, 403 `bad_password`, 429 `too_many_attempts`, 409 `no_platform_report` /
  `git_unavailable` / `already_prepared`. It only creates a separate git worktree + branch and writes
  `PLATFORM_FIX.md` there. It never edits the running checkout, never runs a model, never commits, pushes or
  merges. Password: PBKDF2 hash (default chosen by the user, override with `AGENTDEV_SOURCE_FIX_PASSWORD_HASH`),
  constant-time compare, lock after 5 failures for 5 minutes, every attempt logged on `agentdev.platform_fix`.

## Plan (slices, each with red tests first)
1. Layer classification: `lab_diagnosis.py`, `workflow_lab.py` (`error_kind`, evidence), engine structured
   fields. Tests: `tests/test_lab_layers.py` (429 is not `timeout`, interrupted still dropped, each layer).
2. Brief by layer + `platform_report` / `environment_hints`; assistant prompt may answer "no fix needed".
   Tests: (a) 429-only job has no fix request, (b) loop job keeps the old brief, (c) platform+workflow job asks
   only for the workflow part and the platform part is in `platform_report`. `test_reference_is_compact` green.
3. Lab UI: findings grouped by layer with label + hint, "Fix with assistant" only with workflow findings,
   "Copy platform report", environment guidance, platform-fix dialog (explicit list + password).
4. Rerun failed scenarios after applying a Lab-sourced proposal: one button, cost estimate first, compare.
5. (optional) assistant may propose skills / tools / model / run_limits as data through the Apply card.
ADR: `docs/adr/0009-platform-fix-loop.md` (0005-0008 are taken by uncommitted work in the main checkout).
