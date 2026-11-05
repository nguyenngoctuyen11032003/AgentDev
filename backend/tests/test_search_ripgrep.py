"""search_in_files: ripgrep fast path (ADR 0002) must match the Python path and never silently skip big files."""

import shutil
import subprocess
from pathlib import Path

import pytest

from agentdev.utils.attachments import AttachmentStore
from functions.function_calling import file as ft

HAS_RG = shutil.which("rg") is not None


def _ctx(root: Path) -> dict:
    store = AttachmentStore(root.parent / (root.name + "_store"))
    return {"python_workspace_root": str(root), "graph_directory": str(root), "attachment_store": store}


def _make(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("alpha\nNeedle one\nbeta\nneedle two needle three\n", encoding="utf-8")
    (root / "src" / "b.md").write_text("nothing\n", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "x.js").write_text("needle in deps\n", encoding="utf-8")
    (root / "logo.png").write_bytes(b"\x89PNG\0needle\0")


def _key(result):
    return [(m["file"], m["line"], m["column"], m["line_text"], m["before"], m["after"]) for m in result["matches"]]


def _python_only(monkeypatch):
    monkeypatch.setattr(ft.shutil, "which", lambda name, *a, **k: None)


def test_python_path_when_rg_missing(tmp_path, monkeypatch):
    _make(tmp_path)
    _python_only(monkeypatch)
    result = ft.search_in_files("needle", _context=_ctx(tmp_path))
    assert result["engine"] == "python"
    assert [m["line"] for m in result["matches"]] == [2, 4, 4]


def test_rg_failure_falls_back_to_python(tmp_path, monkeypatch):
    _make(tmp_path)
    monkeypatch.setattr(ft.shutil, "which", lambda name, *a, **k: "rg")

    def boom(*a, **k):
        raise OSError("no rg")

    monkeypatch.setattr(ft.subprocess, "run", boom)
    result = ft.search_in_files("needle", _context=_ctx(tmp_path))
    assert result["engine"] == "python" and len(result["matches"]) == 3


def test_flag_off_forces_python(tmp_path, monkeypatch):
    _make(tmp_path)
    monkeypatch.setenv("AGENTDEV_SEARCH_RG", "0")
    assert ft.search_in_files("needle", _context=_ctx(tmp_path))["engine"] == "python"


@pytest.mark.skipif(not HAS_RG, reason="ripgrep not installed")
def test_rg_matches_python_result_format(tmp_path, monkeypatch):
    _make(tmp_path)
    fast = ft.search_in_files("needle", _context=_ctx(tmp_path))
    assert fast["engine"] == "ripgrep"
    _python_only(monkeypatch)
    slow = ft.search_in_files("needle", _context=_ctx(tmp_path))
    assert _key(fast) == _key(slow) and fast["limited"] == slow["limited"]


@pytest.mark.skipif(not HAS_RG, reason="ripgrep not installed")
def test_rg_respects_max_results_and_case_and_literal(tmp_path):
    _make(tmp_path)
    ctx = _ctx(tmp_path)
    limited = ft.search_in_files("needle", max_results=2, _context=ctx)
    assert limited["limited"] is True and len(limited["matches"]) == 2
    cs = ft.search_in_files("Needle", case_sensitive=True, _context=ctx)
    assert [m["line"] for m in cs["matches"]] == [2]
    lit = ft.search_in_files("needle (", use_regex=False, _context=ctx)
    assert lit["matches"] == []


@pytest.mark.skipif(not HAS_RG, reason="ripgrep not installed")
def test_rg_respects_gitignore_and_skips_dependency_dirs(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=False)
    _make(tmp_path)
    (tmp_path / "src" / "secret.py").write_text("needle secret\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("secret.py\n", encoding="utf-8")
    files = {m["file"] for m in ft.search_in_files("needle", _context=_ctx(tmp_path))["matches"]}
    assert files == {"src/a.py"}


@pytest.mark.skipif(not HAS_RG, reason="ripgrep not installed")
def test_rg_does_not_skip_files_over_2mb(tmp_path):
    big = tmp_path / "big.txt"
    big.write_text("filler line\n" * 250_000 + "the needle is here\n", encoding="utf-8")
    assert big.stat().st_size > ft._MAX_SEARCH_FILE_BYTES
    result = ft.search_in_files("needle", _context=_ctx(tmp_path))
    assert result["engine"] == "ripgrep"
    assert [(m["file"], m["line"]) for m in result["matches"]] == [("big.txt", 250_001)]
    assert "skipped_binary_or_large_files" not in result


@pytest.mark.skipif(not HAS_RG, reason="ripgrep not installed")
def test_rg_globs_and_excludes(tmp_path):
    _make(tmp_path)
    ctx = _ctx(tmp_path)
    only_md = ft.search_in_files("nothing|needle", globs=["*.md"], _context=ctx)
    assert {m["file"] for m in only_md["matches"]} == {"src/b.md"}
    no_py = ft.search_in_files("needle|nothing", exclude_globs=["*.py"], _context=ctx)
    assert {m["file"] for m in no_py["matches"]} == {"src/b.md"}
