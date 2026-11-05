# A7 fixes (workflow editor)

| id | status | test file |
|---|---|---|
| A7-1 | fixed: `:only-render-visible-elements="shouldOnlyRenderVisible(nodes.length)"` (threshold 60) | frontend/src/composables/workflow/useWorkflowLoadGuards.test.js |
| A7-2 | fixed: drag-stop goes through `createLayoutSaver` (toast `workflow_view.layout_save_failed`, one toast per 3 s cooldown, vi/en/zh) | same |
| A7-3 | fixed: `createSequenceGuard` `loadGuard`; `initializeWorkflow`, `loadYamlFile`, `loadAndSyncVueFlowGraph` drop stale results (also compare requested name to current name) | same |
| A7-4..A7-14 | not in scope (P2/P3 outside this task's list) | - |
| lazy-load VueFlow | skipped: route is already lazy, VueFlow is used directly in the template and `useVueFlow` needs it at setup; async-splitting would need a refactor with no measured gain | - |

Logic lives in `frontend/src/composables/workflow/useWorkflowLoadGuards.js` so it is unit-testable (WorkflowView is a 3k-line SFC with no mount harness). Tests were red first (module missing), now 6 green.

## Perf (npm run perf, test d, 200 nodes, drag 3 s, reused dev server on :5173)
- Before (baseline run 1): 22.6 fps avg, 19 frames >50 ms, p95 83.3 ms, 4898 DOM nodes.
- After (run 2 in perf-baseline.md): 36.5 fps avg, 0 frames >50 ms, p95 33.4 ms, 4898 DOM nodes.
- Caveat: DOM nodes unchanged because fitView shows all 200 nodes in the viewport, so culling does not remove any; the gain is likely partly run-to-run noise. Culling helps when zoomed in. Only one before/after pair, not conclusive.
