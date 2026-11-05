"""Processes agents leave running inside a run folder are found (only theirs) and stopped."""

import os
import subprocess
import sys
import time
from pathlib import Path

from agentdev.utils import process_sweep
from agentdev.utils.process_sweep import ProcInfo, find_leftovers

RUN = Path(r"D:\data\warehouse\lab_wf_20261105090708_4e89e6_20261105090723")


def test_finds_tree_roots_started_during_the_run_only():
    me = os.getpid()
    procs = [
        ProcInfo(me, 1, 100.0, "python main.py"),
        ProcInfo(10, 1, 1000.0, rf"node {RUN}\code_workspace\node_modules\.bin\concurrently.js"),
        ProcInfo(11, 10, 1000.0, rf"node {RUN}\code_workspace\client\node_modules\vite\bin\vite.js"),
        ProcInfo(12, 11, 1001.0, "node --watch src/index.js"),  # no path, but under a hit: killed with its tree
        ProcInfo(20, 1, 500.0, rf"node {RUN}\code_workspace\server.js"),  # older than the run: the user's own
        ProcInfo(30, 1, 1000.0, "node D:/other/project/server.js"),
        ProcInfo(40, 1, 1000.0, rf"node {str(RUN).replace(chr(92), '/')}/code_workspace/app.js"),  # forward slashes
        ProcInfo(50, 1, 1000.0, rf"node {RUN}\code_workspace\preview.js"),  # a live preview
    ]
    found = find_leftovers([RUN], since=999.0, keep_pids=[50], procs=procs)
    assert sorted(p.pid for p in found) == [10, 40]


def test_never_targets_this_server():
    me = os.getpid()
    procs = [ProcInfo(me, 1, 2000.0, rf"python {RUN}\x.py")]
    assert find_leftovers([RUN], since=0, procs=procs) == []


def test_sweep_kills_a_real_leftover(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTDEV_SWEEP_IN_TESTS", "1")
    folder = tmp_path / "lab_wf_run"
    folder.mkdir()
    script = folder / "server_left_running.py"
    script.write_text("import time\nwhile True: time.sleep(1)\n", encoding="utf-8")
    started = time.time()
    # The base interpreter, not the venv launcher (which runs the real python as a second process).
    proc = subprocess.Popen([getattr(sys, "_base_executable", sys.executable), str(script)])
    try:
        time.sleep(1.5)
        killed = process_sweep.sweep([folder], started)
        assert killed, "the leftover process was not found"
        proc.wait(timeout=10)  # it is gone
    finally:
        if proc.poll() is None:
            proc.kill()
