"""Literal node executor."""

from typing import List

from agentdev.entity.configs import Node
from agentdev.entity.configs.node.literal import LiteralNodeConfig
from agentdev.entity.messages import Message
from agentdev.runtime.node.executor.base import NodeExecutor


class LiteralNodeExecutor(NodeExecutor):
    """Emit the configured literal message whenever triggered."""

    def execute(self, node: Node, inputs: List[Message]) -> List[Message]:
        if node.node_type != "literal":
            raise ValueError(f"Node {node.id} is not a literal node")

        config = node.as_config(LiteralNodeConfig)
        if config is None:
            raise ValueError(f"Node {node.id} missing literal configuration")

        self._ensure_not_cancelled()
        return [self._build_message(
            role=config.role,
            content=config.content,
            source=node.id,
            preserve_role=True,
        )]

