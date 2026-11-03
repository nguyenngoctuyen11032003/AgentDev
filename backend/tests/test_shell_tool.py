"""run_shell_command: gated by the server opt-in, confined to the workspace, guards obvious disasters."""

import sys
import time

import pytest

from agentdev.utils.code_execution import UNSAFE_CODE_EXECUTION_ENV
from agentdev.utils.exceptions import SecurityError
from functions.function_calling import shell
from functions.function_calling.shell import run_shell_command


@pytest.fixture()
def ctx(tmp_path):
    (tmp_path / "app").mkdir()
    return {"python_workspace_root": str(tmp_path)}


def test_disabled_without_opt_in(ctx, monkeypatch):
    monkeypatch.delenv(UNSAFE_CODE_EXECUTION_ENV, raising=False)
    with pytest.raises(SecurityError):
        run_shell_command("echo hi", _context=ctx)


def test_runs_in_workspace_and_reports_exit_code(ctx, tmp_path, monkeypatch):
    monkeypatch.setenv(UNSAFE_CODE_EXECUTION_ENV, "1")
    py = f'"{sys.executable}"'
    out = run_shell_command(f'{py} -c "import os; print(os.getcwd())"', cwd="app", _context=ctx)
    assert out.startswith("exit code 0") and str(tmp_path / "app") in out
    out = run_shell_command(f'{py} -c "import sys; sys.exit(3)"', _context=ctx)
    assert out.startswith("exit code 3")


def test_cwd_cannot_escape(ctx, monkeypatch):
    monkeypatch.setenv(UNSAFE_CODE_EXECUTION_ENV, "1")
    with pytest.raises(ValueError, match="inside the project"):
        run_shell_command("echo hi", cwd="../..", _context=ctx)


BLOCKED = [
    "rm -rf /",
    "rm -r -f /",
    "rm -rf ~/",
    "rm -rf $HOME",
    "rm -rf ..",
    "rm -rf C:",
    "rm -rf c:\\ ",
    "rd /s /q C:\\ ",
    "rd /s /q C:\\Users",
    "rmdir /s /q C:\\Users\\TUYEN",
    "del /s /q C:\\*",
    "powershell -c Remove-Item -Recurse -Force $env:USERPROFILE",
    "powershell -NoProfile -Command \"Remove-Item -Recurse -Force -Path $env:USERPROFILE\"",
    "git push origin main",
    "git -C . push",
    "git -c user.name=x push --force",
    "echo hi & git push",
    "echo $(git push)",
    "npm publish",
    "npm publish --dry-run",
    "pnpm -r publish",
    "yarn npm publish",
    "twine upload dist/*",
    "python -m twine upload dist/*",
    "cargo publish",
    "dotnet nuget push x.nupkg",
    "gem push x.gem",
    "shutdown /s",
    "sudo reboot",
    "format C:",
    "format c:",
    ":(){ :|:& };:",
]

ALLOWED = [
    "npm run format",
    "npm run format:check",
    "dotnet format",
    "git status",
    "git diff",
    "npm test",
    "pytest -q",
    "git log --grep=shutdown",
    "pytest -k test_graceful_shutdown",
    "grep -rn halt src",
    "git commit -m 'graceful shutdown handler'",
    "npm run halt-check",
    "node scripts/reboot-db.js",
    "echo format d: test",
    "rm -rf node_modules",
    "rm -rf ./*",
    "rm -rf *",
    "rm -rf . ",
    "rd /s /q dist",
    "del /s /q build\\*.obj",
]


@pytest.mark.parametrize("command", BLOCKED)
def test_blocked_commands(ctx, monkeypatch, command):
    monkeypatch.setenv(UNSAFE_CODE_EXECUTION_ENV, "1")
    with pytest.raises(ValueError, match="Blocked"):
        run_shell_command(command, _context=ctx)


@pytest.mark.parametrize("command", ALLOWED)
def test_allowed_commands_pass_the_guard(tmp_path, command):
    assert shell._check(command, tmp_path.resolve(), tmp_path.resolve()) is None


def test_parent_target_allowed_when_still_inside_workspace(tmp_path):
    root = tmp_path.resolve()
    (root / "app").mkdir()
    assert shell._check("rm -rf ../dist", root, root / "app") is None
    assert shell._check("rm -rf ../..", root, root / "app") is not None


def test_timeout(ctx, monkeypatch):
    monkeypatch.setenv(UNSAFE_CODE_EXECUTION_ENV, "1")
    out = run_shell_command(f'"{sys.executable}" -c "import time; time.sleep(5)"', timeout=1, _context=ctx)
    assert out.startswith("timed out after 1s")


def test_timeout_kills_grandchild_holding_pipes(ctx, tmp_path, monkeypatch):
    monkeypatch.setenv(UNSAFE_CODE_EXECUTION_ENV, "1")
    script = tmp_path / "spawn.py"
    script.write_text(
        "import subprocess, sys\n"
        "print('started', flush=True)\n"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "p.wait()\n",
        encoding="utf-8",
    )
    start = time.monotonic()
    out = run_shell_command(f'"{sys.executable}" "{script}"', timeout=2, _context=ctx)
    elapsed = time.monotonic() - start
    assert out.startswith("timed out after 2s")
    assert "started" in out
    assert elapsed < 2 + 6


def test_exited_command_with_background_child_returns(ctx, tmp_path, monkeypatch):
    monkeypatch.setenv(UNSAFE_CODE_EXECUTION_ENV, "1")
    script = tmp_path / "orphan.py"
    script.write_text(
        "import subprocess, sys\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "print('parent done', flush=True)\n",
        encoding="utf-8",
    )
    start = time.monotonic()
    out = run_shell_command(f'"{sys.executable}" "{script}"', timeout=20, _context=ctx)
    assert time.monotonic() - start < 10
    assert out.startswith("exit code 0") and "parent done" in out


def test_decode_utf8_and_oem_fallback(monkeypatch):
    text = "Tiếng Việt"
    assert shell._decode(text.encode("utf-8")) == text
    monkeypatch.setattr(shell, "_fallback_encodings", lambda: ["cp850"])
    assert shell._decode("café déjà".encode("cp850")) == "café déjà"


def test_child_python_output_is_utf8(ctx, monkeypatch):
    monkeypatch.setenv(UNSAFE_CODE_EXECUTION_ENV, "1")
    out = run_shell_command(f'"{sys.executable}" -c "print(\'Ti\\u1ebfng Vi\\u1ec7t\')"', _context=ctx)
    assert "Tiếng Việt" in out
