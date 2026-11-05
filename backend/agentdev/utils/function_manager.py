"""Unified function management."""
import importlib.util
import inspect
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from agentdev.paths import FUNCTIONS_DIR, PROJECT_ROOT

_MODULE_PREFIX = "_dynamic_functions"
_FUNCTION_CALLING_ENV = "MAC_FUNCTIONS_DIR"
_EDGE_FUNCTION_ENV = "MAC_EDGE_FUNCTIONS_DIR"
_EDGE_PROCESSOR_FUNCTION_ENV = "MAC_EDGE_PROCESSOR_FUNCTIONS_DIR"
_DEFAULT_FUNCTIONS_ROOT = FUNCTIONS_DIR
_DEFAULT_FUNCTION_CALLING_DIR = _DEFAULT_FUNCTIONS_ROOT / "function_calling"
_DEFAULT_EDGE_FUNCTION_DIR = _DEFAULT_FUNCTIONS_ROOT / "edge"
_DEFAULT_EDGE_PROCESSOR_DIR = _DEFAULT_FUNCTIONS_ROOT / "edge_processor"


def is_true_function_name(name: Any) -> bool:
    """Whether an edge-condition function name means "always true" (any case, surrounding whitespace ignored).
    Shared by the runtime and the workflow lint so both read ``"True"``/``" true"`` the same way."""
    return isinstance(name, str) and name.strip().lower() == "true"


def _resolve_dir(default: Path, env_var: str | None = None) -> Path:
    """Resolve a directory path with optional environment override."""
    override = os.environ.get(env_var) if env_var else None
    if override:
        return Path(override).expanduser()
    if default.is_absolute():
        return default
    return PROJECT_ROOT / default


FUNCTION_CALLING_DIR = _resolve_dir(_DEFAULT_FUNCTION_CALLING_DIR, _FUNCTION_CALLING_ENV).resolve()
EDGE_FUNCTION_DIR = _resolve_dir(_DEFAULT_EDGE_FUNCTION_DIR, _EDGE_FUNCTION_ENV).resolve()
EDGE_PROCESSOR_FUNCTION_DIR = _resolve_dir(_DEFAULT_EDGE_PROCESSOR_DIR, _EDGE_PROCESSOR_FUNCTION_ENV).resolve()


class FunctionManager:
    """Unified function manager for loading and managing functions across the project."""

    def __init__(self, functions_dir: str | Path = FUNCTIONS_DIR) -> None:
        self.functions_dir = Path(functions_dir)
        self.functions: Dict[str, Callable] = {}
        self._loaded = False
        self._fingerprint: tuple = ()

    def load_functions(self) -> None:
        """Load all Python functions from functions directory."""
        if self._loaded:
            return

        if not self.functions_dir.exists():
            raise ValueError(f"Functions directory does not exist: {self.functions_dir}")

        for file in self.functions_dir.rglob("*.py"):
            if file.name.startswith("_") or file.name == "__init__.py":
                continue
            if "__pycache__" in file.parts:
                continue
                
            module_name = self._build_module_name(file)
            try:
                # Import module dynamically
                spec = importlib.util.spec_from_file_location(module_name, file)
                if spec is None or spec.loader is None:
                    continue
                    
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                current_file = file.resolve()
                # Get all functions defined in the module
                for name, obj in inspect.getmembers(module, inspect.isfunction):
                    if name.startswith("_"):
                        continue
                    # Only register functions defined in the current module/file
                    if getattr(obj, "__module__", None) != module.__name__:
                        code = getattr(obj, "__code__", None)
                        source_path = Path(code.co_filename).resolve() if code else None
                        if source_path != current_file:
                            continue
                    self.functions[name] = obj
            except Exception as e:
                print(f"Error loading module {module_name}: {e}")

        self._fingerprint = self._dir_fingerprint()
        self._loaded = True

    def _dir_fingerprint(self) -> tuple:
        """Names and mtimes of the function files: changes when a file is added, removed or edited."""
        try:
            return tuple(sorted(
                (f.as_posix(), f.stat().st_mtime_ns)
                for f in self.functions_dir.rglob("*.py")
                if "__pycache__" not in f.parts
            ))
        except OSError:
            return ()

    def _build_module_name(self, filepath: Path) -> str:
        """Create a unique module name for a function file."""
        relative = filepath.relative_to(self.functions_dir)
        parts = "_".join(relative.with_suffix("").parts) or "module"
        unique_suffix = f"{abs(hash(filepath.as_posix())) & 0xFFFFFFFF:X}"
        return f"{_MODULE_PREFIX}.{parts}_{unique_suffix}"

    def get_function(self, name: str) -> Optional[Callable]:
        """Get a function by name."""
        if not self._loaded:
            self.load_functions()
        func = self.functions.get(name)
        if func is None and self._dir_fingerprint() != self._fingerprint:
            # A function file was added or edited since the last scan: pick it up without a restart.
            self.reload_functions()
            func = self.functions.get(name)
        return func

    def has_function(self, name: str) -> bool:
        """Check if a function exists."""
        if not self._loaded:
            self.load_functions()
        return name in self.functions

    def call_function(self, name: str, *args, **kwargs) -> Any:
        """Call a function by name with given arguments."""
        func = self.get_function(name)
        if func is None:
            raise ValueError(f"Function {name} not found")
        return func(*args, **kwargs)

    def list_functions(self) -> Dict[str, Callable]:
        """List all available functions."""
        if not self._loaded:
            self.load_functions()
        return self.functions.copy()

    def reload_functions(self) -> None:
        """Reload all functions from the functions directory."""
        self.functions.clear()
        self._loaded = False
        self.load_functions()


# Global function manager registry keyed by directory
_function_managers: Dict[Path, FunctionManager] = {}


def get_function_manager(functions_dir: str | Path) -> FunctionManager:
    """Get or create the global function manager instance for a directory."""
    directory = Path(functions_dir).resolve()

    manager = _function_managers.get(directory)
    if manager is None:
        manager = FunctionManager(directory)
        _function_managers[directory] = manager
    return manager
