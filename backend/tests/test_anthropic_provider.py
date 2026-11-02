"""Tests for the native Anthropic Claude provider (all network calls are faked)."""

import base64
import copy
import json
from types import SimpleNamespace
from typing import Any, Dict, List

import httpx2
import pytest

import anthropic
from anthropic.types import Message as SDKMessage
from anthropic.types import TextBlock, ThinkingBlock, ToolUseBlock, Usage

from agentdev.entity.messages import (
    AttachmentRef,
    FunctionCallOutputEvent,
    Message,
    MessageBlock,
    MessageBlockType,
    MessageRole,
    ToolCallPayload,
)
from agentdev.entity.tool_spec import ToolSpec
from agentdev.runtime.node.agent.providers.anthropic_provider import (
    DEFAULT_MAX_TOKENS,
    FALLBACK_BETA_DEFAULT,
    AnthropicAssistantTurn,
    AnthropicProvider,
)


# ----------------------------------------------------------------------------
# Fakes
# ----------------------------------------------------------------------------


class _FakeStream:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._response


class _FakeMessagesAPI:
    def __init__(self, owner, kind):
        self._owner = owner
        self._kind = kind

    def _next(self, method, request):
        # Deep-copy so later timeline mutation can't change what we recorded.
        self._owner.calls.append({"api": self._kind, "method": method, "request": copy.deepcopy(request)})
        return self._owner.responses.pop(0)

    def stream(self, **request):
        return _FakeStream(self._next("stream", request))

    def create(self, **request):
        return self._next("create", request)


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: List[Dict[str, Any]] = []
        self.messages = _FakeMessagesAPI(self, "messages")
        self.beta = SimpleNamespace(messages=_FakeMessagesAPI(self, "beta"))

    @property
    def last(self) -> Dict[str, Any]:
        return self.calls[-1]["request"]


class FakeTracker:
    workflow_id = "wf-1"

    def __init__(self):
        self.records = []

    def record_usage(self, node_id, model_name, usage, provider=None):
        self.records.append((node_id, model_name, usage, provider))


def make_config(name="claude-opus-5-5", params=None, base_url=None, **extra):
    return SimpleNamespace(
        provider="anthropic",
        base_url=base_url,
        api_key="test-key",
        name=name,
        params=params or {},
        **extra,
    )


def make_provider(name="claude-opus-5-5", params=None, base_url=None, **extra):
    return AnthropicProvider(make_config(name=name, params=params, base_url=base_url, **extra))


def sdk_response(content, stop_reason="end_turn", usage=None, model="claude-opus-5-5", **kwargs):
    return SDKMessage(
        id="msg_1",
        type="message",
        role="assistant",
        model=model,
        content=content,
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=usage or Usage(input_tokens=10, output_tokens=5),
        **kwargs,
    )


def text_response(text="hello", **kwargs):
    return sdk_response([TextBlock(type="text", text=text)], **kwargs)


def tool_response(*calls, thinking=True, stop_reason="tool_use"):
    content = []
    if thinking:
        content.append(ThinkingBlock(type="thinking", thinking="plan", signature="sig-abc"))
    for call_id, name, args in calls:
        content.append(ToolUseBlock(type="tool_use", id=call_id, name=name, input=args))
    return sdk_response(content, stop_reason=stop_reason)


def base_timeline(user="Hi", system="Be brief."):
    timeline: List[Any] = []
    if system:
        timeline.append(Message(role=MessageRole.SYSTEM, content=system))
    timeline.append(Message(role=MessageRole.USER, content=user))
    return timeline


def run(provider, client, timeline, tool_specs=None, **kwargs):
    return provider.call_model(client, conversation=[], timeline=timeline, tool_specs=tool_specs, **kwargs)


def data_uri(mime: str, payload: bytes) -> str:
    return f"data:{mime};base64," + base64.b64encode(payload).decode("ascii")


def attachment_block(block_type, mime, payload, name):
    return MessageBlock(
        type=block_type,
        attachment=AttachmentRef(attachment_id=name, mime_type=mime, name=name, data_uri=data_uri(mime, payload)),
    )


def all_blocks(request):
    return [block for msg in request["messages"] for block in msg["content"]]


def assert_no_empty_text(request):
    for block in all_blocks(request):
        if isinstance(block, dict) and block.get("type") == "text":
            assert block["text"].strip(), request


# ----------------------------------------------------------------------------
# Plain requests / defaults
# ----------------------------------------------------------------------------


def test_plain_text_request_defaults():
    provider = make_provider()
    client = FakeClient(text_response("Hello there"))
    response = run(provider, client, base_timeline())

    req = client.last
    assert client.calls[0]["method"] == "stream"
    assert req["model"] == "claude-opus-5-5"
    assert req["system"] == "Be brief."
    assert req["messages"][0]["role"] == "user"
    assert req["messages"] == [{"role": "user", "content": [{"type": "text", "text": "Hi"}]}]
    assert req["max_tokens"] == DEFAULT_MAX_TOKENS
    assert req["thinking"] == {"type": "adaptive"}
    assert req["cache_control"] == {"type": "ephemeral"}
    assert response.message.role is MessageRole.ASSISTANT
    assert response.message.text_content() == "Hello there"
    assert response.message.tool_calls == []
    assert response.message.metadata["provider"] == "anthropic"


def test_sampling_params_dropped_by_default_and_kept_when_allowed():
    client = FakeClient(text_response(), text_response())
    run(make_provider(params={"temperature": 0.2, "top_p": 0.9, "top_k": 5}), client, base_timeline())
    assert not {"temperature", "top_p", "top_k"} & set(client.last)

    run(
        make_provider(params={"temperature": 0.2, "top_k": 5, "allow_sampling_params": True}),
        client,
        base_timeline(),
    )
    assert client.last["temperature"] == 0.2
    assert client.last["top_k"] == 5
    assert "allow_sampling_params" not in client.last


def test_effort_goes_to_output_config_and_unknown_params_ignored():
    client = FakeClient(text_response(), text_response())
    run(make_provider(params={"effort": "high", "frequency_penalty": 1, "seed": 3}), client, base_timeline())
    assert client.last["output_config"] == {"effort": "high"}
    assert "effort" not in client.last and "seed" not in client.last

    run(make_provider(params={"reasoning": {"effort": "low"}, "max_tokens": 1000}), client, base_timeline())
    assert client.last["output_config"] == {"effort": "low"}
    assert client.last["max_tokens"] == 1000


def test_thinking_false_omits_thinking_and_caching_can_be_disabled():
    client = FakeClient(text_response())
    run(make_provider(params={"thinking": False, "prompt_caching": False}), client, base_timeline())
    assert "thinking" not in client.last
    assert "cache_control" not in client.last


def test_thinking_display_is_applied():
    client = FakeClient(text_response())
    run(make_provider(params={"thinking_display": "summarized"}), client, base_timeline())
    assert client.last["thinking"] == {"type": "adaptive", "display": "summarized"}


def test_older_model_gets_no_default_thinking():
    client = FakeClient(text_response(model="claude-haiku-4-5"))
    run(make_provider(name="claude-haiku-4-5"), client, base_timeline())
    assert "thinking" not in client.last
    assert "fallbacks" not in client.last
    assert client.calls[0]["api"] == "messages"


def test_invalid_thinking_value_raises():
    with pytest.raises(ValueError):
        run(make_provider(params={"thinking": 1234}), FakeClient(text_response()), base_timeline())


def test_stream_false_uses_create():
    client = FakeClient(text_response())
    run(make_provider(params={"stream": False}), client, base_timeline())
    assert client.calls[0]["method"] == "create"
    assert "stream" not in client.last


def test_empty_user_input_gets_placeholder_and_no_empty_blocks():
    client = FakeClient(text_response())
    run(make_provider(), client, [Message(role=MessageRole.USER, content="   ")])
    assert client.last["messages"][0]["role"] == "user"
    assert_no_empty_text(client.last)
    assert "system" not in client.last


# ----------------------------------------------------------------------------
# Fallbacks / beta routing
# ----------------------------------------------------------------------------


def test_fallbacks_default_on_official_endpoint(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    client = FakeClient(text_response())
    run(make_provider(name="claude-opus-5-5"), client, base_timeline())
    assert client.calls[0]["api"] == "beta"
    assert client.last["fallbacks"] == "default"
    assert client.last["betas"] == [FALLBACK_BETA_DEFAULT]
    assert FALLBACK_BETA_DEFAULT == "server-side-fallback-2026-07-01"


def test_fallbacks_skipped_for_custom_base_url(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    client = FakeClient(text_response())
    run(make_provider(base_url="https://my-proxy.example.com"), client, base_timeline())
    assert client.calls[0]["api"] == "messages"
    assert "fallbacks" not in client.last and "betas" not in client.last


def test_fallbacks_can_be_disabled(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    client = FakeClient(text_response())
    run(make_provider(params={"fallbacks": False}), client, base_timeline())
    assert client.calls[0]["api"] == "messages"
    assert "fallbacks" not in client.last


def test_explicit_fallback_list_uses_list_beta(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    client = FakeClient(text_response())
    run(make_provider(params={"fallbacks": [{"model": "claude-opus-4-8"}]}), client, base_timeline())
    assert client.last["betas"] == ["server-side-fallback-2026-06-01"]


def test_beta_only_passthrough_routes_to_beta_api():
    client = FakeClient(text_response(model="claude-haiku-4-5"))
    params = {"context_management": {"edits": [{"type": "clear_tool_uses_20250919"}]}}
    run(make_provider(name="claude-haiku-4-5", params=params), client, base_timeline())
    assert client.calls[0]["api"] == "beta"
    assert client.last["context_management"] == params["context_management"]


def test_other_provider_base_url_is_ignored():
    provider = make_provider(base_url="https://api.openai.com/v1")
    assert provider._resolved_base_url() is None


# ----------------------------------------------------------------------------
# Tool loop
# ----------------------------------------------------------------------------


def _specs():
    return [
        ToolSpec(
            name="mcp.server.search",
            description="Search things",
            parameters={"type": "object", "properties": {"q": {"type": "string"}}},
        ),
        ToolSpec(name="get_time", description="", parameters={}),
    ]


def test_full_tool_loop_round_trips_assistant_turn(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    provider = make_provider(params={"fallbacks": False})
    first = tool_response(("toolu_01", "mcp_server_search", {"q": "cats"}))
    client = FakeClient(first, text_response("done"))
    timeline = base_timeline()

    response = run(provider, client, timeline, tool_specs=_specs())

    tools = client.calls[0]["request"]["tools"]
    assert [t["name"] for t in tools] == ["mcp_server_search", "get_time"]
    assert tools[1]["input_schema"] == {"type": "object", "properties": {}}
    assert "description" not in tools[1]

    assert response.has_tool_calls()
    call = response.message.tool_calls[0]
    assert call.id == "toolu_01"
    assert call.function_name == "mcp.server.search"  # original, unsanitized
    assert json.loads(call.arguments) == {"q": "cats"}
    assert response.message.metadata["thinking"] == "plan"

    assert isinstance(timeline[-1], AnthropicAssistantTurn)
    assert timeline[-1].content == list(first.content)

    timeline.append(FunctionCallOutputEvent(call_id="toolu_01", function_name=call.function_name, output_text="3 cats"))
    final = run(provider, client, timeline, tool_specs=_specs())
    assert final.message.text_content() == "done"

    msgs = client.last["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assistant_content = msgs[1]["content"]
    assert assistant_content == list(first.content)  # verbatim, SDK objects untouched
    assert assistant_content[0].type == "thinking" and assistant_content[0].signature == "sig-abc"
    result = msgs[2]["content"][0]
    assert result == {
        "type": "tool_result",
        "tool_use_id": "toolu_01",
        "content": [{"type": "text", "text": "3 cats"}],
    }


def test_error_output_marks_is_error():
    provider = make_provider(params={"fallbacks": False})
    client = FakeClient(tool_response(("toolu_e", "get_time", {})), text_response())
    timeline = base_timeline()
    run(provider, client, timeline, tool_specs=_specs())
    timeline.append(FunctionCallOutputEvent(call_id="toolu_e", function_name="get_time", output_text="error: boom"))
    run(provider, client, timeline, tool_specs=_specs())
    result = client.last["messages"][-1]["content"][0]
    assert result["type"] == "tool_result" and result["is_error"] is True


def test_parallel_tool_results_land_in_one_user_message():
    provider = make_provider(params={"fallbacks": False})
    client = FakeClient(
        tool_response(("toolu_a", "get_time", {}), ("toolu_b", "mcp_server_search", {"q": "x"})),
        text_response(),
    )
    timeline = base_timeline()
    response = run(provider, client, timeline, tool_specs=_specs())
    assert [c.id for c in response.message.tool_calls] == ["toolu_a", "toolu_b"]
    timeline.append(FunctionCallOutputEvent(call_id="toolu_a", function_name="get_time", output_text="noon"))
    timeline.append(
        FunctionCallOutputEvent(
            call_id="toolu_b",
            function_name="mcp.server.search",
            output_blocks=[MessageBlock(MessageBlockType.TEXT, text="found")],
        )
    )
    run(provider, client, timeline, tool_specs=_specs())
    msgs = client.last["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert [b["tool_use_id"] for b in msgs[2]["content"]] == ["toolu_a", "toolu_b"]


def test_skill_system_message_between_results_is_hoisted():
    provider = make_provider(params={"fallbacks": False})
    client = FakeClient(tool_response(("toolu_s", "get_time", {})), text_response())
    timeline = base_timeline()
    run(provider, client, timeline, tool_specs=_specs())
    timeline.append(FunctionCallOutputEvent(call_id="toolu_s", function_name="get_time", output_text="{}"))
    timeline.append(Message(role=MessageRole.SYSTEM, content="Skill instructions"))
    run(provider, client, timeline, tool_specs=_specs())
    assert client.last["system"] == "Be brief.\n\nSkill instructions"
    assert client.last["messages"][-1]["content"][0]["type"] == "tool_result"


def test_tool_choice_coercion():
    # Forced tool use is only valid on models that accept it, with thinking off.
    provider = make_provider(name="claude-opus-5", params={"thinking": False, "tool_choice": "required"})
    client = FakeClient(text_response())
    run(provider, client, base_timeline(), tool_specs=_specs())
    assert client.last["tool_choice"] == {"type": "any"}

    provider = make_provider(
        name="claude-opus-5",
        params={"thinking": False, "tool_choice": {"type": "function", "function": {"name": "mcp.server.search"}}},
    )
    client = FakeClient(text_response())
    run(provider, client, base_timeline(), tool_specs=_specs())
    assert client.last["tool_choice"] == {"type": "tool", "name": "mcp_server_search"}


@pytest.mark.parametrize(
    "name, params",
    [
        ("claude-opus-5-5", {"tool_choice": "required"}),  # model rejects forced tool use
        ("claude-sonnet-5-5", {"tool_choice": {"type": "tool", "name": "mcp.server.search"}}),
        ("claude-opus-5", {"tool_choice": "required"}),  # thinking on by default
    ],
)
def test_forced_tool_choice_downgraded_to_auto(name, params):
    provider = make_provider(name=name, params={"fallbacks": False, **params})
    client = FakeClient(text_response())
    run(provider, client, base_timeline(), tool_specs=_specs())
    assert client.last["tool_choice"] == {"type": "auto"}


def test_colliding_tool_names_get_unique_api_names():
    specs = [ToolSpec(name="a.b", description="dotted"), ToolSpec(name="a_b", description="underscored")]
    provider = make_provider(params={"fallbacks": False})
    client = FakeClient(tool_response(("toolu_1", "a_b_2", {}), thinking=False))
    response = run(provider, client, base_timeline(), tool_specs=specs)
    names = [tool["name"] for tool in client.last["tools"]]
    assert names == ["a_b", "a_b_2"]
    assert response.message.tool_calls[0].function_name == "a_b"


def test_failed_call_leaves_timeline_untouched_for_retry():
    class Boom(Exception):
        pass

    paused = sdk_response([TextBlock(type="text", text="partial")], stop_reason="pause_turn")
    provider = make_provider(name="claude-haiku-4-5")
    client = FakeClient(paused, text_response())
    original_next = client.messages._next

    def _next(method, request):
        result = original_next(method, request)
        if len(client.calls) == 2:  # the continuation after pause_turn fails
            raise Boom("network")
        return result

    client.messages._next = _next
    timeline = base_timeline()
    before = list(timeline)
    with pytest.raises(Boom):
        run(provider, client, timeline)
    assert timeline == before


# ----------------------------------------------------------------------------
# History from other providers
# ----------------------------------------------------------------------------


def test_history_tool_calls_convert_to_tool_use_and_result():
    provider = make_provider(params={"fallbacks": False})
    client = FakeClient(text_response())
    timeline = base_timeline() + [
        Message(
            role=MessageRole.ASSISTANT,
            content="Let me check.",
            tool_calls=[ToolCallPayload(id="call:1/x", function_name="mcp.server.search", arguments='{"q": "a"}')],
        ),
        Message(role=MessageRole.TOOL, content="result A", tool_call_id="call:1/x"),
        Message(role=MessageRole.USER, content="thanks"),
    ]
    run(provider, client, timeline)
    msgs = client.last["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assistant = msgs[1]["content"]
    assert assistant[0] == {"type": "text", "text": "Let me check."}
    assert assistant[1] == {"type": "tool_use", "id": "call_1_x", "name": "mcp_server_search", "input": {"q": "a"}}
    user = msgs[2]["content"]
    assert user[0] == {"type": "tool_result", "tool_use_id": "call_1_x", "content": [{"type": "text", "text": "result A"}]}
    assert user[1] == {"type": "text", "text": "thanks"}


def test_history_tool_error_message_marks_is_error():
    provider = make_provider(params={"fallbacks": False})
    client = FakeClient(text_response())
    timeline = base_timeline() + [
        Message(role=MessageRole.ASSISTANT, content="", tool_calls=[ToolCallPayload(id="c1", function_name="t", arguments="")]),
        Message(role=MessageRole.TOOL, content="Tool t error: kaput", tool_call_id="c1"),
    ]
    run(provider, client, timeline)
    msgs = client.last["messages"]
    assert msgs[1]["content"] == [{"type": "tool_use", "id": "c1", "name": "t", "input": {}}]
    assert msgs[2]["content"][0]["is_error"] is True
    assert_no_empty_text(client.last)


def test_orphan_tool_result_becomes_text():
    provider = make_provider(params={"fallbacks": False})
    client = FakeClient(text_response())
    timeline = base_timeline() + [Message(role=MessageRole.TOOL, content="stray output", tool_call_id="ghost")]
    run(provider, client, timeline)
    blocks = all_blocks(client.last)
    assert not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks)
    assert any(b.get("type") == "text" and "stray output" in b["text"] for b in blocks)


def test_tool_use_without_result_gets_placeholder_result():
    """E.g. a loop-limited assistant message with tool_calls handed to the next node."""
    provider = make_provider(params={"fallbacks": False})
    client = FakeClient(text_response())
    timeline = base_timeline() + [
        Message(role=MessageRole.ASSISTANT, content="calling", tool_calls=[ToolCallPayload(id="c9", function_name="t", arguments="{}")]),
        Message(role=MessageRole.USER, content="summarize please"),
    ]
    run(provider, client, timeline)
    user = client.last["messages"][2]["content"]
    assert user[0]["type"] == "tool_result" and user[0]["tool_use_id"] == "c9" and user[0]["is_error"] is True
    assert user[1] == {"type": "text", "text": "summarize please"}


def test_tool_result_is_moved_before_text_in_same_user_message():
    provider = make_provider(params={"fallbacks": False})
    client = FakeClient(text_response())
    timeline = base_timeline() + [
        Message(role=MessageRole.ASSISTANT, content="", tool_calls=[ToolCallPayload(id="c1", function_name="t", arguments="{}")]),
        Message(role=MessageRole.TOOL, content="stray", tool_call_id="nope"),  # orphan -> text, comes first
        Message(role=MessageRole.TOOL, content="real", tool_call_id="c1"),
    ]
    run(provider, client, timeline)
    user = client.last["messages"][2]["content"]
    assert user[0]["type"] == "tool_result" and user[0]["tool_use_id"] == "c1"
    assert user[1]["type"] == "text"


def test_trailing_assistant_gets_user_continuation():
    provider = make_provider(params={"fallbacks": False})
    client = FakeClient(text_response())
    timeline = base_timeline() + [Message(role=MessageRole.ASSISTANT, content="partial answer")]
    run(provider, client, timeline)
    assert client.last["messages"][-1]["role"] == "user"


# ----------------------------------------------------------------------------
# Attachments
# ----------------------------------------------------------------------------


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _user_with(*blocks):
    return [Message(role=MessageRole.USER, content=list(blocks))]


def _content_of_first_user(client):
    return client.last["messages"][0]["content"]


def test_png_image_becomes_image_block():
    client = FakeClient(text_response())
    blocks = (MessageBlock.text_block("look"), attachment_block(MessageBlockType.IMAGE, "image/png", PNG, "a.png"))
    run(make_provider(), client, _user_with(*blocks))
    content = _content_of_first_user(client)
    assert content[0] == {"type": "text", "text": "look"}
    assert content[1]["type"] == "image"
    assert content[1]["source"] == {"type": "base64", "media_type": "image/png", "data": base64.b64encode(PNG).decode()}


def test_pdf_becomes_document_block():
    client = FakeClient(text_response())
    run(make_provider(), client, _user_with(attachment_block(MessageBlockType.FILE, "application/pdf", b"%PDF-1.4", "r.pdf")))
    block = _content_of_first_user(client)[0]
    assert block["type"] == "document"
    assert block["source"]["media_type"] == "application/pdf"
    assert block["title"] == "r.pdf"


def test_csv_is_inlined_as_text():
    client = FakeClient(text_response())
    run(make_provider(), client, _user_with(attachment_block(MessageBlockType.FILE, "text/csv", b"a,b\n1,2", "d.csv")))
    block = _content_of_first_user(client)[0]
    assert block["type"] == "text"
    assert "[Attachment: d.csv]" in block["text"] and "a,b\n1,2" in block["text"]


def test_audio_is_described_as_text():
    client = FakeClient(text_response())
    run(make_provider(), client, _user_with(attachment_block(MessageBlockType.AUDIO, "audio/mpeg", b"ID3", "s.mp3")))
    block = _content_of_first_user(client)[0]
    assert block["type"] == "text" and "s.mp3" in block["text"] and "not supported" in block["text"]


def test_oversize_image_becomes_note(monkeypatch):
    import agentdev.runtime.node.agent.providers.anthropic_provider as mod

    monkeypatch.setattr(mod, "MAX_IMAGE_BYTES", 8)
    client = FakeClient(text_response())
    run(make_provider(), client, _user_with(attachment_block(MessageBlockType.IMAGE, "image/png", PNG, "big.png")))
    block = _content_of_first_user(client)[0]
    assert block["type"] == "text" and "big.png" in block["text"]


def test_empty_text_blocks_are_never_sent():
    client = FakeClient(text_response())
    run(
        make_provider(),
        client,
        [
            Message(role=MessageRole.USER, content=[MessageBlock.text_block(""), MessageBlock.text_block("  \n")]),
            Message(role=MessageRole.ASSISTANT, content=""),
            Message(role=MessageRole.USER, content=[MessageBlock.text_block("real"), MessageBlock.text_block(" ")]),
        ],
    )
    assert_no_empty_text(client.last)
    assert client.last["messages"][0]["role"] == "user"
    assert any(b.get("text") == "real" for b in all_blocks(client.last))


def test_tool_output_image_goes_into_tool_result():
    provider = make_provider(params={"fallbacks": False})
    client = FakeClient(tool_response(("toolu_i", "get_time", {})), text_response())
    timeline = base_timeline()
    run(provider, client, timeline, tool_specs=_specs())
    timeline.append(
        FunctionCallOutputEvent(
            call_id="toolu_i",
            function_name="get_time",
            output_blocks=[attachment_block(MessageBlockType.IMAGE, "image/png", PNG, "shot.png")],
        )
    )
    run(provider, client, timeline, tool_specs=_specs())
    result = client.last["messages"][-1]["content"][0]
    assert result["type"] == "tool_result"
    assert result["content"][0]["type"] == "image"


# ----------------------------------------------------------------------------
# Stop reasons
# ----------------------------------------------------------------------------


def test_refusal_has_no_tool_calls_and_explains():
    response_obj = sdk_response(
        [ToolUseBlock(type="tool_use", id="toolu_r", name="get_time", input={})],
        stop_reason="refusal",
    )
    response_obj.stop_details = SimpleNamespace(category="cyber")
    client = FakeClient(response_obj)
    response = run(make_provider(), client, base_timeline(), tool_specs=_specs())
    assert response.message.tool_calls == []
    assert "declined" in response.message.text_content()
    assert "cyber" in response.message.text_content()
    assert response.message.metadata["refusal_category"] == "cyber"


def test_max_tokens_drops_tool_calls():
    client = FakeClient(tool_response(("toolu_m", "get_time", {}), stop_reason="max_tokens"))
    response = run(make_provider(), client, base_timeline(), tool_specs=_specs())
    assert response.message.tool_calls == []
    assert "max_tokens" in response.message.text_content()


def test_pause_turn_is_continued_without_extra_user_message():
    paused_content = [
        TextBlock(type="text", text="searching"),
        {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "input": {"query": "x"}},
    ]
    paused = SimpleNamespace(
        content=paused_content,
        stop_reason="pause_turn",
        usage=Usage(input_tokens=1, output_tokens=1),
        model="claude-opus-5-5",
    )
    client = FakeClient(paused, text_response("final"))
    timeline = base_timeline()
    response = run(make_provider(params={"fallbacks": False}), client, timeline)

    assert len(client.calls) == 2
    first, second = client.calls[0]["request"], client.calls[1]["request"]
    assert first["messages"][-1]["role"] == "user"
    # Second request = same request with the paused assistant turn appended as the last message.
    assert second["messages"][:-1] == first["messages"]
    assert second["messages"][-1] == {"role": "assistant", "content": paused_content}
    assert response.message.text_content() == "final"
    assert sum(isinstance(item, AnthropicAssistantTurn) for item in timeline) == 2


# ----------------------------------------------------------------------------
# Token usage
# ----------------------------------------------------------------------------


def test_token_usage_includes_cache_tokens_and_is_tracked():
    tracker = FakeTracker()
    provider = make_provider(token_tracker=tracker, node_id="node-7")
    usage = Usage(input_tokens=100, output_tokens=40, cache_creation_input_tokens=20, cache_read_input_tokens=300)
    client = FakeClient(text_response(usage=usage))
    run(provider, client, base_timeline())

    assert len(tracker.records) == 1
    node_id, model_name, recorded, provider_name = tracker.records[0]
    assert node_id == "node-7" and model_name == "claude-opus-5-5" and provider_name == "anthropic"
    assert recorded.input_tokens == 420
    assert recorded.output_tokens == 40
    assert recorded.total_tokens == 460
    assert recorded.metadata["cache_read_input_tokens"] == 300
    assert recorded.provider == "anthropic" and recorded.workflow_id == "wf-1"


def test_extract_token_usage_without_usage():
    assert make_provider().extract_token_usage(SimpleNamespace()).input_tokens == 0


# ----------------------------------------------------------------------------
# Real SDK serialization (mock HTTP transport, no network)
# ----------------------------------------------------------------------------


def _sse(response_json: Dict[str, Any]) -> bytes:
    msg = dict(response_json)
    content = msg.pop("content")
    events = [("message_start", {"type": "message_start", "message": {**msg, "content": []}})]
    for index, block in enumerate(content):
        events.append(("content_block_start", {"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}}))
        events.append(("content_block_delta", {"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": block["text"]}}))
        events.append(("content_block_stop", {"type": "content_block_stop", "index": index}))
    events.append(("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 3}}))
    events.append(("message_stop", {"type": "message_stop"}))
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events).encode()


def test_requests_are_accepted_by_real_sdk_and_serialize_verbatim_blocks(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    bodies: List[Dict[str, Any]] = []
    reply = {
        "id": "msg_x", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }

    def handler(request):
        bodies.append({"path": request.url.path, "headers": dict(request.headers), "json": json.loads(request.content)})
        return httpx2.Response(200, content=_sse(reply), headers={"content-type": "text/event-stream"})

    real_client = anthropic.Anthropic(
        api_key="test-key",
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
        max_retries=0,
    )
    provider = make_provider()  # fallbacks on -> beta API
    timeline = base_timeline() + [
        AnthropicAssistantTurn(
            content=[
                ThinkingBlock(type="thinking", thinking="t", signature="sig"),
                ToolUseBlock(type="tool_use", id="toolu_z", name="get_time", input={}),
            ]
        ),
        FunctionCallOutputEvent(call_id="toolu_z", function_name="get_time", output_text="noon"),
    ]
    response = provider.call_model(real_client, conversation=[], timeline=timeline, tool_specs=_specs(), effort="high")
    assert response.message.text_content() == "ok"

    sent = bodies[0]["json"]
    assert sent["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in bodies[0]["headers"].get("anthropic-beta", "")
    assert sent["messages"][1]["content"][0] == {"type": "thinking", "thinking": "t", "signature": "sig"}
    assert sent["messages"][1]["content"][1]["id"] == "toolu_z"
    assert sent["messages"][2]["content"][0]["tool_use_id"] == "toolu_z"
    assert sent["output_config"] == {"effort": "high"}

    # Non-beta path (no fallbacks) must also be accepted by client.messages.stream.
    provider2 = make_provider(name="claude-haiku-4-5", params={"stop": "END", "metadata": {"user_id": "u"}})
    provider2.call_model(real_client, conversation=[], timeline=base_timeline(), tool_specs=None)
    assert "betas" not in bodies[1]["json"]
    assert bodies[1]["json"]["stop_sequences"] == ["END"]


# ----------------------------------------------------------------------------
# Registration
# ----------------------------------------------------------------------------


def test_anthropic_provider_is_registered():
    from agentdev.runtime.node.agent.providers import builtin_providers  # noqa: F401
    from agentdev.runtime.node.agent.providers.base import ProviderRegistry

    if "anthropic" not in ProviderRegistry.list_providers():
        pytest.skip("builtin_providers.py does not register 'anthropic' yet")
    assert ProviderRegistry.get_provider("anthropic") is AnthropicProvider
