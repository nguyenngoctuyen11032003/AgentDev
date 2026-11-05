# 0001 - Per-run process registry and loopback-only previews

Status: accepted (2026-11-05)

## Context
- `run_shell_command` killed only the main process tree on timeout (`taskkill /T`, which follows the parent chain).
  A dev server started with `start /b` or `cmd &` whose launcher had exited was orphaned and survived the timeout,
  the run end and the server.
- Node/script previews (Lab app preview, ports 47100-47199) relied on `HOST` alone; servers reading `HOSTNAME` or
  `BIND*` could listen on all interfaces (audit A5-6).

## Decision
- `agentdev/utils/process_registry.py`: every shell child is registered per run id (`session_id`, fallback
  `shell`) with its workspace folder. Windows: a Job Object per process (descendants stay in the job even after
  the parent exits; `KILL_ON_JOB_CLOSE` also cleans up if the server dies). POSIX: process group (own session).
  `taskkill /T` / `killpg` stay as a fallback.
- Kill points: timeout (that command's tree only), run end and cancel (`process_sweep.sweep` for the run folder,
  used by run and Lab), server shutdown (`bootstrap` lifespan `kill_all`).
- Flag `AGENTDEV_PROCESS_REGISTRY` (default on; `0` disables registration). It only ever cleans up.
- `preview_env` forces `HOST`, `HOSTNAME`, `BIND`, `BIND_ADDR`, `SERVER_HOST` to `127.0.0.1` after any template
  or inherited value; framework templates already pass explicit `127.0.0.1` host flags.

## Not done
- A2-3 (stop already-running parallel siblings): needs interrupting an in-flight CLI/model call; not-yet-started
  siblings are already skipped. Left for a dedicated change.

## Consequences
A command that deliberately leaves a server running keeps it until the run ends; then it is stopped.
