"""Regression: a same-size edit made in the same timestamp tick as the index ("racy git") must still show up in a
turn's changes. Copying the index with shutil.copyfile gave the copy a newer mtime, which made git trust the
stale stat cache and skip the edit (the routes roundtrip test failed under load)."""

import os
import subprocess
from pathlib import Path

from agentdev.api.services import git_checkpoint as gc


def _git(root: Path, *args: str) -> str:
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, env={**os.environ, **env},
                          check=True).stdout


def test_same_size_edit_in_the_index_tick_is_seen(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTDEV_GIT_CHECKPOINT", raising=False)
    root = (tmp_path / "proj")
    root.mkdir()
    _git(root, "init", "-q")
    (root / "a.txt").write_bytes(b"one\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    root = root.resolve()
    stamp = (root / "a.txt").stat().st_mtime_ns
    index = root / ".git" / "index"
    os.utime(index, ns=(stamp, stamp))  # the index was written in the same tick as a.txt: entries are racy

    assert gc.begin_turn_at(root, "k")["status"] == "ok"
    (root / "a.txt").write_bytes(b"two\n")  # same size...
    os.utime(root / "a.txt", ns=(stamp, stamp))  # ...and the same mtime as the cached stat
    os.utime(index, ns=(stamp, stamp))
    gc.end_turn_at(root, "k")
    data = gc.changes_at(root, "k")
    assert data["status"] == "ok" and [f["path"] for f in data["files"]] == ["a.txt"]
