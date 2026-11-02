"""Workflow runtime: node/edge execution plus the Python SDK entry point.

The SDK symbols are resolved lazily: ``agentdev.runtime.sdk`` imports
``agentdev.validation.check``, which itself bootstraps this package, so an eager
import here would create a circular import.
"""

from typing import TYPE_CHECKING, Any

__all__ = ["WorkflowMetaInfo", "WorkflowRunResult", "run_workflow"]

if TYPE_CHECKING:
    from agentdev.runtime.sdk import WorkflowMetaInfo, WorkflowRunResult, run_workflow


def __getattr__(name: str) -> Any:
    if name in __all__:
        from agentdev.runtime import sdk

        return getattr(sdk, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
