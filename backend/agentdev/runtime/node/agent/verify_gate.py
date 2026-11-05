"""Verify gate: the lead of a team may not finish while the project's own tests are red.

Behind ``AGENTDEV_VERIFY_GATE`` (default off, see docs/adr/0004-verify-gate.md). When the top lead ends its turn,
the engine runs the verification command (declared in the workflow as ``team.verify_command`` or auto-detected)
in the run workspace and, if it fails or times out, hands the real result back to the lead as feedback so it can
delegate again. The caller bounds the rounds (``MAX_ROUNDS``). A timeout is never approval; a command that cannot
run at all (not found) is a no-op, not a failure.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ENV_FLAG = "AGENTDEV_VERIFY_GATE"
ENV_TIMEOUT = "AGENTDEV_VERIFY_TIMEOUT_S"
MAX_ROUNDS = 2  # feedback rounds per lead turn: the lead may be sent back at most this many times
DEFAULT_TIMEOUT_S = 180
OUTPUT_LIMIT = 3000  # characters of command output handed to the lead (tail)
# Exit codes of "command not found": POSIX shells and cmd.exe.
_NOT_FOUND_CODES = (127, 9009)
_NPM_STUB = re.compile(r"no test specified", re.IGNORECASE)


def enabled() -> bool:
    return os.environ.get(ENV_FLAG, "0").strip().lower() in ("1", "true", "on", "yes")


def timeout_seconds() -> float:
    try:
        return max(1.0, float(os.environ.get(ENV_TIMEOUT, DEFAULT_TIMEOUT_S)))
    except ValueError:
        return float(DEFAULT_TIMEOUT_S)


@dataclass
class VerifyResult:
    status: str  # pass | fail | timeout | error | none
    command: str = ""
    returncode: Optional[int] = None
    output: str = ""
    duration_s: float = 0.0

    def as_dict(self) -> dict:
        return {"status": self.status, "command": self.command, "returncode": self.returncode,
                "duration_s": round(self.duration_s, 2), "output_tail": self.output[-400:]}


def blocks_finish(result: VerifyResult) -> bool:
    """Only a real failure or a timeout stops the lead; pass, none and error (cannot run) let it finish."""
    return result.status in ("fail", "timeout")


# ---------------------------------------------------------------- detection

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _pytest_command() -> Optional[str]:
    if importlib.util.find_spec("pytest") is None:
        return None
    return f'"{sys.executable}" -B -m pytest -q -x --tb=short -p no:cacheprovider'


def detect_command(root: Path, declared: str = "") -> Optional[str]:
    """The declared command, else npm test / pytest / make test when the project has one, else None."""
    if declared and declared.strip():
        return declared.strip()
    root = Path(root)
    package = root / "package.json"
    if package.is_file():
        try:
            script = ((json.loads(_read(package)).get("scripts") or {}).get("test") or "").strip()
        except (ValueError, AttributeError):
            script = ""
        if script and not _NPM_STUB.search(script):
            return "npm test --silent"
    tests_dir = root / "tests"
    has_pytest = (
        (root / "pytest.ini").is_file()
        or (root / "tox.ini").is_file()
        or "[tool.pytest" in _read(root / "pyproject.toml")
        or "[tool:pytest]" in _read(root / "setup.cfg")
        or (tests_dir.is_dir() and any(tests_dir.glob("test_*.py")))
    )
    if has_pytest:
        command = _pytest_command()
        if command:
            return command
    makefile = root / "Makefile"
    if makefile.is_file() and re.search(r"^test\s*:", _read(makefile), re.MULTILINE):
        return "make test"
    return None


# ---------------------------------------------------------------- runner

def _tail(text: str) -> str:
    if len(text) <= OUTPUT_LIMIT:
        return text
    return f"[... {len(text) - OUTPUT_LIMIT} earlier characters omitted ...]\n" + text[-OUTPUT_LIMIT:]


_SHELL_BUILTINS = {"echo", "dir", "type", "cd", "set", "call", "exit", "test", "true", "false", "cmd", "powershell"}


def _executable_missing(command: str) -> bool:
    """True when the first word of ``command`` is neither a program on PATH nor a path nor a shell builtin."""
    try:
        words = shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return False
    if not words:
        return True
    first = words[0].strip("\"'")
    if first.lower() in _SHELL_BUILTINS:
        return False
    return shutil.which(first) is None and not Path(first).exists()


def run_verification(root: Path, command: str, run_id: str, timeout: Optional[float] = None) -> VerifyResult:
    """Run ``command`` in ``root`` with a hard timeout; the whole process tree dies on timeout.

    The process is registered in the process registry (so cancel / run end / shutdown also kill it) and its
    output goes to a temp file, so a background grandchild holding a pipe can never block the gate.
    """
    from agentdev.connections.cli_auth import kill_process_tree
    from agentdev.utils.process_registry import enabled as registry_enabled, get_registry

    if _executable_missing(command):
        return VerifyResult("error", command, None, "command not found")
    limit = timeout if timeout is not None else timeout_seconds()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "CI": "1"}
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(root), env.get("PYTHONPATH", "")) if p)
    env.pop("PYTEST_ADDOPTS", None)
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    started = time.monotonic()
    with tempfile.TemporaryFile() as sink:
        try:
            proc = subprocess.Popen(command, shell=True, cwd=str(root), env=env, stdin=subprocess.DEVNULL,
                                    stdout=sink, stderr=subprocess.STDOUT, **kwargs)
        except OSError as exc:
            return VerifyResult("error", command, None, str(exc), time.monotonic() - started)
        registry = get_registry()
        registry.register(run_id, proc, root)
        timed_out = False
        try:
            proc.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            timed_out = True
            if registry_enabled():
                registry.kill_process(run_id, proc)
            kill_process_tree(proc)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        sink.seek(0)
        output = _tail(sink.read().decode("utf-8", errors="replace").strip())
    duration = time.monotonic() - started
    if timed_out:
        return VerifyResult("timeout", command, None, output, duration)
    code = proc.returncode
    if code == 0:
        return VerifyResult("pass", command, 0, output, duration)
    if code in _NOT_FOUND_CODES:
        return VerifyResult("error", command, code, output, duration)
    return VerifyResult("fail", command, code, output, duration)


def feedback_text(result: VerifyResult, round_no: int) -> str:
    """What the lead is told when it tried to finish and the verification did not pass."""
    if result.status == "timeout":
        state = "did not finish in time (a timeout is not a pass)"
    else:
        state = f"failed (exit code {result.returncode})"
    return (
        f"[VERIFY GATE, round {round_no} of {MAX_ROUNDS}] You tried to finish, but the project's verification "
        f"command {state}.\nCommand: {result.command}\nOutput (tail):\n{result.output or '(no output)'}\n\n"
        "Do not finish yet. Brief a team member (for example the developer) with this result to fix the cause "
        "in the project, then confirm it passes. If the failure is unrelated to the task or cannot be fixed, say "
        "so plainly in your final answer; never call the work verified."
    )
