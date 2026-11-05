# A3 + A4 (frontend) fixes

| id | status | test file |
|---|---|---|
| A3-01 confirm hidden under dialog | fixed (`--z-confirm, 1150` fallback in ConfirmHost; BaseDialog unchanged, stays --z-modal; token itself added by design-system agent) | e2e only (no DOM test infra in vitest) |
| A3-02 authType | fixed (`needsLiveModels`) | frontend/src/utils/connectionsLogic.test.js |
| A3-03 load error state + retry | fixed (loadError, role=alert, retry) | skipped test: no component test infra (no test-utils/jsdom); build+lint verified |
| A3-04 Google popup stuck | fixed (`utils/googleOAuth.js`: sync popup, popup_blocked, cancel, 5 min timeout; Cancel/Esc allowed while saving) | connectionsLogic.test.js |
| A3-05 signed-out counted ready | fixed (`readyCount`) | connectionsLogic.test.js |
| A3-06 raw backend strings | fixed (localizeBackendError in view + dialog) | none (covered by existing errorTranslate rules) |
| A3-10 refresh errors | fixed (`refreshQuietly`, liveModels cleared on refresh) | none (UI wiring) |
| A3-07, A3-09, A3-11, A3-12 | skipped: SUSPECTED / P3 (A3-11 unmount flag added anyway) | - |
| A3-08 44px buttons | skipped: lives in ui.css, not my file | - |
| A4-2 frontend | fixed: deleteConnection(id,{signOutCli}) -> ?sign_out_cli=true; confirm text says record-only; opt-in checkbox (default off) in ConfirmHost via confirmDialog `checkbox`; toast honors cliLoggedOut | connectionsLogic.test.js |

Extra files touched: utils/confirm.js (checkbox option), new utils/connectionsLogic.js, utils/googleOAuth.js, 3 locales (9 new keys + reworded confirm_logout_detail).
