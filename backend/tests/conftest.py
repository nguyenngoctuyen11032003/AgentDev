"""Shared pytest fixtures for the backend test suite."""

import sys
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
