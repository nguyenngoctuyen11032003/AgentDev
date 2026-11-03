"""Keyless memory: keyword (BM25) retrieval and legacy config handling."""

import copy
import logging

import pytest
import yaml

import agentdev.runtime.node.agent.memory  # noqa: F401  (registers built-in stores)
from agentdev.entity.configs.base import ConfigError
from agentdev.entity.configs.node.memory import (
    EmbeddingConfig,
    FileMemoryConfig,
    MemoryStoreConfig,
    SimpleMemoryConfig,
    strip_legacy_memory_embeddings,
)
from agentdev.runtime.node.agent.memory.builtin_stores import MemoryFactory
from agentdev.runtime.node.agent.memory.keyword_search import rank_by_keywords, tokenize
from agentdev.runtime.node.agent.memory.memory_base import (
    MemoryContentSnapshot,
    MemoryItem,
    MemoryWritePayload,
)
from agentdev.schema_registry import iter_memory_store_schemas

LEGACY_OPENAI_EMBEDDING = {
    "provider": "openai",
    "model": "text-embedding-3-small",
    "api_key": "${AGENTDEV_TEST_UNSET_KEY}",
    "base_url": "${AGENTDEV_TEST_UNSET_URL}",
    "params": {"use_chunking": True},
}


def _store(store_type="simple", **config):
    return MemoryStoreConfig.from_dict(
        {"name": "mem", "type": store_type, "config": config}, path="graph.memory[0]"
    )


def _item(item_id, text):
    return MemoryItem(id=item_id, content_summary=text, metadata={})


def _retrieve(memory, text, top_k=3, threshold=-1.0):
    return memory.retrieve("tester", MemoryContentSnapshot(text=text), top_k, threshold)


# ---------- tokenizer / ranking ----------

def test_tokenize_lowercases_and_splits_unicode():
    assert tokenize("Xin chào, THẾ GIỚI! hello_world 42") == ["xin", "chào", "thế", "giới", "hello_world", "42"]
    assert tokenize("") == []
    assert tokenize(None) == []
    assert tokenize("  ...!!  ") == []


def test_tokenize_cjk_emits_unigrams_and_bigrams():
    tokens = tokenize("记忆模块")
    assert "记" in tokens and "记忆" in tokens and "模块" in tokens


def test_rank_by_keywords_relevant_item_first():
    items = [
        _item("a", "The weather today is sunny and warm"),
        _item("b", "Python memory retrieval uses BM25 keyword scoring"),
        _item("c", "Cooking pasta requires boiling water"),
    ]
    ranked = rank_by_keywords("how does keyword retrieval scoring work", items, text_of=lambda i: i.content_summary, top_k=3)
    assert ranked[0][0].id == "b"
    assert ranked[0][1] == pytest.approx(1.0)
    # Items with no overlapping token are dropped.
    assert [entry[0].id for entry in ranked] == ["b"]


def test_rank_by_keywords_empty_inputs():
    items = [_item("a", "some content")]
    assert rank_by_keywords("", items, text_of=lambda i: i.content_summary, top_k=3) == []
    assert rank_by_keywords("   ", items, text_of=lambda i: i.content_summary, top_k=3) == []
    assert rank_by_keywords("content", [], text_of=lambda i: i.content_summary, top_k=3) == []
    assert rank_by_keywords("content", items, text_of=lambda i: i.content_summary, top_k=0) == []


def test_rank_by_keywords_threshold_filters_weaker_matches():
    items = [
        _item("strong", "alpha beta gamma"),
        _item("weak", "alpha unrelated words here and more filler text"),
    ]
    ranked = rank_by_keywords("alpha beta gamma", items, text_of=lambda i: i.content_summary, top_k=5, similarity_threshold=0.9)
    assert [entry[0].id for entry in ranked] == ["strong"]


# ---------- SimpleMemory without embedding ----------

def test_simple_memory_default_config_needs_no_embedding():
    store = _store("simple")
    cfg = store.as_config(SimpleMemoryConfig)
    assert cfg.embedding is None
    memory = MemoryFactory.create_memory(store)
    assert memory.embedding is None


def test_simple_memory_empty_store_returns_nothing():
    memory = MemoryFactory.create_memory(_store("simple"))
    assert _retrieve(memory, "anything") == []


def test_simple_memory_update_and_keyword_retrieve():
    memory = MemoryFactory.create_memory(_store("simple"))
    for inputs, output in [
        ("Write about volcanoes", "Volcanoes erupt molten lava from the mantle through the crust of the earth."),
        ("Write about the ocean", "The ocean covers most of the planet and is home to whales and coral reefs."),
        ("Write about deserts", "Deserts receive very little rain and have extreme temperature swings."),
    ]:
        memory.update(
            MemoryWritePayload(
                agent_role="writer",
                inputs_text=inputs,
                input_snapshot=None,
                output_snapshot=MemoryContentSnapshot(text=output),
            )
        )
    assert memory.count_memories() == 3
    assert all(item.embedding is None for item in memory.contents)

    results = _retrieve(memory, "tell me about whales in the ocean", top_k=2)
    assert results
    assert "ocean" in results[0].content_summary.lower()
    assert _retrieve(memory, "") == []


def test_simple_memory_unicode_vietnamese(tmp_path):
    path = tmp_path / "mem" / "vi.json"
    memory = MemoryFactory.create_memory(_store("simple", memory_path=str(path)))
    memory.contents = [
        _item("1", "Hà Nội là thủ đô của Việt Nam, nổi tiếng với phở bò"),
        _item("2", "Thành phố Hồ Chí Minh là trung tâm kinh tế lớn nhất"),
        _item("3", "Đà Lạt có khí hậu mát mẻ quanh năm"),
    ]
    results = _retrieve(memory, "Thủ đô HÀ NỘI có món gì ngon?", top_k=3)
    assert results[0].id == "1"

    # Persisted as UTF-8 and reloads correctly (keyword retrieval still works).
    memory.save()
    reloaded = MemoryFactory.create_memory(_store("simple", memory_path=str(path)))
    reloaded.load()
    assert reloaded.count_memories() == 3
    assert _retrieve(reloaded, "khí hậu Đà Lạt")[0].id == "3"


# ---------- FileMemory without embedding ----------

def test_file_memory_keyword_retrieval(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "install.md").write_text("To install the backend run uv sync and start the server.", encoding="utf-8")
    (docs / "memory.md").write_text("Memory stores use BM25 keyword retrieval when no embedding is set.", encoding="utf-8")
    store = _store(
        "file",
        index_path=str(tmp_path / "index" / "idx.json"),
        file_sources=[{"path": str(docs), "file_types": [".md"]}],
    )
    assert store.as_config(FileMemoryConfig).embedding is None
    memory = MemoryFactory.create_memory(store)
    memory.load()
    assert memory.count_memories() == 2
    results = _retrieve(memory, "how does keyword retrieval work", top_k=1)
    assert len(results) == 1
    assert results[0].metadata["file_name"] == "memory.md"


# ---------- Legacy configs ----------

def test_legacy_openai_embedding_block_falls_back_to_keywords(caplog):
    with caplog.at_level(logging.WARNING):
        store = _store("simple", memory_path=None, embedding=copy.deepcopy(LEGACY_OPENAI_EMBEDDING))
    assert store.as_config(SimpleMemoryConfig).embedding is None
    memory = MemoryFactory.create_memory(store)
    assert memory.embedding is None
    memory.contents = [_item("x", "legacy workflows keep working"), _item("y", "unrelated")]
    assert _retrieve(memory, "do legacy workflows work")[0].id == "x"

    file_store = _store(
        "file",
        file_sources=[{"path": "."}],
        embedding=copy.deepcopy(LEGACY_OPENAI_EMBEDDING),
    )
    assert file_store.as_config(FileMemoryConfig).embedding is None


def test_strip_legacy_embeddings_before_placeholder_resolution():
    data = {
        "graph": {
            "memory": [
                {"name": "a", "type": "simple", "config": {"embedding": copy.deepcopy(LEGACY_OPENAI_EMBEDDING)}},
                {"name": "b", "type": "simple", "config": {"embedding": {"provider": "local", "model": "m"}}},
                {"name": "c", "type": "blackboard", "config": {}},
            ]
        }
    }
    strip_legacy_memory_embeddings(data)
    stores = data["graph"]["memory"]
    assert "embedding" not in stores[0]["config"]
    assert stores[1]["config"]["embedding"] == {"provider": "local", "model": "m"}
    assert stores[2]["config"] == {}
    strip_legacy_memory_embeddings({"graph": None})  # tolerant of odd shapes
    strip_legacy_memory_embeddings("not a mapping")


def test_legacy_workflow_with_unset_embedding_placeholders_loads(tmp_path, monkeypatch):
    """A whole workflow with an old openai embedding block loads without API_KEY set."""
    from agentdev.paths import WORKFLOWS_DIR
    from agentdev.validation.check import _stub_missing_env_placeholders, load_config

    monkeypatch.delenv("AGENTDEV_TEST_UNSET_KEY", raising=False)
    monkeypatch.delenv("AGENTDEV_TEST_UNSET_URL", raising=False)
    source = WORKFLOWS_DIR / "demo_simple_memory.yaml"
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    data["graph"]["memory"][0]["config"]["embedding"] = copy.deepcopy(LEGACY_OPENAI_EMBEDDING)
    legacy = tmp_path / "legacy.yaml"
    legacy.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    stubs = _stub_missing_env_placeholders(legacy)
    stubs.pop("AGENTDEV_TEST_UNSET_KEY", None)
    stubs.pop("AGENTDEV_TEST_UNSET_URL", None)
    design = load_config(legacy, vars_override=stubs)
    store = design.graph.memory[0]
    assert store.as_config(SimpleMemoryConfig).embedding is None


def test_mem0_store_is_rejected_with_clear_message():
    with pytest.raises(ConfigError) as excinfo:
        _store("mem0", api_key="x", agent_id="a1")
    message = str(excinfo.value)
    assert "Mem0" in message and "no longer supported" in message
    assert "simple" in message and "file" in message and "blackboard" in message


def test_mem0_not_registered_and_fields_are_keyless():
    assert "mem0" not in iter_memory_store_schemas()
    type_spec = MemoryStoreConfig.field_specs()["type"]
    assert "mem0" not in (type_spec.enum or [])
    for cls in (EmbeddingConfig, SimpleMemoryConfig, FileMemoryConfig):
        specs = cls.field_specs()
        assert "api_key" not in specs and "base_url" not in specs
        for spec in specs.values():
            assert "${" not in str(spec.default)
    assert SimpleMemoryConfig.field_specs()["embedding"].required is False
    assert FileMemoryConfig.field_specs()["embedding"].required is False


def test_embedding_config_rejects_api_providers_when_parsed_directly():
    with pytest.raises(ConfigError):
        EmbeddingConfig.from_dict({"provider": "openai", "model": "x"}, path="e")
    cfg = EmbeddingConfig.from_dict({"model": "all-MiniLM-L6-v2"}, path="e")
    assert cfg.provider == "local"


def test_unavailable_local_embedding_falls_back(monkeypatch):
    """If the optional local model cannot load, the store still works with keywords."""
    from agentdev.runtime.node.agent.memory import embedding as embedding_mod

    def boom(cfg):
        raise ImportError("sentence-transformers is required for LocalEmbedding")

    monkeypatch.setattr(embedding_mod, "LocalEmbedding", boom)
    memory = MemoryFactory.create_memory(_store("simple", embedding={"provider": "local", "model": "m"}))
    assert memory.embedding is None
    memory.contents = [_item("x", "fallback still retrieves by keyword")]
    assert _retrieve(memory, "keyword fallback")[0].id == "x"


def test_no_openai_import_in_memory_code():
    import pathlib

    import agentdev.runtime.node.agent.memory as memory_pkg

    root = pathlib.Path(memory_pkg.__file__).parent
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "import openai" not in text, path.name
        assert "mem0" not in text.lower(), path.name
