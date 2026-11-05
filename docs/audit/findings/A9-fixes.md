# A9 fixes (Lab) + A1-01 Batch entry

| id | status | test file |
|---|---|---|
| A9-1 (P1) one job per workflow, 409 `lab_job_running` (check+register under one lock) | fixed | backend/tests/test_lab_hardening.py |
| A9-2 "Run this workflow for real" link to /launch?workflow= (verdict block) | fixed | frontend/src/views/labView.test.js |
| A9-3 coded errors for evaluate/check/generate + errText in LabView | fixed | test_lab_hardening.py, labView.test.js |
| A9-4 resume errors via `LabError(code)` (vi text removed) | fixed | test_lab_hardening.py, test_workflow_lab.py (updated) |
| A9-5 no `startsWith('interrupted')`, only `job.interrupted` | fixed | labView.test.js |
| A9-6 (P3) `lab.batch_link_label`, no arrow stripping | fixed | labView.test.js |
| A9-7 (P3) LabRunPreview `tr` fallbacks and DEVICES labels removed (uses `t`) | fixed (LabRunPreview only; other `tr` copies left) | labView.test.js |
| A9-8 avg cost excludes failed/unpriced runs (server `avg_run_cost_usd`) | fixed | test_lab_hardening.py |
| A9-9 (P3) DELETE /api/lab/jobs/{id} + delete button in LabHistory (refused while running) | fixed | test_lab_hardening.py, labView.test.js |
| A9-10 touch targets <=720px (.btn.sm, scenario name, selects) | fixed (CSS, not measured live) | - |
| A9-11, A9-12 | skipped (P3 suspected / no defect) | - |
| A1-01 Batch Run link same-tab, no target=_blank | fixed (App.vue sidebar part belongs to another agent; Batch-as-Lab-tab not done) | labView.test.js |
| Judge prefers other vendor than default, skips logged-out CLI | fixed; test_workflow_lab.py judge tests updated deliberately | test_lab_hardening.py |

Note: e2e/lab.spec.js "literal scenario" test fails on an unmocked GET .../runs/<id>/files 404 against the real backend (mock job); not caused by these changes.
