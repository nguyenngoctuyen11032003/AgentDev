"""Register built-in thinking modes."""

from agentdev.entity.configs.node.thinking import ReflectionThinkingConfig, ThinkingConfig
from agentdev.runtime.node.agent.thinking.thinking_manager import ThinkingManagerBase
from agentdev.runtime.node.agent.thinking.self_reflection import SelfReflectionThinkingManager
from agentdev.runtime.node.agent.thinking.registry import (
    register_thinking_mode,
    get_thinking_registration,
)

register_thinking_mode(
    "reflection",
    config_cls=ReflectionThinkingConfig,
    manager_cls=SelfReflectionThinkingManager,
    summary="LLM reflects on its output and refine its output",
)


class ThinkingManagerFactory:
    @staticmethod
    def get_thinking_manager(config: ThinkingConfig) -> ThinkingManagerBase:
        registration = get_thinking_registration(config.type)
        typed_config = config.as_config(registration.config_cls)
        if not typed_config:
            raise ValueError(f"Invalid thinking config for type '{config.type}'")
        return registration.manager_cls(typed_config)
