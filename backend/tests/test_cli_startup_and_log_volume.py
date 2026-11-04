"""Cheaper CLI start-up (native exe instead of the npm .cmd shim, cached login status) and clipped log output."""

from __future__ import annotations

from unittest.mock import patch

from agentdev.connections import cli_auth
from agentdev.utils.logger import WorkflowLogger, _clip_for_sink


def _make_codex_install(root, nested=True):
    shim = root / "codex.cmd"
    shim.write_text("@echo off\n")
    pkg = "codex-win32-x64"
    base = root / "node_modules" / "@openai"
    if nested:
        base = base / "codex" / "node_modules" / "@openai"
    exe = base / pkg / "vendor" / "x86_64-pc-windows-msvc" / "bin" / "codex.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    return shim, exe


def test_cmd_shim_is_replaced_by_native_codex_exe(tmp_path):
    for nested in (True, False):
        root = tmp_path / ("nested" if nested else "flat")
        root.mkdir()
        shim, exe = _make_codex_install(root, nested)
        with patch("shutil.which", return_value=str(shim)), patch("platform.machine", return_value="AMD64"), \
                patch.object(cli_auth.os, "name", "nt"):
            assert cli_auth.find_cli("codex") == str(exe)


def test_cmd_shim_kept_when_native_exe_is_not_found(tmp_path):
    shim = tmp_path / "claude.cmd"
    shim.write_text("")
    with patch("shutil.which", return_value=str(shim)), patch.object(cli_auth.os, "name", "nt"):
        assert cli_auth.find_cli("claude") == str(shim)
        assert cli_auth.find_cli("codex") == str(shim)


def test_non_shim_path_is_returned_unchanged():
    with patch("shutil.which", return_value="/usr/bin/codex"):
        assert cli_auth.find_cli("codex") == "/usr/bin/codex"


def test_detect_cli_recent_reuses_a_fresh_result_and_logout_clears_it():
    cli_auth._STATUS_CACHE.clear()
    calls = []

    def fake_run(path, args, timeout=cli_auth.DETECT_TIMEOUT):
        calls.append(args)
        return 0, "Logged in", ""

    with patch("shutil.which", return_value="/bin/codex"), patch.object(cli_auth, "_run", fake_run):
        first = cli_auth.detect_cli_recent("openai")
        spawned = len(calls)
        assert first["logged_in"] is True and spawned == 2  # --version + login status
        assert cli_auth.detect_cli_recent("openai")["logged_in"] is True
        assert len(calls) == spawned  # served from the cache
        cli_auth.logout_cli("openai")
        assert "openai" not in cli_auth._STATUS_CACHE
        calls.clear()
        cli_auth.detect_cli_recent("openai")
        assert len(calls) == 2
    cli_auth._STATUS_CACHE.clear()


def test_detect_cli_recent_expires():
    cli_auth._STATUS_CACHE.clear()
    with patch("shutil.which", return_value="/bin/codex"), patch.object(cli_auth, "_run", lambda *a, **k: (0, "ok", "")):
        cli_auth.detect_cli("openai")
        entry = cli_auth._STATUS_CACHE["openai"]
        cli_auth._STATUS_CACHE["openai"] = (entry[0] - 100, entry[1])
        assert cli_auth.detect_cli_recent("openai", max_age=15)["logged_in"] is True
        assert cli_auth._STATUS_CACHE["openai"][0] > entry[0] - 100  # refreshed
    cli_auth._STATUS_CACHE.clear()


def test_clip_for_sink_shortens_long_strings_only():
    data = {"a": "x" * 5000, "b": ["y" * 10, "z" * 4000], "n": 3, "c": {"d": "q" * 400}}
    out = _clip_for_sink(data, 1000)
    assert len(out["a"]) < 1100 and out["a"].endswith("[+4000 chars]")
    assert out["b"][0] == "y" * 10 and out["b"][1].endswith("[+3000 chars]")
    assert out["n"] == 3 and out["c"]["d"] == "q" * 400
    assert len(data["a"]) == 5000  # input untouched


def test_workflow_logger_keeps_full_text_in_memory_but_clips_the_log_sink():
    sink = []

    class Sink:
        def info(self, message, **details):
            sink.append(details)

    wl = WorkflowLogger("clip_test", use_structured_logging=False, log_to_console=False)
    wl.use_structured_logging, wl.structured_logger = True, Sink()
    big = "p" * 20000
    wl.record_model_call("n1", "m", input_data=big, output="ok")
    assert wl.logs[-1].details["input_data"] == big
    assert len(sink[-1]["input_data"]) < 2000
