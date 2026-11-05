# 0004. Verify gate: a team lead may not finish while the project's tests are red

Status: accepted as opt-in, flag `AGENTDEV_VERIFY_GATE` stays OFF by default (2026-11-05)

## Context
Baseline (`docs/audit/final.md` section 3): `bugfix_team` on Haiku failed about half of the real runs. The repeated
failure is that the Tech Lead runs alone and ends its turn without delegating (`nodes_run = ['Tech Lead']`, one
model call) while the tests are still red.

Investigation (read-only):
- `AgentNodeExecutor.execute` calls `_handle_tool_calls` only when the first reply has tool calls (or a user note is
  pending). A first reply without tool calls is returned as the node's answer directly.
- Inside `_handle_tool_calls`, a reply without tool calls ends the loop. Nothing in the engine checks that anything was
  delegated, changed or verified. `team.py` only offers the delegation tools; "delegate first" lives in the lead's
  role text (`bugfix_team.yaml`), which a small model may ignore. The Bug Fixer's `Đã kiểm chứng` line is also only
  a prompt convention checked by the lead itself.
- So the only enforceable truth is outside the model: does the project's own test command pass?

## Decision
New module `agentdev/runtime/node/agent/verify_gate.py` and a small hook in `agent_executor.py`:
- Flag `AGENTDEV_VERIFY_GATE` (`1` = on). Off = exactly the old code path (the extra routing condition is false).
- Applies only to the top lead of a team (not members, not sub-leads, not small talk / plain questions, not when a
  plan was submitted) and only when a project workspace exists (never the AgentDev install folder).
- Command: `team.verify_command` in the workflow YAML (new optional field), else auto-detect: `package.json`
  `scripts.test` (ignoring the npm default stub) -> `npm test --silent`; pytest markers (pytest.ini, tox.ini,
  pyproject/setup.cfg sections, `tests/test_*.py`) -> `python -B -m pytest -q -x`; `Makefile` with a `test:` target
  -> `make test`. None found = no-op.
- When the lead tries to finish, the engine runs the command (timeout 180 s, env `AGENTDEV_VERIFY_TIMEOUT_S`;
  the process is registered in the process registry and its whole tree is killed on timeout; output goes to a temp
  file and only the last 3000 characters are kept). `fail` or `timeout` blocks the finish: the real result is appended
  to the lead's conversation (as a user turn, the same mechanism as mid-run notes) and the lead is called again.
  `pass`, `none`, and `error` (command not found) let it finish.
- Hard bound: at most `MAX_ROUNDS = 2` feedback rounds per lead turn, then the lead's answer stands. The feedback
  tells the lead to say plainly when the failure is unrelated or unfixable, and never to call the work verified.
- Result of the latest run is kept in `global_state["verify_gate"]` (status, command, exit code, duration, tail) and
  logged on the node logger; the Lab judge can read it later (not wired now).

Invariants: silence/timeout is never approval (timeout blocks); no paid step is ever started by the gate; no model
call is added when the tests are green or the gate is off; every child process is registered and killed.

## Not done
- "No file changed while the task asked for changes" is not detected: red tests cover the failing-bug case, but a
  feature request on a green repo is not guarded.
- A repo whose tests were already red for unrelated reasons costs up to 2 extra lead calls per turn.
- A lead that legitimately ends the turn with a clarifying question while tests are red is pushed too.

## A/B and default
Real A/B (bugfix_team, Haiku, tasks a,b,c, 3 repeats per arm, 18 runs, 0.284 USD): success OFF 7/9, ON 5/9; calls 15.2 vs
11.6 per run; lead-alone runs 1 vs 2. ON was not better, so the default stays OFF (not tuned to win). In one ON run
the gate fired twice and the lead still did not delegate, which suggests the lead may stop at the plan-approval step
rather than forget to delegate. Next step before re-testing: record the lead's final text in `bench_projects`, and use
n >= 5 per task. Full numbers: `docs/audit/final.md` section 7.
