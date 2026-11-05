"""FunctionEdgeManager centralizes function-based edge conditions."""

from typing import Callable, Optional

from agentdev.entity.configs.edge.edge_condition import FunctionEdgeConditionConfig
from agentdev.utils.structured_logger import get_server_logger
from .base import ConditionFactoryContext
from .base import EdgeConditionManager
from agentdev.utils.function_manager import FunctionManager, is_true_function_name
from agentdev.utils.human_prompt import AUTO_SKIP_PAID
from ...node.executor import ExecutionContext


class FunctionEdgeConditionManager(EdgeConditionManager[FunctionEdgeConditionConfig]):
    def __init__(self, config: FunctionEdgeConditionConfig, ctx: ConditionFactoryContext, execution_context: ExecutionContext) -> None:
        super().__init__(config, ctx, execution_context)
        self._name = config.name or "true"
        self.label = self._name or "true"
        self.metadata = {"function": self._name}
        self._evaluator = self._build_evaluator()

    def _build_evaluator(self) -> Callable[[str], bool]:
        if is_true_function_name(self._name):
            return lambda _: True

        function_obj = self._resolve_function(self._name, self.ctx.function_manager)
        if function_obj is None:
            logger = get_server_logger()
            logger.warning(f"Edge condition function '{self._name}' not found; the edge will not fire")
            self.metadata = {"function": self._name, "missing": True}

            def missing(_: str) -> bool:
                # Fail-closed: raising routes through the shared error path, which
                # skips the edge and emits EDGE_CONDITION_ERROR. A typo must never
                # open a (possibly paid) branch.
                raise LookupError(f"Condition function '{self._name}' not found")

            return missing

        def evaluator(data: str) -> bool:
            return bool(function_obj(data))

        return evaluator

    def process(
        self,
        edge_link,
        source_result,
        from_node,
        log_manager,
    ) -> None:
        evaluator = self._evaluator
        if is_true_function_name(self._name) and _is_paid_gate(from_node):
            # An unconditional edge cannot tell approval from refusal: when a paid gate was skipped
            # automatically (Lab), the refusal must not flow into the next (paid) step. The run stops there.
            evaluator = lambda data: AUTO_SKIP_PAID not in (data or "")  # noqa: E731
        self._process_with_condition(
            evaluator,
            label=self.label,
            metadata=self.metadata,
            edge_link=edge_link,
            source_result=source_result,
            from_node=from_node,
            log_manager=log_manager,
        )

    def _resolve_function(
        self, name: str, function_manager: Optional["FunctionManager"]
    ) -> Optional[Callable[[str], bool]]:
        if not function_manager:
            return None
        return function_manager.get_function(name)


def _is_paid_gate(node) -> bool:
    if getattr(node, "node_type", None) != "human":
        return False
    try:
        from agentdev.entity.configs.node.human import HumanConfig

        cfg = node.as_config(HumanConfig)
    except Exception:
        return False
    return bool(getattr(cfg, "paid", False))
