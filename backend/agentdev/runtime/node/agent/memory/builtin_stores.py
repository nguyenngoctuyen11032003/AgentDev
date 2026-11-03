"""Register built-in memory stores."""

from agentdev.entity.configs.node.memory import (
    BlackboardMemoryConfig,
    FileMemoryConfig,
    SimpleMemoryConfig,
    MemoryStoreConfig,
)
from agentdev.runtime.node.agent.memory.blackboard_memory import BlackboardMemory
from agentdev.runtime.node.agent.memory.file_memory import FileMemory
from agentdev.runtime.node.agent.memory.memory_base import MemoryBase
from agentdev.runtime.node.agent.memory.simple_memory import SimpleMemory
from agentdev.runtime.node.agent.memory.registry import register_memory_store, get_memory_store_registration

register_memory_store(
    "simple",
    config_cls=SimpleMemoryConfig,
    factory=lambda store: SimpleMemory(store),
    summary="Lightweight store of past outputs with keyword retrieval (no API key); persists when memory_path is set",
)

register_memory_store(
    "file",
    config_cls=FileMemoryConfig,
    factory=lambda store: FileMemory(store),
    summary="Indexes local files on disk; keyword search by default (no API key)",
)

register_memory_store(
    "blackboard",
    config_cls=BlackboardMemoryConfig,
    factory=lambda store: BlackboardMemory(store),
    summary="Shared blackboard memory allowing multiple nodes to read/write",
)


class MemoryFactory:
    @staticmethod
    def create_memory(store: MemoryStoreConfig) -> MemoryBase:
        registration = get_memory_store_registration(store.type)
        return registration.factory(store)
