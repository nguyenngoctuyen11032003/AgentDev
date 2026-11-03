"""Shared pytest fixtures for the backend test suite."""

import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

# Module attributes holding the absolute runtime output locations from
# ``agentdev.paths``. They are redirected into each test's ``tmp_path`` so the
# suite never writes into the real repository ``WareHouse/`` or ``logs/``.
_WAREHOUSE_ATTRS = (
    ("agentdev.runtime.sdk", "OUTPUT_ROOT"),
    ("agentdev.api.routes.execute_sync", "OUTPUT_ROOT"),
    ("agentdev.api.settings", "WARE_HOUSE_DIR"),
    ("agentdev.api.routes.sessions", "WARE_HOUSE_DIR"),
    ("agentdev.api.services.workflow_run_service", "WARE_HOUSE_DIR"),
    ("agentdev.api.services.batch_run_service", "WARE_HOUSE_DIR"),
    ("agentdev.api.services.attachment_service", "WAREHOUSE_DIR"),
    ("agentdev.entity.graph_config", "WAREHOUSE_DIR"),
)
_LOGS_ATTRS = (("agentdev.utils.structured_logger", "LOGS_DIR"),)
_SESSIONS_ATTRS = (("agentdev.api.services.session_history", "SESSIONS_DIR"),)


def _patch_loaded(monkeypatch, targets, value) -> None:
    for module_name, attr in targets:
        module = sys.modules.get(module_name)
        # Skip modules that are not loaded or were replaced by test stubs.
        if isinstance(module, ModuleType) and hasattr(module, attr):
            monkeypatch.setattr(module, attr, value)


@pytest.fixture(autouse=True)
def _isolate_runtime_dirs(tmp_path, monkeypatch):
    _patch_loaded(monkeypatch, _WAREHOUSE_ATTRS, tmp_path / "WareHouse")
    _patch_loaded(monkeypatch, _LOGS_ATTRS, tmp_path / "logs")
    _patch_loaded(monkeypatch, _SESSIONS_ATTRS, tmp_path / "sessions")
    monkeypatch.setenv("VUEGRAPHS_DB_PATH", str(tmp_path / "data" / "vuegraphs.db"))
    yield


# --- Filesystem links -------------------------------------------------------
# Several security tests plant links that try to escape a session workspace.
# On Windows, creating a symbolic link requires SeCreateSymbolicLinkPrivilege
# (Developer Mode or an elevated shell); without it ``symlink_to`` raises
# ``OSError`` with ``winerror == 1314``. Directory links fall back to an NTFS
# junction, which needs no privilege and is an equivalent escape vector, so the
# boundary checks are still exercised. File links have no unprivileged
# equivalent and the test is skipped in exactly that situation.

_ERROR_PRIVILEGE_NOT_HELD = 1314


def _is_symlink_privilege_error(exc: OSError) -> bool:
    return sys.platform == "win32" and getattr(exc, "winerror", None) == _ERROR_PRIVILEGE_NOT_HELD


def _create_junction(link, target) -> None:
    import _winapi

    link = Path(link)
    target = Path(target)
    if not target.is_absolute():
        target = link.parent / target
    target = Path(os.path.abspath(target))
    if target == Path(os.path.abspath(link)):
        # A junction cannot point at itself; pointing at its own parent is an
        # equivalent directory cycle.
        target = target.parent
    if target.exists():
        _winapi.CreateJunction(str(target), str(link))
        return
    # Dangling target: junctions require an existing target at creation time.
    target.mkdir(parents=True)
    try:
        _winapi.CreateJunction(str(target), str(link))
    finally:
        target.rmdir()


def make_link(link, target, *, directory: bool = False) -> None:
    """Create ``link`` -> ``target``, falling back to a junction on Windows."""
    link = Path(link)
    try:
        link.symlink_to(target, target_is_directory=directory)
        return
    except OSError as exc:
        if not _is_symlink_privilege_error(exc):
            raise
    if not directory:
        pytest.skip(
            "Creating file symlinks on Windows requires Developer Mode or admin "
            "(WinError 1314) and file links have no unprivileged equivalent"
        )
    _create_junction(link, target)


def is_link(path) -> bool:
    """True for symbolic links and Windows junctions."""
    path = os.fspath(path)
    return os.path.islink(path) or bool(getattr(os.path, "isjunction", lambda _p: False)(path))


@pytest.fixture
def link():
    """Factory fixture: ``link(path, target, directory=False)``."""
    return make_link
