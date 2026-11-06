# 0005. Git checkpoints: undo what a run edited, without touching the user's work

Status: accepted, flag `AGENTDEV_GIT_CHECKPOINT` ON by default (non-destructive; `0` = off, no-op) (2026-11-06)

## Context
A run can edit files of the user's project. Today there is no way back except the user's own git skills. A naive
`git stash` / `git checkout` / `git reset` would hide or overwrite uncommitted user work, so none of them is used.

## Decision
Service `agentdev/api/services/git_checkpoint.py`, routes under `/api/sessions/{id}/outputs/changes`.
- Applies only when the session workspace (opened project, else session folder) is itself a git repo: `git rev-parse
  --show-toplevel` must equal the workspace. A folder inside a bigger repo, or no repo, is a no-op with status
  `not_git` (we never run `git init`).
- Before each run turn a snapshot is written to a hidden ref `refs/agentdev/run-<session>/<n>` with plumbing only:
  copy of the real index to a temp index file, `add -A`, `write-tree`, `commit-tree`, `update-ref`. HEAD, branches,
  the real index and the working tree are not touched; `git branch` does not list it. After the turn the same capture
  is stored as `.../<n>-after` (what the run left). Both are read-only captures.
- Changes of a turn = `diff-tree before after`. For each file the current worktree blob hash (`hash-object`, so CRLF
  filters match) is compared: equals `after` = `pending` (can be undone), equals `before` = `reverted`, anything else
  = `conflict` (the user edited it after the run). The state is derived, never stored, so undo is idempotent.
- Undo restores only `pending` files: modified/deleted files from `before` via a temp index + `checkout-index -f`
  (real index untouched); files the run created are deleted only if still equal to `after`, empty parent folders are
  pruned. `conflict` files are skipped and reported per file; nothing is ever overwritten. Undo is refused while a run
  is in progress.
- "Keep as branch" creates `agentdev/run-<session>` (numbered when taken) at the `after` commit with `git branch`
  (no checkout).
- Every git call: list argv (no shell), timeout, `GIT_OPTIONAL_LOCKS=0`, `core.quotepath=off`, identity passed through
  env so no user config is required. Failures degrade to a status, never to a failed run.

## Consequences
- Cost: one `add -A` per turn start/end, with the real index copied so unchanged files are not re-hashed.
- The refs are never pruned automatically; `git update-ref -d` or `git gc` after deleting them cleans up.
- Not covered: files ignored by `.gitignore` (not captured), changes outside the workspace, binary diffs (name only).
