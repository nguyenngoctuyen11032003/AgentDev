# A5 fixes (Skill library)

| id | status | test file |
|---|---|---|
| A5-01 | fixed (copy to temp, swap, restore on failure) | backend/tests/test_skill_library.py::test_import_overwrite_keeps_old_on_copy_failure |
| A5-02 | fixed (createLatest ticket + editor.loading locks Save) | frontend/src/components/form/skillPickerLogic.test.js (createLatest) |
| A5-03 | fixed (filter by valid, logic in skillPickerLogic.js) | frontend/src/components/form/skillPickerLogic.test.js |
| A5-04 | fixed (loadError block with hint + Retry, list ticket) | skipped test: no DOM test infra (no jsdom/test-utils); covered by createLatest test |
| A5-05 | fixed (skills.missing key vi/en/zh) | none (copy-only) |
| A5-06 | fixed (refetch on visibilitychange + refresh button, listener removed on unmount) | none (no DOM infra) |
| A5-07 | fixed (loading, error+hint+retry, no-results, aria-live, unmount cancel) | none (no DOM infra) |
| A5-08 | skipped (SUSPECTED, not confirmed) | - |
| A5-09 | skipped (M, needs backend error-code contract across routes + UI map; out of this pass) | - |
| A5-10 | fixed (atomic write via tmp + os.replace; rename after write) | test_rename_with_failed_write_keeps_old_name, test_save_is_atomic_write |
| extra | _iter_skill_dirs ignores dot-folders (temp import dirs) | covered by A5-01 test |

Note: frontend has no component-test deps, so logic was extracted to pure modules (skillPickerLogic.js, utils/latestOnly.js). Backend tests were red before the fix.
