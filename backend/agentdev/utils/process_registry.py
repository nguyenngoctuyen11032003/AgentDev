"""Per-run registry of child processes, killed as whole trees on timeout, run end, cancel and shutdown.

``taskkill /T`` and a process-group kill follow the parent chain only: a dev server started with ``start /b`` or
``cmd &`` whose launcher already exited is orphaned and survives. On Windows every registered process is put in a
Job Object (descendants stay in the job even after their parent exits; KILL_ON_JOB_CLOSE also takes them down when
the server dies). On POSIX the process lives in its own session, so its process group is killed.

Flag: ``AGENTDEV_PROCESS_REGISTRY`` (default on; "0"/"false"/"off" disables registration, never the plain kill).
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ENV_FLAG = "AGENTDEV_PROCESS_REGISTRY"


def enabled() -> bool:
    return os.environ.get(_ENV_FLAG, "1").strip().lower() not in ("0", "false", "off", "no")


# ---------------------------------------------------------------------------
# Windows Job Objects (ctypes, no extra dependency)
# ---------------------------------------------------------------------------

def _kernel32():
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    return k32


def _create_job() -> Optional[int]:
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        k32 = _kernel32()
        job = k32.CreateJobObjectW(None, None)
        if not job:
            return None

        class _Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class _IoCounters(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("a", "b", "c", "d", "e", "f")]

        class _Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", _Basic), ("IoInfo", _IoCounters),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        info = _Extended()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            k32.CloseHandle(job)
            return None
        return int(job)
    except Exception:  # noqa: BLE001 - fall back to taskkill /T
        logger.debug("Cannot create a Job Object", exc_info=True)
        return None


def _assign_job(job: int, proc: subprocess.Popen) -> bool:
    try:
        k32 = _kernel32()
        handle = k32.OpenProcess(0x0100 | 0x0001, False, proc.pid)  # SET_QUOTA | TERMINATE
        if not handle:
            return False
        try:
            return bool(k32.AssignProcessToJobObject(job, handle))
        finally:
            k32.CloseHandle(handle)
    except Exception:  # noqa: BLE001
        return False


def _close_job(job: int, terminate: bool = True) -> None:
    try:
        k32 = _kernel32()
        if terminate:
            k32.TerminateJobObject(job, 1)
        k32.CloseHandle(job)
    except Exception:  # noqa: BLE001
        logger.debug("Cannot close a Job Object", exc_info=True)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

@dataclass
class _Entry:
    proc: subprocess.Popen
    job: Optional[int]
    root: Optional[str]


def _norm(path: Any) -> str:
    try:
        return os.path.normcase(str(Path(path).resolve()))
    except OSError:
        return os.path.normcase(str(path))


def _kill_entries(entries: list[_Entry]) -> int:
    from agentdev.connections.cli_auth import kill_process_tree

    for e in entries:
        if e.job is not None:
            _close_job(e.job)
        if e.proc.poll() is None:
            kill_process_tree(e.proc)  # taskkill /T or killpg: also covers a failed Job Object
        try:
            e.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("Process %s did not exit after kill", e.proc.pid)
    return len(entries)


@dataclass
class ProcessRegistry:
    _runs: dict[str, list[_Entry]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def register(self, run_id: str, proc: subprocess.Popen, root: Any = None) -> None:
        """Track ``proc`` (and everything it spawns from now on) under ``run_id``."""
        if not enabled():
            return
        job = _create_job()
        if job is not None and not _assign_job(job, proc):
            _close_job(job, terminate=False)
            job = None
        entry = _Entry(proc, job, _norm(root) if root else None)
        with self._lock:
            entries = self._runs.setdefault(run_id, [])
            # Without a job a dead process has nothing left to kill; with one, orphans may still run.
            entries[:] = [e for e in entries if e.job is not None or e.proc.poll() is None]
            entries.append(entry)

    def kill_process(self, run_id: str, proc: subprocess.Popen) -> int:
        """Kill one registered process tree (a timed-out command) and keep the run's other trees."""
        with self._lock:
            entries = self._runs.get(run_id, [])
            taken = [e for e in entries if e.proc is proc]
            entries[:] = [e for e in entries if e.proc is not proc]
        return _kill_entries(taken)

    def kill_run(self, run_id: str) -> int:
        with self._lock:
            entries = self._runs.pop(run_id, [])
        return _kill_entries(entries)

    def kill_for_folders(self, folders: Iterable[Path]) -> int:
        roots = [_norm(f) for f in folders]
        taken: list[_Entry] = []
        with self._lock:
            for run_id in list(self._runs):
                keep = []
                for e in self._runs[run_id]:
                    inside = e.root is not None and any(e.root == r or e.root.startswith(r + os.sep) for r in roots)
                    (taken if inside else keep).append(e)
                if keep:
                    self._runs[run_id] = keep
                else:
                    del self._runs[run_id]
        return _kill_entries(taken)

    def kill_all(self) -> int:
        with self._lock:
            entries = [e for items in self._runs.values() for e in items]
            self._runs.clear()
        return _kill_entries(entries)

    def count(self, run_id: Optional[str] = None) -> int:
        with self._lock:
            if run_id is not None:
                return len(self._runs.get(run_id, []))
            return sum(len(v) for v in self._runs.values())


_registry = ProcessRegistry()


def get_registry() -> ProcessRegistry:
    return _registry
