# 0001. edit_file and multi_edit tools

Status: accepted (2026-11-05)

## Context
The only edit tool, `apply_text_edits`, is line-number based. A model that miscounts lines overwrites the wrong
range, and an `end_line` past the end of the file was silently clamped (the tail of the file was deleted).
Claude Code style `old_string -> new_string` edits are anchored to content, so they cannot hit the wrong place.

## Decision
- Add `edit_file(path, old_string, new_string, replace_all=False)` and `multi_edit(path, edits[])` to
  `workspace/functions/function_calling/file.py` (auto-registered by the function catalog; also listed in
  `WORKSPACE_WRITE_TOOLS`).
- `old_string` must match exactly once unless `replace_all`. Not found or ambiguous: error, nothing written.
- `multi_edit` applies edits in order on an in-memory copy; any failure aborts all (all-or-nothing).
- CRLF/LF and a UTF-8 BOM are preserved (the file's dominant line ending is applied to the given strings).
- Write is atomic: temp file in the same folder, then `os.replace`. Paths stay inside the workspace; the
  `attachments` folder is read-only, as for the other file tools.
- Flag: env `AGENTDEV_EDIT_TOOLS` (default on). `0`/`false`/`off` makes both tools refuse with a clear error.
- `apply_text_edits` gets a safety check: an `end_line` beyond the file is an error (was clamped), and an optional
  `expected_old` argument must equal the selected lines or the edit fails.

## Consequences
Additive: existing tools keep their signatures. The assistant reference is not extended (size guard stays green).
Only UTF-8 files are supported by the new tools; other encodings use `apply_text_edits`.
