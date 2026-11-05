# Review fixes (backend) 2026-11-06

1. verify_gate: needs MAC_ALLOW_UNSAFE_CODE_EXECUTION + shell `_check`; sanitized env (preview_env); status error (never pass) when refused.
2. verify_gate: cancel-aware wait (kills tree), relative executables resolve against the project root, Windows "not recognized" = error, pytest exit 5 = none, project venv python preferred, pytest ModuleNotFoundError (exit 2) = error.
3. process_registry: kill_run wired into both run-end hooks (workflow_run_service, workflow_lab); finished entries/Job handles pruned on register.
4. workflow_lab._resume: one-running-job-per-workflow guard under the same lock that registers the job.
5. autobind: provider-less node infers vendor from model prefix (claude/gpt/gemini); same-vendor account wins, else default account's own model.
6. lab route: `lab_yaml_invalid` (+ `lab_job_delete_failed`) in vi/en/zh; delete_job removes the record first, 500 on failure, outputs only afterwards.
7. file.py: Python search fallback honours root + nested .gitignore (`_GitIgnore`); duplicate `searched_files = 0` removed. Not covered: .git/info/exclude, global ignore, .ignore. rg-vs-python parity test skipped here (rg not installed).
