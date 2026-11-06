# 0009. Platform fix loop: a developer agent on a separate worktree

Status: Proposed (2026-11-06)

## Context
The Lab now tells workflow errors apart from AgentDev platform errors and writes a `platform_report` (markdown)
on a job when it suspects a platform bug. The user wants a path from that report to a source fix, but the
running app must never edit itself:
- the Lab scores workflows with the same code it would change, so a self-edit can "fix" a score by loosening a
  gate, the `paid` rule, the silence-is-not-approval rule or the judge;
- a running server editing its own files can break the session that asked for the fix.

## Decision
- Trigger: a Lab job with a non-empty `platform_report`. The UI first shows `GET /api/lab/platform-fix/info`
  (`steps`, `forbidden`, `gates`), so the user sees exactly what will happen before typing anything.
- Human confirm + password: `POST /api/lab/jobs/{id}/platform-fix {password, confirm: true}`. PBKDF2-SHA256 hash
  (default password `AgentDev`, override `AGENTDEV_SOURCE_FIX_PASSWORD_HASH`), constant-time compare, 5 failures
  lock it for 5 minutes, every attempt logged on `agentdev.platform_fix` (never the password).
  `AGENTDEV_PLATFORM_FIX=0` turns the feature off.
- What it does, and only that: new branch `platform-fix/<id8>` from HEAD, new git worktree
  `<repo>-platform-fix-<id8>` next to the repository, `PLATFORM_FIX.md` inside it (report, forbidden files,
  required checks, "do not merge without the user's review"). No model is run, nothing is committed, pushed,
  merged or opened as a PR; repository hooks are disabled for the `git worktree add`.
- A developer agent (or a person) works in that worktree. Forbidden files: `FORBIDDEN` in
  `backend/agentdev/api/services/platform_fix.py` (single source of truth; gates, `paid`, timeouts, Lab judge and
  scoring, this feature, invariant tests). A fix that seems to need one stops and asks the user.
- Mandatory gates before merge: `GATES` in the same file (forbidden files untouched, full tests, invariant tests,
  a red-first regression test, `bench_engine`, the same Lab scenarios re-run before/after, human review).
- A human reviewer merges. There are no automated PRs or merges.

## Consequences
- Fixes are isolated and reviewable; the running app and its scoring stay unchanged until a person merges.
- The password is a speed bump against an accidental click or another local page, not strong auth (the API is
  local-only). Lockout is in memory and resets on restart.
- Worktrees and branches accumulate; the brief lists the cleanup command.
