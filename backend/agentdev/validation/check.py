"""Utilities for loading, validating design_0.4.0 workflows."""

from pathlib import Path
from typing import Any, Dict, Optional

from agentdev.runtime.bootstrap.schema import ensure_schema_registry_populated
from agentdev.validation.check_yaml import validate_design
from agentdev.validation.check_workflow import check_workflow_structure
from agentdev.entity.config_loader import prepare_design_mapping
from agentdev.entity.configs import DesignConfig, ConfigError
from agentdev.schema_registry import iter_node_schemas
from agentdev.utils.io_utils import read_yaml


ensure_schema_registry_populated()


class DesignError(RuntimeError):
    """Raised when a workflow design cannot be loaded or validated."""



def _allowed_node_types() -> set[str]:
    names = set(iter_node_schemas().keys())
    if not names:
        raise DesignError("No node types registered; cannot validate workflow")
    return names


def _ensure_supported(graph: Dict[str, Any]) -> None:
    """Ensure the MVP constraints are satisfied for the provided graph."""
    for node in graph.get("nodes", []) or []:
        nid = node.get("id")
        ntype = node.get("type")
        allowed = _allowed_node_types()
        if ntype not in allowed:
            raise DesignError(
                f"Unsupported node type '{ntype}' for node '{nid}'. Only {allowed} nodes are supported."
            )
        if ntype == "agent":
            agent_cfg = node.get("config") or {}
            if not isinstance(agent_cfg, dict):
                raise DesignError(f"Agent node '{nid}' config must be an object")
            for legacy_key in ["memory"]:
                if legacy_key in agent_cfg:
                    raise DesignError(
                        f"'{legacy_key}' is deprecated. Use the new graph-level memory stores for node '{nid}'."
                    )


def load_config(
    config_path: Path,
    *,
    fn_module: Optional[str] = None,
    set_defaults: bool = True,
    vars_override: Optional[Dict[str, Any]] = None,
) -> DesignConfig:
    """Load, validate, and sanity-check a workflow file."""

    try:
        raw_data = read_yaml(config_path)
    except FileNotFoundError as exc:
        raise DesignError(f"Design file not found: {config_path}") from exc

    if not isinstance(raw_data, dict):
        raise DesignError("YAML root must be a mapping")

    if vars_override:
        merged_vars = dict(raw_data.get("vars") or {})
        merged_vars.update(vars_override)
        raw_data = dict(raw_data)
        raw_data["vars"] = merged_vars

    data = prepare_design_mapping(raw_data, source=str(config_path))

    schema_errors = validate_design(data, set_defaults=set_defaults, fn_module_ref=fn_module)
    if schema_errors:
        formatted = "\n".join(f"- {err}" for err in schema_errors)
        raise DesignError(f"Design validation failed for '{config_path}':\n{formatted}")

    try:
        design = DesignConfig.from_dict(data, path="root")
    except ConfigError as exc:
        raise DesignError(f"Design parsing failed for '{config_path}': {exc}") from exc

    logic_errors = check_workflow_structure(data)
    if logic_errors:
        formatted = "\n".join(f"- {err}" for err in logic_errors)
        raise DesignError(f"Workflow logical issues detected for '{config_path}':\n{formatted}")
    else:
        print("Workflow OK.")

    graph = data.get("graph") or {}
    _ensure_supported(graph)

    return design


def _stub_missing_env_placeholders(config_path: Path) -> Dict[str, Any]:
    """Return dummy values for ``${VAR}`` placeholders that only exist at runtime.

    API keys, model names, etc. come from the environment when a workflow runs;
    static validation (CI has no ``.env``) must not fail just because they are unset.
    """
    import os
    import re

    from agentdev.utils.env_loader import load_dotenv_file

    load_dotenv_file()
    raw = read_yaml(config_path)
    declared = set((raw.get("vars") or {}).keys()) if isinstance(raw, dict) else set()
    names = set(re.findall(r"\$\{([A-Za-z0-9_]+)\}", config_path.read_text(encoding="utf-8")))
    return {name: f"<{name}>" for name in sorted(names - declared) if name not in os.environ}


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry: ``python -m agentdev.validation.check --path <workflow.yaml>``.

    Exits 0 when the workflow loads cleanly, 1 otherwise (used by
    ``scripts/validate_all_yamls.py`` and CI).
    """
    import argparse

    parser = argparse.ArgumentParser(description="Validate a workflow YAML file.")
    parser.add_argument("--path", required=True, type=Path, help="Workflow YAML file to validate")
    args = parser.parse_args(argv)

    if not args.path.is_file():
        print(f"Design file not found: {args.path}")
        return 1
    try:
        load_config(args.path, vars_override=_stub_missing_env_placeholders(args.path))
    except Exception as exc:  # report any load/validation failure, not only DesignError
        print(f"{type(exc).__name__}: {exc}")
        return 1
    return 0


def check_config(yaml_content: Any) -> str:
    if not isinstance(yaml_content, dict):
        return "YAML root must be a mapping"

    # Skip placeholder resolution during save - users may configure env vars at runtime
    # Use yaml_content directly instead of prepare_design_mapping()
    schema_errors = validate_design(yaml_content)
    if schema_errors:
        formatted = "\n".join(f"- {err}" for err in schema_errors)
        return formatted

    logic_errors = check_workflow_structure(yaml_content)
    if logic_errors:
        formatted = "\n".join(f"- {err}" for err in logic_errors)
        return formatted

    graph = yaml_content.get("graph") or {}
    try:
        _ensure_supported(graph)
    except Exception as e:
        return str(e)

    return ""

if __name__ == "__main__":
    raise SystemExit(main())
