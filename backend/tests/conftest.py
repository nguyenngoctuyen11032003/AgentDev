"""Shared pytest fixtures for the backend test suite."""

import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import ModuleType

import pytest

# The suite works on a private copy of the workflow folder (the shipped workflows plus the demo
# fixtures in tests/fixtures/), so it never writes into workspace/workflows and parallel runs do
# not step on each other. Set before anything imports ``agentdev.paths``.
_REAL_WORKFLOWS = Path(__file__).resolve().parents[2] / "workspace" / "workflows"
_TEST_WORKFLOWS = Path(tempfile.mkdtemp(prefix="agentdev_test_workflows_"))
for _source in [*_REAL_WORKFLOWS.glob("*.yaml"), *(Path(__file__).parent / "fixtures").glob("*.yaml")]:
    shutil.copyfile(_source, _TEST_WORKFLOWS / _source.name)
os.environ["AGENTDEV_WORKFLOWS_DIR"] = str(_TEST_WORKFLOWS)

# Never read the developer's ``.env`` into ``os.environ``: a clean checkout has none,
# so tests must not depend on it. Marking the loader as done keeps it a no-op.
import agentdev.utils.env_loader as _env_loader

_env_loader._DOTENV_LOADED = True

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
_MEMORY_ATTRS = (("agentdev.workflow.graph", "MEMORY_DIR"),)


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
    _patch_loaded(monkeypatch, _MEMORY_ATTRS, tmp_path / "memory")
    monkeypatch.setenv("VUEGRAPHS_DB_PATH", str(tmp_path / "data" / "vuegraphs.db"))
    # Code that resolves ``agentdev.paths.STORAGE_DIR`` at call time (e.g. Lab jobs).
    import agentdev.paths as paths_module

    monkeypatch.setattr(paths_module, "STORAGE_DIR", tmp_path / "storage")
    yield


@pytest.fixture(autouse=True)
def _isolate_connection_store(tmp_path, monkeypatch):
    """Point the connection store at an empty per-test file.

    ``get_store()`` caches one ``ConnectionStore`` in ``store._store``; replacing that
    cache (restored by monkeypatch afterwards) means no test ever sees or writes the
    developer's real ``storage/connections.json``.
    """
    from agentdev.connections import store as store_module

    path = tmp_path / "storage" / "connections.json"
    monkeypatch.setattr(store_module, "CONNECTIONS_FILE", path)
    monkeypatch.setattr(store_module, "_store", store_module.ConnectionStore(path))
    yield


@pytest.fixture
def signed_in_account(monkeypatch):
    """A fake signed-in CLI account in the isolated store, used by autobind.

    The account's model list is not probed (that would read the real CLI's local state),
    so autobind falls back to the static vendor catalog.
    """
    from agentdev.connections import autobind
    from agentdev.connections.store import Connection, get_store

    monkeypatch.setattr(autobind, "_default_model", lambda _conn: None)
    store = get_store()
    conn = Connection(id="claude-test", vendor="anthropic", label="Test", auth_type="cli")
    with store._lock:
        connections = store._load()
        connections[conn.id] = conn
        store._save(connections)
    return conn


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




def pytest_unconfigure(config):
    shutil.rmtree(_TEST_WORKFLOWS, ignore_errors=True)
