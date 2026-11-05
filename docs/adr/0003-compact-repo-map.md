# 0003. Compact repo map instead of the 160-line tree

Status: accepted (2026-11-05)

## Context
`attachment_service` gives the lead/members a flat tree of up to 160 lines for an uploaded project. Large repos
are cut off and the model learns nothing about what lives inside files.

## Decision
- New helper `agentdev/api/services/repo_map.py`: a directory tree (collapsing big folders) plus top-level
  symbols (def/class/function/export) of the hottest files, size-capped in characters, cached by the
  mtimes of the files it read.
- `attachment_service` uses it when `AGENTDEV_REPO_MAP` is on, and falls back to the old tree otherwise.
- Default is ON only because the bench repo (`scripts/bench_repo_gen.py`) shows it is smaller than the old tree;
  sizes are recorded in the test and in the ADR follow-up below.

## Consequences
Prompt size is bounded by a character cap rather than a line count. Symbol extraction is regex based (no new
dependency) and best effort.
