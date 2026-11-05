# Review fixes (frontend)

1. LaunchView render window: REAL. `followTail` (utils/messageWindow.js) called in `addDialogue` for the user's own message. Test: messageWindow.test.js.
2. LabWorkbench Batch tab: REAL. Error state + retry (i18n lab.tabs.load_failed/retry); tab now mounted on first visit and hidden (v-show), so a running batch survives tab switches. e2e: lab.spec.js (chunk failure + retry; hidden panel).
3. logoutToast: REAL, but the backend response has no reason field (only `cliLoggedOut`), so the frontend derives it with `sharesCliLogin` (another CLI connection of the same vendor existed before delete) and shows neutral info `logout_cli_kept`. Test in connectionsLogic.test.js. Optional backend follow-up: return `cliKept: true`.
4. googleOAuth: REAL. Popup closed on every reject path; `flow.cancelled`; ConnectDialog shows no error toast when the dialog is closed mid sign-in. Test added.
5. lab.errors.lab_yaml_invalid: added in vi/en/zh (did not exist yet).
