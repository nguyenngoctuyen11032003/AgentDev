# Lab baseline: main vs audit/round-2 (real model)

Date 2026-11-05. One job per code version, 2 scenarios x 1 repeat, workflow `zz_lab_baseline` (one Haiku agent `claude-haiku-5-5`, no tools, no paid gate). Judge = account mid model (claude-sonnet-5-5), 1 call per run (4 judge calls total). Account: logged-in Anthropic CLI, no API key.
main = commit 0cf0e7e (worktree); branch = same commit plus the uncommitted round-2 working tree. Isolated storage/workflows dirs (scratchpad), real storage untouched.

| | main | audit/round-2 |
|---|---|---|
| Runs / judge calls | 2 / 2 | 2 / 2 |
| Agent tokens (run1 + run2) | 1479 + 1529 = 3008 | 1479 + 1539 = 3018 |
| Agent cost USD | 0.0003 + 0.0005 = 0.0008 | 0.0003 + 0.0003 = 0.0006 |
| Judge tokens | 2692 + 2822 = 5514 | 2741 + 2852 = 5593 |
| Judge cost USD | 0.011523 + 0.012224 = 0.023747 | 0.011685 + 0.012301 = 0.023986 |
| Job wall seconds | 9.4 (avg run 4.2) | 8.4 (avg run 3.5) |
| Scores | 10, 10 (pass 2/2, verdict ready) | 10, 10 (pass 2/2, verdict ready) |
| cache_read on agent turn | 0 | 790 / 792 |
| cost_known flag | absent | true (run and judge) |
| escalated_from | none | none |

Total real spend about 0.049 USD (both jobs, agent + judge).

Observations
- Same quality and nearly identical token counts; the judge dominates cost (about 97%).
- Branch reports `cost_known` and `evidence: []`; main does not.
- Branch shows prompt cache reads (about 790 tokens) on a tiny prompt; main shows 0. Small sample (n=2), so timing and cost differences are within noise.
- The judge uses Sonnet, not Haiku, by design (`_judge_model`).
