"""Compact repo map (ADR 0003): smaller than the old tree on a big repo, cached, flag-controlled."""

from pathlib import Path

import pytest

from agentdev.api.services import repo_map
from agentdev.api.services.attachment_service import render_project_tree


def _entries(root: Path):
    return [(p, p.relative_to(root).as_posix()) for p in sorted(root.rglob("*"))
            if p.is_file() and ".git" not in p.relative_to(root).parts and "__pycache__" not in p.parts]


def _size(lines):
    return sum(len(x) + 1 for x in lines)


@pytest.fixture(scope="module")
def bench_repo(tmp_path_factory):
    from scripts.bench_repo_gen import build_repo

    root = tmp_path_factory.mktemp("bench") / "repo"
    build_repo(root, seed=1234)
    return root


def test_repo_map_is_smaller_than_legacy_tree_on_bench_repo(bench_repo, capsys):
    entries = _entries(bench_repo)
    legacy = render_project_tree([rel for _p, rel in entries])
    mapped = repo_map.build_repo_map(entries, use_cache=False)
    print(f"BENCH files={len(entries)} legacy_chars={_size(legacy)} legacy_lines={len(legacy)} "
          f"map_chars={_size(mapped)} map_lines={len(mapped)}")
    assert _size(mapped) < _size(legacy)
    assert _size(mapped) <= repo_map.MAX_MAP_CHARS
    text = "\n".join(mapped)
    assert "pkg/ (" in text and "clamp" in text  # structure and a real symbol are visible


def test_repo_map_extracts_symbols(tmp_path):
    (tmp_path / "a.py").write_text("def alpha():\n    pass\n\nclass Beta:\n    def inner(self): ...\n_hidden = 1\n")
    (tmp_path / "b.ts").write_text("export function gamma() {}\nexport const delta = 1\nclass Eps {}\n")
    assert repo_map.extract_symbols(tmp_path / "a.py") == ["alpha", "Beta"]
    assert repo_map.extract_symbols(tmp_path / "b.ts") == ["gamma", "delta", "Eps"]


def test_repo_map_cached_until_a_file_changes(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("def one(): ...\n")
    entries = _entries(tmp_path)
    repo_map.clear_cache()
    calls = []
    real = repo_map.extract_symbols
    monkeypatch.setattr(repo_map, "extract_symbols", lambda *a, **k: calls.append(1) or real(*a, **k))
    first = repo_map.build_repo_map(entries)
    assert repo_map.build_repo_map(entries) == first and len(calls) == 1
    (tmp_path / "a.py").write_text("def two(): ...\n" + "# pad\n" * 3)
    second = repo_map.build_repo_map(entries)
    assert len(calls) == 2 and any("two" in line for line in second)


def test_overview_never_larger_than_legacy_and_flag_off(bench_repo, tmp_path, monkeypatch):
    entries = _entries(bench_repo)
    legacy = render_project_tree([rel for _p, rel in entries])
    heading, lines = repo_map.render_overview_tree(entries, legacy)
    assert heading.startswith("Repo map") and _size(lines) < _size(legacy)
    monkeypatch.setenv("AGENTDEV_REPO_MAP", "0")
    assert repo_map.render_overview_tree(entries, legacy) == ("Folder tree", legacy)
    monkeypatch.delenv("AGENTDEV_REPO_MAP")
    (tmp_path / "x.py").write_text("def x(): ...\n")
    small = _entries(tmp_path)
    small_legacy = render_project_tree([rel for _p, rel in small])
    assert repo_map.render_overview_tree(small, small_legacy)[0] == "Folder tree"  # tiny repo: exact tree kept


def test_size_cap_holds_with_many_symbol_files(tmp_path):
    for i in range(60):
        (tmp_path / f"m{i}.py").write_text("\n".join(f"def function_with_long_name_{i}_{j}(): ..." for j in range(30)))
    mapped = repo_map.build_repo_map(_entries(tmp_path), use_cache=False)
    assert _size(mapped) <= repo_map.MAX_MAP_CHARS + 400  # tree is budgeted separately from the symbol lines
