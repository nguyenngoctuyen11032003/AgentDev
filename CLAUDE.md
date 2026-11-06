# AgentDev

Chat with a lead agent that runs an AI team (workflows of agents). FastAPI backend + Vue 3 frontend, derived from ChatDev 2.0. UI language: Vietnamese (vi/en/zh). Reply to the user in Vietnamese, short.

## Commands
Prerequisites: `uv`, Node 20+, and the `claude` (and/or `codex`) CLI logged in (no API keys). Single frontend test file: `cd frontend && npx vitest run src/path/file.test.js`.
Backend (uv project in `backend/`, run from there):
- Install: `make install` (uv sync + npm install)
- Server: `cd backend && uv run python main.py --port 6400` (binds 127.0.0.1; LAN needs `--host`/`BACKEND_BIND`; other Host names need `AGENTDEV_ALLOWED_HOSTS=a,b` (else 400); other browser origins need `CORS_ALLOW_ORIGINS`)
- Tests: `cd backend && uv run pytest -q --tb=short | tail -40` (single file: `uv run pytest tests/test_x.py -q`)
- Engine bench (fake model, free): `uv run python -m scripts.bench_engine`
- Token bench (fake model, free): `uv run python -m scripts.bench_tokens --fake` (outputs to `docs/audit/`)

Frontend (`frontend/`):
- Dev: `VITE_API_BASE_URL=http://localhost:6400 npm run dev` (port 5173; `make dev` starts both)
- Unit: `npm test` (vitest) · Build: `npm run build` · Lint: `npm run lint`
- E2E: `npm run e2e` (Playwright, `frontend/e2e/`; reuses running servers or starts its own; fake literal workflow, no tokens). Other ports: `E2E_API=http://localhost:6411 E2E_WEB=http://localhost:5175 npm run e2e`. Do not use :5174 (taken by another app).
- i18n check: `node scripts/check-i18n.mjs` (vi/en/zh must not drift)

Run full test/build/lint only at the end of a phase; otherwise run the single affected file.

## Map of the three core screens
| Screen | View | Backend |
|---|---|---|
| Quy trình (workflow editor, YAML <-> canvas, assistant) | `frontend/src/views/WorkflowView.vue`, `composables/useWorkflowAssistant.js` | `api/routes/workflows.py`, `vuegraphs.py`, `workflow_assistant.py`, `services/assistant_sessions.py` |
| Phòng thí nghiệm (Lab: score a workflow on scenarios, judge, fix brief, previews) | `views/LabView.vue` | `api/routes/lab.py`, `lab_preview.py`, `services/workflow_lab.py`, `lab_diagnosis.py`, `lab_outputs.py`, `app_preview.py` |
| Chạy (run chat, sessions, gates, products) | `views/LaunchView.vue`, `views/launch/`, `components/launch/`, `composables/useLaunch*.js`, `useSessions.js`, `useMarkdown.js` | `api/routes/execute.py`, `websocket.py`, `sessions.py`, `services/session_execution.py`, `message_handler.py`, `prompt_channel.py` |

Engine: `backend/agentdev/runtime/` (node executors in `runtime/node/executor/`, e.g. `agent_executor`, `loop_counter_executor`). API client: `frontend/src/api/client.js` (all HTTP goes through it; no raw `fetch('/api...')`).
Locales: `frontend/src/i18n/locales/{vi,en,zh}.json`. Sample workflows: `backend/tests/data`, `yaml_*` dirs.

## Invariants (never break; tests guard them)
1. Only logged-in CLI accounts; no model API keys anywhere (`tests/test_no_model_api_keys.py`).
2. Silence or timeout is NEVER approval of a gate.
3. A gate with `paid: true` is NEVER auto-approved. Never run paid steps (video render) in tests/benchmarks.
4. `tests/test_workflow_assistant.py::test_reference_is_compact` must stay green (assistant reference stays small).
5. Real-model spend in audits is capped; prefer Haiku; log tokens + cost for every real run.

## Conventions
- i18n: every user-visible string needs keys in vi, en AND zh. No hard-coded strings in `<script>`; no logic that compares displayed text.
- Run chat: every message mutation goes through `updateMessage` (LaunchView). Run status uses the `RUN_STATUS` enum (`components/launch/runStatus.js`), never string literals.
- State comes from structured events (e.g. `HANDOFF`, `EDGE_CONDITION_ERROR`), never by parsing log text.
- Several end nodes: the end node that finishes LAST with output gives the final answer (ties: declaration order). Lint `MULTIPLE_END_NODES` warns when two ends can run in one turn; prefer mutually exclusive ends.
- Every agent turn logs one JSON line on logger `agentdev.run_summary` (session, node, model, tokens, cache_read, cost_usd, cost_known, duration_s, status). Failed/timed-out calls still record usage (`cost_known=false` when no price).
- Benchmarks/tests that patch engine globals must restore them (`install_fake()` returns an undo callable).
- Edge conditions are fail-closed: an erroring condition does not fire the edge and emits a warning.
- `loop_counter`: an edge inside a loop must point back to the loop-entry step (lint in `proposal_lint.py`).
- Every child process, timer, listener, WebSocket must be cleaned on cancel/unmount/close.
- Every path that spends money has a `paid` gate, a pre-run cost estimate, and counts in `cost_usd`.
- Every UI state needs loading / empty / error (with a fix hint) / success. No endless spinners.
- Fixing a bug requires a regression test (red first).
- Comments and code identifiers in English; UI text via i18n.

- File edits by agents: prefer `edit_file`/`multi_edit` (exact unique match, keeps CRLF/BOM, atomic) over line-number edits (flag `AGENTDEV_EDIT_TOOLS`). `search_in_files` uses ripgrep when present (`AGENTDEV_SEARCH_RG`); repo map flag `AGENTDEV_REPO_MAP`.
- Engine flags (all default OFF; env `=1` enables, A/B in `docs/audit/final.md` sections 9, 11, 12): `AGENTDEV_PARALLEL_READS`, `AGENTDEV_STRUCTURED_REPORT`, `AGENTDEV_CLI_MAX_OUTPUT`, `AGENTDEV_MEMBER_PROTOCOL_SYSTEM`, `AGENTDEV_NATIVE_TOOL_RESCUE`, `AGENTDEV_VERIFY_GATE`. Flip a default only after a real A/B clears: success >= OFF, cost/time not >15% worse, no new failure class.
- Shell/background processes are registered per run and killed as a tree on timeout/cancel/shutdown (`utils/process_registry.py`, flag `AGENTDEV_PROCESS_REGISTRY`). Previews bind 127.0.0.1 only.
- Deleting the last CLI account removes only the AgentDev record; CLI sign-out needs `?sign_out_cli=true`. Autobind prefers a connection of the same vendor as `provider`.
- E2E: import `test` from `e2e/helpers/fixture.js` (fails on console.error / 4xx / 5xx not allowed). Visual snapshots: `npm run e2e:visual` (update with `e2e:visual:update`, only for intended UI changes). UI perf baseline: `npm run perf` -> `docs/audit/perf-baseline.md`. A11y: `npm run e2e:axe` (axe WCAG A/AA, 8 pages x light/dark x 375/1440; critical/serious fail the test).
- Project bench: `uv run python -m scripts.bench_projects --fake|--real` (real needs `--max-usd`; reports `nodes_run`). Every engine change is measured with it; real runs are logged in `docs/audit/final.md`.

## Large files: do NOT read whole (Grep, then Read with offset/limit)
`views/LaunchView.vue` (~6.1k lines), `views/WorkflowView.vue` (~3.1k), `views/LabView.vue` (~1.5k), `api/services/workflow_lab.py` (~1.6k), `i18n/locales/*.json`, `package-lock.json`, `backend/uv.lock`.

## Git
Work on a branch, never on `main`. Commits must have no Claude author/co-author (use the `clean-commit` skill); do not commit/push/merge without the user's approval. Audit reports live in `docs/audit/`.
