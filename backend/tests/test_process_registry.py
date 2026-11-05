"""Shell children (and grandchildren, even orphaned ones) die on timeout, run end and server shutdown."""

import os
import subprocess
import sys
import time

import pytest

from agentdev.utils import process_registry
from agentdev.utils.code_execution import UNSAFE_CODE_EXECUTION_ENV
from functions.function_calling.shell import run_shell_command

SLEEPER = "import time; time.sleep(60)"


def _alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _wait_dead(pid: int, seconds: float = 8.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if not _alive(pid):
            return True
        time.sleep(0.2)
    return not _alive(pid)


def _wait_file(path, seconds: float = 8.0) -> int:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if path.exists() and path.read_text().strip():
            return int(path.read_text().strip())
        time.sleep(0.1)
    raise AssertionError("pid file never written")


@pytest.fixture()
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv(UNSAFE_CODE_EXECUTION_ENV, "1")
    yield {"python_workspace_root": str(tmp_path), "session_id": "run-1"}
    process_registry.get_registry().kill_all()


def _script(tmp_path, wait_for_child: bool):
    pidfile = tmp_path / "grandchild.pid"
    # A middle process that starts a detached grandchild (own pid file) and optionally exits straight away.
    script = tmp_path / "spawn.py"
    script.write_text(
        "import subprocess, sys\n"
        f"code = 'import os,time; open(' + repr({str(pidfile)!r}) + ',\"w\").write(str(os.getpid())); time.sleep(60)'\n"
        "p = subprocess.Popen([sys.executable, '-c', code])\n"
        + ("p.wait()\n" if wait_for_child else "import time; time.sleep(1)\n"),
        encoding="utf-8",
    )
    return script, pidfile


def test_timeout_kills_grandchild(ctx, tmp_path):
    script, pidfile = _script(tmp_path, wait_for_child=True)
    out = run_shell_command(f'"{sys.executable}" "{script}"', timeout=3, _context=ctx)
    assert out.startswith("timed out")
    assert _wait_dead(_wait_file(pidfile))


def test_run_end_kills_orphaned_grandchild(ctx, tmp_path):
    """The launcher exits, the grandchild is orphaned: only the registry can still find it."""
    script, pidfile = _script(tmp_path, wait_for_child=False)
    out = run_shell_command(f'"{sys.executable}" "{script}"', timeout=30, _context=ctx)
    assert out.startswith("exit code 0")
    pid = _wait_file(pidfile)
    assert _alive(pid)
    process_registry.get_registry().kill_run("run-1")
    assert _wait_dead(pid)


def test_sweep_of_the_run_folder_kills_registered_trees(ctx, tmp_path, monkeypatch):
    from agentdev.utils.process_sweep import sweep

    script, pidfile = _script(tmp_path, wait_for_child=False)
    run_shell_command(f'"{sys.executable}" "{script}"', timeout=30, _context=ctx)
    pid = _wait_file(pidfile)
    sweep([tmp_path], since=time.time() - 60)
    assert _wait_dead(pid)


def test_kill_all_on_shutdown(ctx, tmp_path):
    script, pidfile = _script(tmp_path, wait_for_child=False)
    run_shell_command(f'"{sys.executable}" "{script}"', timeout=30, _context=ctx)
    pid = _wait_file(pidfile)
    assert process_registry.get_registry().kill_all() >= 1
    assert _wait_dead(pid)


def test_flag_off_does_not_register(ctx, tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTDEV_PROCESS_REGISTRY", "0")
    run_shell_command(f'"{sys.executable}" -c "print(1)"', _context=ctx)
    assert process_registry.get_registry().count() == 0
