# 0007. Field-wise clipping of member reports and old tool results

Status: accepted as opt-in, flag stays OFF by default (2026-11-06): section 12 bundle A/B (n=21 per arm) did not clear the cost and new-failure-class rule; no per-flag measurement

## Context
A member's report reached the lead cut to `MAX_MEMBER_RESULT_CHARS` (2000) keeping the first and last 1000 chars
(`team._truncate`). Evidence (`file:line`), command results and open items usually sit in the middle and were lost.
Old tool results inside one loop were cut to their first 1500 chars, so a late error line was lost too.

## Decision
`agentdev/runtime/node/agent/report_format.py` (pure functions):
- `structure_report(text, limit, fallback)`: text within the cap is unchanged. Otherwise lines are classified into
  Evidence (`path:line`), Commands (+ results), Files changed, Open items, and prose. Each field gets a share of the
  same total cap (30 / 22 / 15 / 20 %), unused room flows on, the summary prose gets the rest. Inside a field the
  newest lines win (errors first for Commands). A report with no structured line falls back to head + tail.
  Total stays at the old cap (+ at most 120 chars of note).
- `clip_old_result(text, limit)`: head 40 %, tail 30 %, error lines of the omitted middle in between.
- The member's prompt is NOT changed (no extra tokens): it already asks for files changed, test results, unresolved.
Only the lead's view is affected; the full report stays in the team state.

## Consequences
Tests: `tests/test_structured_report.py` (evidence lines survive, the old cut loses them).
