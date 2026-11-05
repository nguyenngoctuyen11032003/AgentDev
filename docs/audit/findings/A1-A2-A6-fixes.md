# Fixes: App shell, Home, Batch Run, General Settings (A1, A2 code part, A6)

id | status | test file
---|---|---
A1-01 | fixed in App.vue (nav bar shown on /batch-run; only /launch hides it). `target=_blank` in LabView.vue skipped: not my file (Lab owner) | frontend/src/views/shellStructure.test.js
A1-02 | fixed (dead SettingsModal, import, ref removed) | shellStructure.test.js
A1-03 | fixed (comment rewritten) | shellStructure.test.js
A1-04 | fixed (`<main>` -> `<section>` in SettingsView.vue) | shellStructure.test.js
A1-05 | fixed (BATCH_STATUS enum + label keys, raw fallback removed) | frontend/src/views/batchRunStatus.test.js
A1-06 | fixed (exception message no longer shown; backend detail goes through localizeBackendError) | batchRunStatus.test.js
A1-07 | fixed (role=status aria-live=polite on status + progress text) | no unit test (markup only), covered by structure review
A1-08 | fixed (44px min size for .btn.sm/.icon-only at <=640px) | no unit test (CSS only)
A1-09..A1-11 | skipped: P3 / Lab-owned / SUSPECTED
A2-01 | fixed (HomeView RouterLink; e2e/home.spec.js role button -> link) | shellStructure.test.js, e2e/home.spec.js
A2-02..A2-04 | skipped: tutorial markdown, not in my files (another agent has tutorialContent.test.js)
A2-06, A2-08 | skipped: P3
A6-01 | fixed (toggle, store key, SettingsModal default, 3 i18n keys x2, LaunchView v-memo line removed; legacy saved key deleted on load; unused configStore import in LaunchView removed) | shellStructure.test.js
A6-02..A6-08 | skipped: P3 / SUSPECTED
Decisions: SettingsModal kept; it already shares GeneralSettings.vue with the page. Layout: BatchRunView height now subtracts the 55px nav bar.
