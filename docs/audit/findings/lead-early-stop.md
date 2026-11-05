# Tech Lead stops early (nodes_run = ['Tech Lead'], 1 call, no edits)

## Cause (evidence from 2 real Haiku runs, bugfix_team, task a)
Not the plan gate (`plan_submitted=false` in both) and not a conversational answer. The lead DID try to delegate:
it called `delegate_parallel` as a native Claude Code tool_use instead of inside the JSON `tool_calls` reply.
The CLI (run with `--tools ""`) answered `No such tool available: delegate_parallel`; Haiku retried natively,
failed again and ended the single CLI call with plain text. Final texts recorded by the new `lead_final` field:
- "my attempt to start the Code Scout and Repro Analyst in parallel failed twice with 'No such tool available: delegate_parallel'. The team never ran ..."
- "The tool returned 'No such tool available: delegate_parallel', and my retry as a text reply produced no results ..."
The tool-protocol preamble already tells the model what to do on that error, but the retry loop runs inside one
`claude -p` call, so the host sees only the final text (no `tool_calls`) and treats it as the node's answer.
This also explains why the verify gate did not help (the lead re-fails the same way) and why the failure hits
`delegate_parallel` (a name that looks like a native tool) more than `delegate_task`.

## Change (backend only, no flag: it only fires when the reply has no tool calls)
- `providers/_native.py::native_calls_of_listed_tools`: reads the stream-json `assistant` tool_use blocks and returns
  those whose name is a host tool of this call (never a built-in such as Bash); repeats merged.
- `claude_cli_provider._call_once`: if the parsed reply has no tool calls, recover those native calls as tool calls
  and drop the "tool unavailable" text. The host then runs them normally (limits, gates, paid checks unchanged).
- Tests (red first): `tests/test_cli_providers.py::test_claude_tools_native_call_of_a_listed_tool_is_recovered`,
  `..._of_an_unlisted_tool_is_not_recovered`.
- `scripts/bench_projects.py`: each run now records `lead_final` (600 chars) and `plan_submitted`
  (`tests/test_bench_projects.py::test_report_records_lead_final_text_and_plan_flag`).

## Real runs used: 4 of 4 allowed (all Haiku, task a, no paid gate), about 0.015 USD
Run 1 (not lead-alone, 4 calls, fix failed: acceptance `hidden_clamp_test` false) and runs 2, 3 reproduced the
lead-alone failure (2 of the 3 runs with the new recorder; run 3 result not read, the loop was cut by a
tooling error). The fix itself is NOT yet verified with a real model; the budget was exhausted.

## Proposed verification (needs budget approval)
A/B real, bugfix_team, Haiku, task a only, n = 8 per arm (before = git stash of the provider change vs after):
16 runs x about 0.0035 USD (lead-alone runs are cheap, full runs about 0.03-0.05) = about 0.3-0.5 USD worst case.
Success criterion: lead-alone rate from about 1 in 3 on task a (observed here) to 0 of 8, with `lead_final`
logged for any remaining case. Also check Codex provider for the same pattern (not investigated).
