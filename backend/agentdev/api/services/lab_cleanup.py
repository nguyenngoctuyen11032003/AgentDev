"""Suggest and run a per-workflow cleanup of old Lab products right after an evaluation finishes.

The Lab keeps every run's product folder (often hundreds of MB with ``node_modules``). Instead of a global
"older than N days" sweep, the user is asked at the moment it matters: an evaluation just finished, and the
older products of the same workflow have piled up. What is always kept:

* every folder of the job just finished (``keep_job``) and of the latest job that passed (the baseline the
  next evaluation is compared against, and the user's last known-good product);
* folders of running jobs, folders a running job may be writing and folders with a live preview.

Scores and history (``lab_jobs/*.json``) are never deleted here: only product folders.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from agentdev.api.services import lab_outputs as lo

SUGGEST_MIN_BYTES = 500 * 1024 * 1024
SUGGEST_MIN_RUNS = 20


def _job_sessions(job: Any, recorded: set[str]) -> set[str]:
    sessions: set[str] = set()
    for result in lo._job_results(job):
        run_dir = lo.checked_run_dir(result.get("output_dir"))
        if run_dir is not None:
            sessions.add(lo.session_key(run_dir.name))
    with contextlib.suppress(Exception):
        sessions.update(lo.session_key(d.name) for d in lo.inferred_run_dirs(job, recorded).values())
    return sessions


def _plan(workflow: str, keep_job: str) -> dict[str, Any]:
    """The folders of ``workflow`` that a cleanup would delete, and what it keeps."""
    stem = Path(workflow).stem
    jobs = lo._all_jobs()
    recorded = lo._recorded_sessions()
    _referenced, running, oldest_running = lo._references()

    keep: set[str] = set(running)
    baseline_id = ""
    newest_ready = -1.0
    for job in jobs:
        data = job.to_dict() or {}
        if Path(str(data.get("workflow") or "")).stem != stem:
            continue
        if data.get("id") == keep_job:
            keep |= _job_sessions(job, recorded)
        if data.get("verdict") == "ready" and float(data.get("started_at") or 0) > newest_ready:
            newest_ready, baseline_id = float(data.get("started_at") or 0), str(data.get("id") or "")
    if baseline_id and baseline_id != keep_job:
        job = next((j for j in jobs if (j.to_dict() or {}).get("id") == baseline_id), None)
        if job is not None:
            keep |= _job_sessions(job, recorded)

    targets: list[Path] = []
    for folder in lo._lab_dirs():
        match = lo._SESSION_NAME.match(folder.name)
        if not match or match["stem"] != stem:
            continue
        key = lo.session_key(folder.name)
        if key in keep or lo._has_live_preview(folder):
            continue
        if oldest_running is not None and key not in recorded and lo._mtime(folder) >= oldest_running - 5:
            continue  # may be the in-progress run of a running job
        targets.append(folder)
    return {"targets": targets, "baseline_job": baseline_id}


def suggestion(workflow: str, keep_job: str = "") -> dict[str, Any]:
    """Whether to offer a cleanup now, and how much it would free (sizes are measured, so this walks folders)."""
    plan = _plan(workflow, keep_job)
    runs = len({lo.session_key(p.name) for p in plan["targets"]})
    size = sum(lo.dir_size(p) for p in plan["targets"])
    return {"workflow": workflow, "reclaimable_runs": runs, "reclaimable_bytes": size,
            "baseline_job": plan["baseline_job"],
            "suggest": size >= SUGGEST_MIN_BYTES or runs >= SUGGEST_MIN_RUNS,
            "thresholds": {"bytes": SUGGEST_MIN_BYTES, "runs": SUGGEST_MIN_RUNS}}


def cleanup(workflow: str, keep_job: str = "") -> dict[str, Any]:
    plan = _plan(workflow, keep_job)
    deleted = freed = 0
    for folder in plan["targets"]:
        lo._stop_previews(folder)
        freed += lo._remove_tree(folder)
        if not folder.exists():
            deleted += 1
    return {"deleted": deleted, "freed_bytes": freed, "baseline_job": plan["baseline_job"]}
