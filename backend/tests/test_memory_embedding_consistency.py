"""Tests for memory embedding dimension consistency."""
from unittest.mock import MagicMock
from agentdev.runtime.node.agent.memory.memory_base import MemoryContentSnapshot, MemoryItem
from agentdev.runtime.node.agent.memory.simple_memory import SimpleMemory

def _make_store(memory_path=None):
    """Build a minimal MemoryStoreConfig mock for SimpleMemory."""
    simple_cfg = MagicMock()
    simple_cfg.memory_path = memory_path
    simple_cfg.embedding = None  # We'll set embedding manually

    store = MagicMock()
    store.name = "test_store"
    store.as_config.return_value = simple_cfg
    return store


def _make_embedding(dim: int):
    """Create a mock EmbeddingBase that produces vectors of the given dimension."""
    emb = MagicMock()
    emb.get_embedding.return_value = [0.1] * dim
    return emb


def _make_memory_item(item_id: str, dim: int):
    """Create a MemoryItem with an embedding of the specified dimension."""
    return MemoryItem(
        id=item_id,
        content_summary=f"content for {item_id}",
        metadata={},
        embedding=[float(i) for i in range(dim)],
    )


class TestSimpleMemoryRetrieveMixedDimensions:

    def test_mixed_dimensions_does_not_crash(self):
        """Retrieve with mixed-dimensional embeddings MUST not raise."""
        store = _make_store()
        memory = SimpleMemory(store)
        memory.embedding = _make_embedding(dim=768)

        # 3 items with correct dim, 2 with wrong dim
        memory.contents = [
            _make_memory_item("ok_1", 768),
            _make_memory_item("bad_1", 1536),
            _make_memory_item("ok_2", 768),
            _make_memory_item("bad_2", 256),
            _make_memory_item("ok_3", 768),
        ]

        query = MemoryContentSnapshot(text="test query")
        # Should NOT raise ValueError / numpy error
        results = memory.retrieve(
            agent_role="tester",
            query=query,
            top_k=5,
            similarity_threshold=-1.0,
        )
        # Only the 3 correct-dimension items should be candidates
        assert len(results) <= 3

    def test_all_same_dimension_returns_results(self):
        """When all embeddings share the correct dimension, all are candidates."""
        store = _make_store()
        memory = SimpleMemory(store)
        memory.embedding = _make_embedding(dim=768)

        memory.contents = [
            _make_memory_item("a", 768),
            _make_memory_item("b", 768),
        ]

        query = MemoryContentSnapshot(text="test query")
        results = memory.retrieve(
            agent_role="tester",
            query=query,
            top_k=5,
            similarity_threshold=-1.0,
        )
        assert len(results) == 2

    def test_all_wrong_dimension_returns_empty(self):
        """When every stored embedding has a wrong dimension, return empty."""
        store = _make_store()
        memory = SimpleMemory(store)
        memory.embedding = _make_embedding(dim=768)

        memory.contents = [
            _make_memory_item("x", 1536),
            _make_memory_item("y", 1536),
        ]

        query = MemoryContentSnapshot(text="test query")
        results = memory.retrieve(
            agent_role="tester",
            query=query,
            top_k=5,
            similarity_threshold=-1.0,
        )
        assert results == []
