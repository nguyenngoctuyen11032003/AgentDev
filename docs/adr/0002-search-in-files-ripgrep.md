# 0002. search_in_files uses ripgrep when available

Status: accepted (2026-11-05)

## Context
The Python walker reads every file and silently skips files above 2 MB. On large repos it is slow and misses hits.

## Decision
- When `rg` is on PATH (`shutil.which`) run it with `--json`, honouring `.gitignore`, and map hits to the same
  result format (`matches[file,line,column,line_text,before,after]`, `limited`, `searched_files`, `engine`).
  `engine` becomes `"ripgrep"`. Limits (`max_results`, line clipping, globs, hidden files) are identical.
- The rg path has no 2 MB skip; binary files are still skipped by rg itself.
- Any rg failure (not found, bad regex for rg, timeout, non-0/1 exit) falls back to the Python path.
- Flag: env `AGENTDEV_SEARCH_RG` (default on; `0` forces the Python path).

## Consequences
Faster and complete on large trees. Dependency/build folders stay excluded unless a glob names them, as before.
