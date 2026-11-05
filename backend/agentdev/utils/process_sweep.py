"""Stop processes an agent started inside a run's folder and left running after the run ended.

Agents test what they build (``npm run dev``, ``node server.js``, ``uvicorn``...) through a CLI or the shell
tool, and those processes outlive the agent: the CLI exits, they are orphaned and keep their ports. A Lab
app that hardcoded Vite's port 5173 kept answering on ``localhost:5173`` after its run, in front of AgentDev's
own UI. When a run ends, every process whose command line points into the run's folder and that started
during the run is killed with its whole tree.

Safety: only processes created after the run started (so nothing the user had running before, such as
their own dev server in an opened project), never this server or its ancestors, never a Lab preview
("Chạy thử") the user started on purpose, and only command lines that contain the folder path.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_LIST_TIMEOUT = 20
_CREATION_SLACK = 2.0  # seconds of clock skew between the run start and the process creation time


@dataclass(frozen=True)
class ProcInfo:
    pid: int
    ppid: int
    created: float  # epoch seconds, 0 when unknown
    cmd: str


def _no_window() -> dict:
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}


def list_processes() -> list[ProcInfo]:
    """Every process with its parent, creation time and command line (empty list when it cannot be read)."""
    try:
        if os.name == "nt":
            script = ("Get-CimInstance Win32_Process | ForEach-Object { [pscustomobject]@{ p = $_.ProcessId; "
                      "q = $_.ParentProcessId; c = $_.CommandLine; t = if ($_.CreationDate) "
                      "{ ([DateTimeOffset]$_.CreationDate).ToUnixTimeSeconds() } else { 0 } } } | ConvertTo-Json -Compress")
            out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace",
                                 timeout=_LIST_TIMEOUT, check=False, **_no_window()).stdout
            rows = json.loads(out or "[]")
            rows = rows if isinstance(rows, list) else [rows]
            return [ProcInfo(int(r.get("p") or 0), int(r.get("q") or 0), float(r.get("t") or 0), r.get("c") or "")
                    for r in rows if isinstance(r, dict)]
        out = subprocess.run(["ps", "-eo", "pid=,ppid=,etimes=,args="], capture_output=True, text=True,
                             timeout=_LIST_TIMEOUT, check=False).stdout
        now = time.time()
        procs = []
        for line in out.splitlines():
            parts = line.split(None, 3)
            if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
                elapsed = float(parts[2]) if parts[2].isdigit() else now
                procs.append(ProcInfo(int(parts[0]), int(parts[1]), now - elapsed, parts[3] if len(parts) > 3 else ""))
        return procs
    except Exception as exc:  # noqa: BLE001 - a sweep is best effort
        logger.debug("Cannot list processes: %s", exc)
        return []


def _variants(folder: Path) -> list[str]:
    text = str(folder)
    forms = {text, text.replace("\\", "/"), text.replace("/", "\\")}
    return [f.casefold() for f in forms if len(f) > 8]


def _protected(procs: dict[int, ProcInfo], keep: Iterable[int]) -> set[int]:
    """This server, its ancestors, and the trees under ``keep`` (live previews)."""
    protected = {0, os.getpid()}
    pid = os.getpid()
    for _ in range(64):
        info = procs.get(pid)
        if info is None or info.ppid in protected:
            break
        protected.add(info.ppid)
        pid = info.ppid
    children: dict[int, list[int]] = {}
    for info in procs.values():
        children.setdefault(info.ppid, []).append(info.pid)
    stack = [p for p in keep if p]
    while stack:
        pid = stack.pop()
        if pid in protected:
            continue
        protected.add(pid)
        stack.extend(children.get(pid, []))
    return protected


def find_leftovers(folders: Iterable[Path], since: float, keep_pids: Iterable[int] = (),
                   procs: list[ProcInfo] | None = None) -> list[ProcInfo]:
    """Processes started after ``since`` whose command line points into one of ``folders`` (tree roots only)."""
    needles = [v for folder in folders for v in _variants(Path(folder))]
    if not needles:
        return []
    table = {p.pid: p for p in (procs if procs is not None else list_processes())}
    protected = _protected(table, keep_pids)
    hits = {p.pid for p in table.values()
            if p.pid not in protected and p.created and p.created >= since - _CREATION_SLACK
            and any(n in p.cmd.casefold() for n in needles)}
    # Kill each tree once: drop hits whose ancestor is also a hit (taskkill /T takes the descendants).
    roots = []
    for pid in hits:
        parent, seen = table[pid].ppid, set()
        while parent in table and parent not in seen and parent not in hits:
            seen.add(parent)
            parent = table[parent].ppid
        if parent not in hits:
            roots.append(table[pid])
    return roots


def _kill_tree(pid: int) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=10,
                           check=False, **_no_window())
        else:
            import signal

            os.kill(pid, signal.SIGKILL)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Cannot kill %s: %s", pid, exc)


def _preview_pids() -> list[int]:
    try:
        from agentdev.api.services.app_preview import get_preview_manager

        manager = get_preview_manager()
        with manager._lock:
            previews = list(manager._previews.values())
        return [proc.pid for preview in previews for _label, proc in list(preview.procs)]
    except Exception:  # noqa: BLE001 - previews unavailable: nothing to protect
        return []


def sweep(folders: Iterable[Path], since: float) -> list[ProcInfo]:
    """Kill what an agent left running inside ``folders`` since ``since``; returns what was killed."""
    folders = list(folders)
    try:
        from agentdev.utils.process_registry import get_registry

        get_registry().kill_for_folders(folders)  # run end / cancel: registered trees die first
    except Exception:  # noqa: BLE001
        logger.debug("Registry cleanup failed", exc_info=True)
    if "pytest" in sys.modules and not os.environ.get("AGENTDEV_SWEEP_IN_TESTS"):
        return []  # unit tests run workflows on fake folders: never touch the machine's processes
    leftovers = find_leftovers(folders, since, _preview_pids())
    for proc in leftovers:
        logger.warning("Stopping process left running by an agent (pid %s): %s", proc.pid, proc.cmd[:300])
        _kill_tree(proc.pid)
    return leftovers
