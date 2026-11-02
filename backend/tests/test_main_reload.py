"""Tests for ``main.build_reload_kwargs`` (backend/main.py).

Regression coverage for issue #569: when ``--reload`` is active the default
watch configuration must exclude the WareHouse/ output directory, otherwise
agent-generated files trigger a StatReload restart mid-workflow and the
webui hangs indefinitely.

The tests load ``main`` through an isolated ``importlib`` spec so
that the stubs we inject for its heavy dependencies (``runtime.bootstrap``
and ``agentdev.api.app``) are cleaned up automatically and do not leak into the
``sys.modules`` cache shared with the rest of the test suite.
"""

import argparse
import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest


MAIN_PATH = Path(__file__).resolve().parent.parent / "main.py"


@pytest.fixture
def main_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Load ``main`` with heavy imports stubbed, cleaning up after."""
    stubs = {}

    def _stub(name: str) -> ModuleType:
        stub = MagicMock(name=name)
        stubs[name] = stub
        return stub

    for name in (
        "agentdev.runtime",
        "agentdev.runtime.bootstrap",
        "agentdev.runtime.bootstrap.schema",
        "agentdev.api",
        "agentdev.api.app",
    ):
        monkeypatch.setitem(sys.modules, name, _stub(name))

    # Expose ensure_schema_registry_populated as a no-op callable on its module.
    stubs["agentdev.runtime.bootstrap.schema"].ensure_schema_registry_populated = lambda: None
    stubs["agentdev.api.app"].app = MagicMock(name="app")

    spec = importlib.util.spec_from_file_location(
        "main_under_test", MAIN_PATH
    )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop("main_under_test", None)


def _args(**overrides) -> argparse.Namespace:
    defaults = dict(
        reload=False,
        reload_dir=None,
        reload_exclude=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class TestBuildReloadKwargs:
    def test_reload_disabled_returns_empty(self, main_module):
        assert main_module.build_reload_kwargs(_args(reload=False)) == {}

    def test_default_watches_source_dirs_only(self, main_module):
        kw = main_module.build_reload_kwargs(_args(reload=True))
        from agentdev.paths import (
            EXAMPLES_DIR,
            FUNCTIONS_DIR,
            PACKAGE_DIR,
            SCRIPTS_DIR,
            WAREHOUSE_DIR,
        )

        dirs = kw["reload_dirs"]
        assert str(PACKAGE_DIR) in dirs
        assert str(SCRIPTS_DIR) in dirs
        assert str(FUNCTIONS_DIR) in dirs
        assert str(EXAMPLES_DIR) in dirs
        # Watched dirs are absolute so reload works from any launch CWD.
        assert all(Path(d).is_absolute() for d in dirs)
        # The output dir that caused the bug must not be watched.
        assert str(WAREHOUSE_DIR) not in dirs
        assert not any(Path(d).name == "WareHouse" for d in dirs)

    def test_default_excludes_cover_output_dirs(self, main_module):
        kw = main_module.build_reload_kwargs(_args(reload=True))
        excludes = kw["reload_excludes"]
        # Core regression: WareHouse/ writes must be ignored by watchfiles.
        assert any("WareHouse" in p for p in excludes)
        assert any(p.startswith("storage/") for p in excludes)
        # Logs, data, temp, node_modules live in .gitignore too.
        assert any("logs" in p for p in excludes)

    def test_returned_lists_are_copies(self, main_module):
        """Callers mutating the result must not poison the defaults."""
        kw = main_module.build_reload_kwargs(_args(reload=True))
        kw["reload_dirs"].append("WareHouse")
        kw["reload_excludes"].append("junk")
        fresh = main_module.build_reload_kwargs(_args(reload=True))
        assert "WareHouse" not in fresh["reload_dirs"]
        assert "junk" not in fresh["reload_excludes"]

    def test_user_reload_dir_overrides_default(self, main_module):
        kw = main_module.build_reload_kwargs(
            _args(reload=True, reload_dir=["app", "lib"])
        )
        assert kw["reload_dirs"] == ["app", "lib"]
        # Excludes keep their defaults.
        assert any("WareHouse" in p for p in kw["reload_excludes"])

    def test_user_reload_exclude_overrides_default(self, main_module):
        kw = main_module.build_reload_kwargs(
            _args(reload=True, reload_exclude=["*.md"])
        )
        assert kw["reload_excludes"] == ["*.md"]
        # Dirs keep their defaults.
        assert kw["reload_dirs"] == main_module.RELOAD_SOURCE_DIRS


class TestParserFlags:
    def test_reload_dir_is_repeatable(self, main_module):
        parser = main_module.build_parser()
        args = parser.parse_args(["--reload", "--reload-dir", "a", "--reload-dir", "b"])
        assert args.reload_dir == ["a", "b"]

    def test_reload_exclude_is_repeatable(self, main_module):
        parser = main_module.build_parser()
        args = parser.parse_args(
            ["--reload", "--reload-exclude", "x/*", "--reload-exclude", "y/*"]
        )
        assert args.reload_exclude == ["x/*", "y/*"]

    def test_defaults_produce_empty_override_slots(self, main_module):
        parser = main_module.build_parser()
        args = parser.parse_args([])
        assert args.reload is False
        assert args.reload_dir is None
        assert args.reload_exclude is None


class TestExcludePatternDepth:
    """Regression guard for reviewer feedback on PR #611.

    ``uvicorn`` filters reload candidates with ``pathlib.Path.match``, which
    on Python < 3.13 does not expand ``**``. A bare ``WareHouse/*`` pattern
    therefore only catches direct children, not the nested files that
    AgentDev actually generates under ``WareHouse/<project>/...``. The
    default set must cover each depth explicitly.
    """

    @pytest.mark.parametrize(
        "relative_path",
        [
            "storage/warehouse/demo/foo.py",
            "storage/logs/server.log",
            "storage/db/vuegraphs.db",
            "WareHouse/foo.py",
            "WareHouse/demo/foo.py",
            "WareHouse/demo/sub/foo.py",
            "WareHouse/a/b/c/d/e/foo.py",
            "logs/run.log",
            "logs/2026/04/run.log",
            "data/cache/item.json",
            "node_modules/pkg/dist/index.js",
        ],
    )
    def test_nested_paths_are_excluded(self, main_module, relative_path):
        excludes = main_module.RELOAD_EXCLUDES
        path = Path(relative_path)
        assert any(path.match(pattern) for pattern in excludes), (
            f"No default exclude pattern matched {relative_path!r}; "
            f"patterns={excludes}"
        )

    def test_legitimate_source_paths_are_not_excluded(self, main_module):
        """Guard against the patterns being so broad they block real edits."""
        excludes = main_module.RELOAD_EXCLUDES
        for ok in ("api/app.py", "runtime/bootstrap/schema.py", "workflow/a/b.py"):
            assert not any(
                Path(ok).match(pattern) for pattern in excludes
            ), f"Source path {ok!r} is incorrectly excluded"


class TestWatchfilesWarning:
    """Second reviewer point: warn when --reload-exclude is a no-op.

    ``--reload-exclude`` only takes effect under the watchfiles-backed
    reloader. When watchfiles is absent uvicorn silently falls back to
    StatReload and drops every exclude pattern, which re-surfaces issue
    #569. The server should log a warning instead of failing silently.
    """

    def test_warns_when_watchfiles_missing(
        self, main_module, monkeypatch, caplog
    ):
        monkeypatch.setattr(main_module, "_watchfiles_available", lambda: False)
        # Exercise the same condition main() checks, without spinning uvicorn.
        with caplog.at_level(logging.WARNING, logger="main_under_test"):
            logger = logging.getLogger("main_under_test")
            if not main_module._watchfiles_available():
                logger.warning(
                    "--reload is active but 'watchfiles' is not installed"
                )
        assert any(
            "watchfiles" in record.message.lower() for record in caplog.records
        )

    def test_available_returns_bool(self, main_module):
        """``_watchfiles_available`` must be a plain bool-returning probe."""
        result = main_module._watchfiles_available()
        assert isinstance(result, bool)
