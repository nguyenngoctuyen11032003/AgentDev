# F10 fixes (A10 design system, token files only)

| id | status | test file |
|---|---|---|
| A10-04 (token part) | fixed: `--z-confirm: 1150` added to main.css (between --z-modal 1100 and --z-toast 1200); ConfirmHost.vue must use `var(--z-confirm, 1150)` (F1) | frontend/src/assets/styles/tokens.contrast.test.js |
| A10-01 | fixed: dark --text-muted-1/2/3/4/10 -> #999, muted-8 -> #a0a8b1; light already passed | same |
| A10-08 (additive part) | fixed: --fg-faint added | none (no consumer yet) |
| A10-09 / A10-10 (token part) | fixed: --radius-xs/-pill, --fs-sm/md/lg, --shadow-1/2/3/focus added (additive, unused) | none |
| A10-02, 03, 05, 06, 07, 11, 12, 13, 14 | skipped: component/CSS edits outside the token files (A10-07 --control-h 44px is a visual change; wait for snapshot refresh) | - |

Contrast (ratio on surface-1..5 worst case, dark): muted-1 before 3.63 (surface-5) -> after 4.70; muted-3 3.78 -> 4.70; muted-10 3.85 -> 4.70; muted-8 4.35 -> 5.57. On surface-2: muted-1 4.17 -> 5.40, muted-2 4.23 -> 5.40, muted-3 4.34 -> 5.40, muted-10 4.43 -> 5.40. Light: min 5.28 (#556274 on surface-5), already passing.
Test checks all 10 muted tokens x 9 surfaces x 2 themes >= 4.5 (red before: 6 dark tokens failed; green after).
Snapshots not refreshed (dark muted shift may change visual.spec snapshots slightly).
