# Phase 0.1 E2E findings

Product bugs found while writing the page journeys. Tests that expose a real bug are marked `test.fixme` with the id.

| id | page | evidence | suspected cause |
|---|---|---|---|
| P0-E2E-01 | settings/skills (also any `confirmDialog()` opened while a `BaseDialog` is open, e.g. logout from the connection detail dialog) | `frontend/e2e/settings-skills.spec.js` > "saving an existing name asks before overwriting" (fixme). Playwright: the "Ghi đè" button of the `alertdialog` cannot be clicked, `textarea ... from <div class="base-dialog-backdrop"> subtree intercepts pointer events` (223 retries). The user cannot confirm the overwrite, so saving an existing skill name is stuck. | `frontend/src/components/common/ConfirmHost.vue:87` and `frontend/src/components/common/BaseDialog.vue:151` both use `z-index: var(--z-modal)` (1100, `assets/styles/main.css:21`) and both teleport to `body`; the dialog opens later so it sits later in the DOM and covers the confirm. Fix: give the confirm a higher layer (e.g. `--z-confirm`) or teleport it after the dialog. |

## Notes (not bugs)

- Two Playwright runs at the same time share `e2e/artifacts/test-results` and the `zz_e2e_fake` workflow, which gives random ENOENT / 409 / vanishing-workflow failures. Run a second suite with `E2E_WORKFLOW_ID=zz_e2e_other E2E_OUTPUT=e2e/artifacts/other npm run e2e`.
- The workflow YAML tab is read-only (textarea `readonly`), so there is no "broken YAML typed by hand" path to test.
