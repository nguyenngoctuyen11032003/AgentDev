import os
import subprocess
import sys

import pytest

from agentdev.connections import cli_auth

posix = pytest.mark.skipif(os.name == "nt", reason="process groups are POSIX only")


@posix
def test_kill_never_targets_our_own_process_group(monkeypatch):
    """A child left in our group must be killed alone; killpg on it would kill the server too."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    killed_groups = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: killed_groups.append(pgid))
    try:
        cli_auth.kill_process_tree(proc)
        assert killed_groups == []
        assert proc.wait(5) is not None
    finally:
        if proc.poll() is None:
            proc.kill()


@posix
def test_cli_started_in_own_group_is_killed_as_a_group():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"], **cli_auth.new_process_group_kwargs()
    )
    assert os.getpgid(proc.pid) != os.getpgid(0)
    cli_auth.kill_process_tree(proc)
    assert proc.wait(5) is not None
