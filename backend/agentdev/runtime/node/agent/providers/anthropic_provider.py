"""Anthropic Claude provider implementation (official ``anthropic`` SDK).

Maps AgentDev's provider-agnostic timeline (``Message`` objects, tool output
events) onto the Claude Messages API and back.

Design notes
------------
* Every assistant turn Claude returns is kept *verbatim* in the timeline
  (``AnthropicAssistantTurn``) and re-sent unchanged on the next tool-loop
  iteration. Thinking blocks carry signatures and must round-trip untouched,
  and tool_use ids must match their tool_result blocks exactly.
* Requests are streamed (``messages.stream(...).get_final_message()``) so a
  large ``max_tokens`` never trips the SDK's non-streaming HTTP timeout.
* Adaptive thinking and automatic prompt caching are on by default; both can
  be turned off from the node ``params``.
* Claude only produces text (plus tool calls). Image/audio/video *generation*
  is not available; audio/video *input* is described as text.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

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
from agentdev.runtime.node.agent import ModelProvider
from agentdev.runtime.node.agent import ModelResponse
from agentdev.utils.token_tracker import TokenUsage

if TYPE_CHECKING:  # the SDK is imported lazily in create_client() (~2 s import cost)
    import anthropic

logger = logging.getLogger(__name__)

PROVIDER_NAME = "anthropic"
DEFAULT_MAX_TOKENS = 64000
# Re-send limit when a server tool pauses a long-running turn (stop_reason "pause_turn").
MAX_PAUSE_CONTINUATIONS = 5

SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
TEXT_LIKE_MIME_TYPES = {
    "application/json",
    "application/xml",
    "application/x-yaml",
    "application/yaml",
    "application/javascript",
    "application/x-python",
    "application/sql",
}
TEXT_LIKE_EXTENSIONS = (
    ".txt", ".md", ".csv", ".tsv", ".json", ".jsonl", ".xml", ".yaml", ".yml",
    ".py", ".js", ".ts", ".html", ".css", ".sql", ".log", ".ini", ".toml",
)

# Current Claude models reject sampling parameters; they are dropped unless
# the node opts in with ``allow_sampling_params: true``.
SAMPLING_PARAMS = ("temperature", "top_p", "top_k")
# Models that accept the server-side refusal fallback (``fallbacks: "default"``).
FALLBACK_MODELS = {"claude-opus-5-5", "claude-fable-5-1", "claude-opus-5", "claude-sonnet-5-5"}
# Models that reject forced tool_choice ({"type": "any"} / {"type": "tool"}) with a 400.
NO_FORCED_TOOL_CHOICE_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1", "claude-mythos-5-1"}
FALLBACK_BETA_DEFAULT = "server-side-fallback-2026-07-01"  # scalar form: fallbacks="default"
FALLBACK_BETA_LIST = "server-side-fallback-2026-06-01"  # array form: fallbacks=[{"model": ...}]
# Models that predate adaptive thinking: no thinking is sent unless configured.
NO_ADAPTIVE_THINKING_MARKERS = (
    "claude-2", "claude-3", "claude-instant",
    "haiku-4-5", "sonnet-4-5", "opus-4-5", "opus-4-1",
    "sonnet-4-0", "opus-4-0", "claude-sonnet-4-2", "claude-opus-4-2",
)
# Keys forwarded to messages.create/stream unchanged when present in params.
PASSTHROUGH_PARAMS = (
    "metadata", "inference_geo", "service_tier", "extra_headers", "extra_body",
    "context_management", "container", "mcp_servers",
)
# Passthrough keys only accepted by client.beta.messages.* in the installed SDK.
BETA_ONLY_PARAMS = ("context_management", "mcp_servers")
# Keys other providers use that mean nothing to Claude; ignored silently.
IGNORED_PARAMS = (
    "protocol", "frequency_penalty", "presence_penalty", "seed", "n",
    "response_modalities", "candidate_count", "image_config", "aspect_ratio",
    "safety_settings", "audio_config", "video_config", "parallel_tool_calls",
)
OFF_VALUES = (False, None, "off", "none", "false", "no", 0)

_UNSET = object()
_INVALID_ID_CHARS = re.compile(r"[^a-zA-Z0-9_-]")


@dataclass
class AnthropicAssistantTurn:
    """Claude's raw assistant content, kept verbatim so it can be re-sent unchanged."""

    content: List[Any] = field(default_factory=list)


class AnthropicProvider(ModelProvider):
    """Anthropic Claude provider using the Messages API."""

    def __init__(self, config):
        super().__init__(config)
        # Sanitized tool name -> original AgentDev tool name (Claude requires ^[a-zA-Z0-9_-]{1,128}$).
        self._tool_name_map: Dict[str, str] = {}
        self._warned_sampling = False
        self._warned_base_url = False

    # ------------------------------------------------------------------
    # ModelProvider API
    # ------------------------------------------------------------------

    def create_client(self) -> anthropic.Anthropic:
        client_kwargs: Dict[str, Any] = {}
        api_key = (self.api_key or "").strip()
        if api_key:
            client_kwargs["api_key"] = api_key  # otherwise the SDK resolves ANTHROPIC_API_KEY etc.
        base_url = self._resolved_base_url()
        if base_url:
            client_kwargs["base_url"] = base_url
        timeout = (self.params or {}).get("timeout")
        if timeout:
            client_kwargs["timeout"] = float(timeout)
        max_retries = (self.params or {}).get("max_retries")
        if max_retries is not None:
            client_kwargs["max_retries"] = int(max_retries)
        import anthropic

        return anthropic.Anthropic(**client_kwargs)

    def call_model(
        self,
        client,
        conversation: List[Message],
        timeline: List[Any],
        tool_specs: Optional[List[ToolSpec]] = None,
        **kwargs,
    ) -> ModelResponse:
        options = dict(self.params or {})
        options.update(kwargs)
        streaming = options.pop("stream", True) not in OFF_VALUES

        system, messages = self._build_messages(timeline)
        request = self._build_request(system, messages, tool_specs, options)
        response = self._send(client, request, streaming)

        # Paused turns are collected locally and only committed to the shared timeline
        # once the whole call succeeds, so an executor-level retry starts from a clean timeline.
        paused_turns: List[AnthropicAssistantTurn] = []
        while getattr(response, "stop_reason", None) == "pause_turn" and len(paused_turns) < MAX_PAUSE_CONTINUATIONS:
            # A server tool paused the turn: keep the partial turn and let Claude continue it.
            self._track_token_usage(response)
            paused_turns.append(AnthropicAssistantTurn(content=list(response.content)))
            # Re-send ending on the paused assistant turn: the API resumes from its trailing
            # server_tool_use block. An extra user message ("Continue.") must NOT be added.
            _, request["messages"] = self._build_messages(timeline + paused_turns, allow_trailing_assistant=True)
            response = self._send(client, request, streaming)

        self._track_token_usage(response)
        message = self._deserialize_response(response)
        timeline.extend(paused_turns)
        timeline.append(AnthropicAssistantTurn(content=list(response.content)))
        return ModelResponse(message=message, raw_response=response)

    def extract_token_usage(self, response: Any) -> TokenUsage:
        usage = getattr(response, "usage", None)
        if not usage:
            return TokenUsage()
        uncached = getattr(usage, "input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        input_tokens = uncached + cache_write + cache_read
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            metadata={
                "input_tokens": uncached,
                "cache_creation_input_tokens": cache_write,
                "cache_read_input_tokens": cache_read,
                "output_tokens": output_tokens,
                "stop_reason": getattr(response, "stop_reason", None),
            },
        )

    # ------------------------------------------------------------------
    # Request building
    # ------------------------------------------------------------------

    def _send(self, client: anthropic.Anthropic, request: Dict[str, Any], streaming: bool) -> Any:
        # Beta-only kwargs raise TypeError on client.messages.*; route them to the beta API.
        use_beta = bool(request.get("betas")) or any(key in request for key in BETA_ONLY_PARAMS)
        api = client.beta.messages if use_beta else client.messages
        if streaming:
            with api.stream(**request) as stream:
                return stream.get_final_message()
        return api.create(**request)

    def _build_request(
        self,
        system: Optional[str],
        messages: List[Dict[str, Any]],
        tool_specs: Optional[List[ToolSpec]],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        params = dict(params)
        # Client-level settings, already applied in create_client().
        params.pop("timeout", None)
        params.pop("max_retries", None)

        max_tokens = params.pop("max_tokens", None)
        max_output_tokens = params.pop("max_output_tokens", None)
        request: Dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": int(max_tokens or max_output_tokens or DEFAULT_MAX_TOKENS),
            "messages": messages,
        }
        if system:
            request["system"] = system

        allow_sampling = params.pop("allow_sampling_params", False) not in OFF_VALUES
        dropped = [key for key in SAMPLING_PARAMS if key in params]
        for key in dropped:
            value = params.pop(key)
            if allow_sampling:
                request[key] = value
        if dropped and not allow_sampling and not self._warned_sampling:
            self._warned_sampling = True
            logger.warning(
                "Dropping %s for Claude model %s: current Claude models reject sampling "
                "parameters (set params.allow_sampling_params: true to send them anyway).",
                ", ".join(dropped),
                self.model_name,
            )

        thinking = self._resolve_thinking(params.pop("thinking", _UNSET), params.pop("thinking_display", None))
        if thinking:
            request["thinking"] = thinking

        output_config = dict(params.pop("output_config", None) or {})
        effort = params.pop("effort", None)
        reasoning = params.pop("reasoning", None)  # OpenAI-style {"effort": ...}
        if not effort and isinstance(reasoning, dict):
            effort = reasoning.get("effort")
        if effort:
            output_config["effort"] = effort
        if output_config:
            request["output_config"] = output_config

        if params.pop("prompt_caching", True) not in OFF_VALUES:
            request["cache_control"] = {"type": "ephemeral"}

        stop_sequences = params.pop("stop_sequences", None) or params.pop("stop", None)
        if stop_sequences:
            request["stop_sequences"] = [stop_sequences] if isinstance(stop_sequences, str) else list(stop_sequences)

        tools = self._build_tools(tool_specs or [])
        server_tools = params.pop("server_tools", None) or []
        user_tools = params.pop("tools", None) or []  # raw Anthropic tool definitions
        tools.extend(list(server_tools) + list(user_tools))
        tool_choice = params.pop("tool_choice", None)
        if tools:
            request["tools"] = tools
            if tool_choice is not None:
                request["tool_choice"] = self._coerce_tool_choice(tool_choice, thinking_on=bool(thinking))

        for key in PASSTHROUGH_PARAMS:
            if key in params:
                request[key] = params.pop(key)

        betas = list(params.pop("betas", None) or [])
        fallbacks = self._resolve_fallbacks(params.pop("fallbacks", _UNSET))
        if fallbacks:
            request["fallbacks"] = fallbacks
            beta = FALLBACK_BETA_DEFAULT if fallbacks == "default" else FALLBACK_BETA_LIST
            if beta not in betas:
                betas.append(beta)
        if betas:
            request["betas"] = betas

        for key in IGNORED_PARAMS:
            params.pop(key, None)
        if params:
            logger.debug("Ignoring params not used by the Claude provider: %s", sorted(params))
        return request

    def _resolve_thinking(self, thinking: Any, display: Optional[str]) -> Optional[Dict[str, Any]]:
        if thinking is _UNSET:
            config = {"type": "adaptive"} if self._supports_adaptive_thinking() else None
        elif isinstance(thinking, dict):
            config = dict(thinking)
        elif thinking is True or (isinstance(thinking, str) and thinking.lower() == "adaptive"):
            config = {"type": "adaptive"}
        elif thinking in OFF_VALUES or (isinstance(thinking, str) and thinking.lower() in OFF_VALUES):
            config = None
        else:
            raise ValueError(
                f"Unsupported thinking value {thinking!r} for Claude; use a dict, true/'adaptive', or false/'off'."
            )
        if config and display and config.get("type") == "adaptive":
            config.setdefault("display", display)
        return config

    def _resolve_fallbacks(self, fallbacks: Any) -> Any:
        if fallbacks is _UNSET:
            if self.model_name in FALLBACK_MODELS and self._is_official_endpoint():
                return "default"
            return None
        if fallbacks in OFF_VALUES or (isinstance(fallbacks, str) and fallbacks.lower() in OFF_VALUES):
            return None
        return fallbacks

    def _supports_adaptive_thinking(self) -> bool:
        name = self.model_name.lower()
        return not any(marker in name for marker in NO_ADAPTIVE_THINKING_MARKERS)

    def _resolved_base_url(self) -> Optional[str]:
        raw = (self.base_url or "").strip()
        if not raw:
            return None
        if "api.openai.com" in raw or "generativelanguage.googleapis.com" in raw:
            # Typical copy/paste of ${BASE_URL} from an OpenAI/Gemini node.
            if not self._warned_base_url:
                self._warned_base_url = True
                logger.warning(
                    "Ignoring base_url %s for Claude node (it points at another provider); "
                    "using ANTHROPIC_BASE_URL or the official Anthropic endpoint instead.",
                    raw,
                )
            return None
        return raw

    def _is_official_endpoint(self) -> bool:
        url = self._resolved_base_url() or os.environ.get("ANTHROPIC_BASE_URL", "")
        return not url or "api.anthropic.com" in url

    def _coerce_tool_choice(self, tool_choice: Any, *, thinking_on: bool = False) -> Any:
        choice = self._normalize_tool_choice(tool_choice)
        if choice.get("type") in ("any", "tool"):
            # Forced tool use is rejected (400) on the newest models and whenever thinking is on.
            if self.model_name in NO_FORCED_TOOL_CHOICE_MODELS or thinking_on:
                logger.warning(
                    "Forced tool_choice %s is not supported for %s%s; using {'type': 'auto'} instead. "
                    "Ask for the tool in the prompt (or set params.thinking: false on older models).",
                    choice,
                    self.model_name,
                    " with thinking enabled" if thinking_on else "",
                )
                downgraded = {"type": "auto"}
                if "disable_parallel_tool_use" in choice:
                    downgraded["disable_parallel_tool_use"] = choice["disable_parallel_tool_use"]
                return downgraded
        return choice

    def _normalize_tool_choice(self, tool_choice: Any) -> Dict[str, Any]:
        if isinstance(tool_choice, dict):
            choice = dict(tool_choice)
            # OpenAI shape {"type": "function", "function": {"name": ...}}
            if choice.get("type") == "function":
                name = (choice.get("function") or {}).get("name") or choice.get("name")
                return {"type": "tool", "name": self._api_tool_name(name or "")}
            if choice.get("type") == "tool" and choice.get("name"):
                choice["name"] = self._api_tool_name(choice["name"])
            return choice
        value = str(tool_choice).lower()
        if value == "required":
            return {"type": "any"}
        if value in ("auto", "none", "any"):
            return {"type": value}
        return {"type": "tool", "name": self._api_tool_name(str(tool_choice))}

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def _build_tools(self, tool_specs: List[ToolSpec]) -> List[Dict[str, Any]]:
        self._tool_name_map = {}
        tools: List[Dict[str, Any]] = []
        for spec in tool_specs:
            base = self._sanitize_tool_name(spec.name)
            name, suffix = base, 2
            # "a.b" and "a_b" sanitize to the same name; duplicates are a 400, so suffix them.
            while name in self._tool_name_map and self._tool_name_map[name] != spec.name:
                tail = f"_{suffix}"
                name, suffix = base[: 128 - len(tail)] + tail, suffix + 1
            if name in self._tool_name_map:
                continue  # same tool listed twice
            self._tool_name_map[name] = spec.name
            schema = dict(spec.parameters or {})
            if schema.get("type") != "object":
                schema = {"type": "object", "properties": schema.get("properties", {}), **{
                    k: v for k, v in schema.items() if k not in ("type", "properties")
                }}
            schema.setdefault("properties", {})
            tool: Dict[str, Any] = {"name": name, "input_schema": schema}
            if spec.description:
                tool["description"] = spec.description
            tools.append(tool)
        return tools

    def _sanitize_tool_name(self, name: str) -> str:
        cleaned = _INVALID_ID_CHARS.sub("_", name or "")[:128]
        return cleaned or "tool"

    def _original_tool_name(self, name: str) -> str:
        return self._tool_name_map.get(name, name)

    def _api_tool_name(self, original: str) -> str:
        for api_name, source in self._tool_name_map.items():
            if source == original:
                return api_name
        return self._sanitize_tool_name(original)

    def _sanitize_tool_id(self, raw: Optional[str]) -> str:
        cleaned = _INVALID_ID_CHARS.sub("_", raw or "")
        return cleaned or f"toolu_{uuid.uuid4().hex}"

    # ------------------------------------------------------------------
    # Timeline -> Messages API payload
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        timeline: List[Any],
        *,
        allow_trailing_assistant: bool = False,
    ) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        system_parts: List[str] = []
        messages: List[Dict[str, Any]] = []
        known_tool_ids: set[str] = set()

        for item in timeline:
            if isinstance(item, AnthropicAssistantTurn):
                for block in item.content:
                    if self._block_attr(block, "type") == "tool_use":
                        known_tool_ids.add(self._block_attr(block, "id"))
                self._append(messages, "assistant", list(item.content))
                continue

            if isinstance(item, FunctionCallOutputEvent):
                self._append(messages, "user", [self._event_to_tool_result(item, known_tool_ids)])
                continue

            if not isinstance(item, Message):
                continue  # native objects from other providers

            if item.role is MessageRole.SYSTEM:
                text = item.text_content().strip()
                if text:
                    system_parts.append(text)
            elif item.role is MessageRole.TOOL:
                self._append(messages, "user", [self._tool_message_to_result(item, known_tool_ids)])
            elif item.role is MessageRole.ASSISTANT:
                self._append(messages, "assistant", self._assistant_message_content(item, known_tool_ids))
            else:
                self._append(messages, "user", self._user_message_content(item))

        # The conversation must open with a user turn and must not end on an
        # assistant turn (prefill is rejected by current models).
        if not messages or messages[0]["role"] != "user":
            messages.insert(0, {"role": "user", "content": [self._text("Begin.")]})
        messages = self._repair_tool_pairing(messages, allow_trailing_assistant)
        if messages[-1]["role"] == "assistant" and not allow_trailing_assistant:
            messages.append({"role": "user", "content": [self._text("Continue.")]})

        system = "\n\n".join(system_parts) if system_parts else None
        return system, messages

    def _repair_tool_pairing(
        self,
        messages: List[Dict[str, Any]],
        allow_trailing_assistant: bool,
    ) -> List[Dict[str, Any]]:
        """Enforce the API's tool_use/tool_result pairing rules.

        Every tool_use in an assistant turn needs a tool_result in the *immediately
        following* user message, those tool_results must come first in that message,
        and a tool_result may only answer a tool_use from the turn right before it.
        History from other providers / a tool loop cut off by the loop limit can
        violate this; assistant turns are never edited (thinking signatures), only
        the user side is fixed up.
        """
        repaired: List[Dict[str, Any]] = []
        pending: List[str] = []  # tool_use ids of the previous assistant turn
        for index, message in enumerate(messages):
            if message["role"] == "assistant":
                if pending:
                    # Assistant follows assistant-with-tool_use: no user turn in between.
                    repaired.append({"role": "user", "content": self._missing_results(pending)})
                repaired.append(message)
                pending = []
                for block in message["content"]:
                    if self._block_attr(block, "type") == "tool_use":
                        tool_id = self._block_attr(block, "id")
                        if tool_id and tool_id not in pending:
                            pending.append(tool_id)
                continue

            results: List[Any] = []
            others: List[Any] = []
            answered: set[str] = set()
            for block in message["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tool_id = block.get("tool_use_id")
                    if tool_id in pending and tool_id not in answered:
                        answered.add(tool_id)
                        results.append(block)
                    else:
                        others.extend(self._tool_result_as_text(block))
                else:
                    others.append(block)
            missing = [tool_id for tool_id in pending if tool_id not in answered]
            content = results + self._missing_results(missing) + others
            if content:
                repaired.append({"role": "user", "content": content})
            pending = []

        if pending and not allow_trailing_assistant:
            repaired.append({"role": "user", "content": self._missing_results(pending)})
        return repaired

    def _missing_results(self, tool_ids: List[str]) -> List[Dict[str, Any]]:
        return [
            {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": [self._text("(tool was not executed; no result available)")],
                "is_error": True,
            }
            for tool_id in tool_ids
        ]

    def _tool_result_as_text(self, block: Dict[str, Any]) -> List[Dict[str, Any]]:
        content = block.get("content")
        if isinstance(content, str):
            texts = [content]
        else:
            texts = [c.get("text", "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text"]
        return self._text_blocks(f"[Tool result {block.get('tool_use_id')}]\n" + "\n".join(texts))

    def _append(self, messages: List[Dict[str, Any]], role: str, content: List[Any]) -> None:
        if not content:
            return
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"].extend(content)
        else:
            messages.append({"role": role, "content": list(content)})

    def _user_message_content(self, message: Message) -> List[Dict[str, Any]]:
        content: List[Dict[str, Any]] = []
        blocks = message.blocks()
        if blocks:
            for block in blocks:
                content.extend(self._block_to_content(block, allow_media=True))
        else:
            content.extend(self._text_blocks(message.text_content()))
        return content

    def _assistant_message_content(self, message: Message, known_tool_ids: set[str]) -> List[Dict[str, Any]]:
        content: List[Dict[str, Any]] = []
        blocks = message.blocks()
        if blocks:
            for block in blocks:
                # Assistant turns may only carry text (and tool_use).
                content.extend(self._block_to_content(block, allow_media=False))
        else:
            content.extend(self._text_blocks(message.text_content()))
        for call in message.tool_calls or []:
            tool_id = self._sanitize_tool_id(call.id)
            known_tool_ids.add(tool_id)
            content.append({
                "type": "tool_use",
                "id": tool_id,
                "name": self._sanitize_tool_name(call.function_name),
                "input": self._parse_arguments(call.arguments),
            })
        return content

    def _tool_message_to_result(self, message: Message, known_tool_ids: set[str]) -> Dict[str, Any]:
        content: List[Dict[str, Any]] = []
        blocks = message.blocks()
        if blocks:
            for block in blocks:
                content.extend(self._block_to_content(block, allow_media=True, for_tool_result=True))
        else:
            content.extend(self._text_blocks(message.text_content()))
        text = message.text_content() or ""
        return self._tool_result(message.tool_call_id, content, known_tool_ids, is_error=self._looks_like_error(text))

    def _event_to_tool_result(self, event: FunctionCallOutputEvent, known_tool_ids: set[str]) -> Dict[str, Any]:
        content: List[Dict[str, Any]] = []
        if event.output_blocks:
            for block in event.output_blocks:
                content.extend(self._block_to_content(block, allow_media=True, for_tool_result=True))
        elif event.output_text:
            content.extend(self._text_blocks(event.output_text))
        return self._tool_result(
            event.call_id,
            content,
            known_tool_ids,
            is_error=self._looks_like_error(event.output_text or ""),
            tool_name=event.function_name,
        )

    def _tool_result(
        self,
        call_id: Optional[str],
        content: List[Dict[str, Any]],
        known_tool_ids: set[str],
        *,
        is_error: bool = False,
        tool_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        tool_id = self._sanitize_tool_id(call_id)
        if not content:
            content = [self._text("(no output)")]
        if tool_id not in known_tool_ids:
            # A result without a matching tool_use (e.g. history from another provider)
            # would be rejected; pass it on as plain text instead.
            label = tool_name or call_id or "tool"
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return self._text(f"[Result of {label}]\n" + "\n".join(texts))
        result: Dict[str, Any] = {"type": "tool_result", "tool_use_id": tool_id, "content": content}
        if is_error:
            result["is_error"] = True
        return result

    def _looks_like_error(self, text: str) -> bool:
        # AgentDev's executor reports tool failures as "error: ..." / "Error: ..." / "Tool X error: ...".
        lowered = text.strip().lower()
        return lowered.startswith("error:") or (lowered.startswith("tool ") and " error: " in lowered[:200])

    def _parse_arguments(self, arguments: Any) -> Dict[str, Any]:
        if isinstance(arguments, dict):
            return arguments
        if not arguments:
            return {}
        try:
            parsed = json.loads(arguments)
        except (TypeError, ValueError):
            return {"input": arguments}
        return parsed if isinstance(parsed, dict) else {"input": parsed}

    # ------------------------------------------------------------------
    # Content blocks / attachments
    # ------------------------------------------------------------------

    def _block_to_content(
        self,
        block: Any,
        *,
        allow_media: bool,
        for_tool_result: bool = False,
    ) -> List[Dict[str, Any]]:
        if isinstance(block, dict):
            try:
                block = MessageBlock.from_dict(block)
            except Exception:
                return self._text_blocks(json.dumps(block, ensure_ascii=False, default=str))
        if not isinstance(block, MessageBlock):
            return self._text_blocks(str(block))

        if block.type is MessageBlockType.TEXT:
            return self._text_blocks(block.text or "")
        if block.type is MessageBlockType.DATA:
            return self._text_blocks(block.text or json.dumps(block.data or {}, ensure_ascii=False, default=str))

        attachment = block.attachment
        if attachment is None:
            return self._text_blocks(block.text or "")
        if not allow_media:
            return self._text_blocks(block.describe())

        mime = (attachment.mime_type or self._guess_mime(block)).lower()
        name = attachment.name or attachment.attachment_id or "attachment"

        if mime in SUPPORTED_IMAGE_TYPES:
            image = self._image_content(attachment, mime)
            if image:
                return [image]
            return [self._text(f"[Image {name} could not be attached (missing or larger than 5 MB)]")]

        if mime == "application/pdf" and not for_tool_result:
            data = self._read_attachment_bytes(attachment)
            if data:
                return [{
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.standard_b64encode(data).decode("ascii"),
                    },
                    "title": name,
                }]

        if self._is_text_like(mime, name):
            data = self._read_attachment_bytes(attachment)
            if data is not None:
                return self._text_blocks(f"[Attachment: {name}]\n{self._bytes_to_text(data)}")

        if mime.startswith("image/"):
            return [self._text(f"[Image {name} ({mime}) omitted: Claude accepts JPEG, PNG, GIF and WebP only]")]
        return [self._text(f"[Attachment {name} ({mime}) omitted: not supported by Claude] {block.describe()}".strip())]

    def _image_content(self, attachment: AttachmentRef, mime: str) -> Optional[Dict[str, Any]]:
        remote = attachment.remote_file_id or ""
        if remote.startswith(("http://", "https://")) and not attachment.data_uri and not attachment.local_path:
            return {"type": "image", "source": {"type": "url", "url": remote}}
        data = self._read_attachment_bytes(attachment)
        if not data or len(data) > MAX_IMAGE_BYTES:
            return None
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime,
                "data": base64.standard_b64encode(data).decode("ascii"),
            },
        }

    def _is_text_like(self, mime: str, name: str) -> bool:
        return (
            mime.startswith("text/")
            or mime in TEXT_LIKE_MIME_TYPES
            or mime.endswith("+json")
            or mime.endswith("+xml")
            or name.lower().endswith(TEXT_LIKE_EXTENSIONS)
        )

    def _guess_mime(self, block: MessageBlock) -> str:
        if block.type is MessageBlockType.IMAGE:
            return "image/png"
        if block.type is MessageBlockType.AUDIO:
            return "audio/mpeg"
        if block.type is MessageBlockType.VIDEO:
            return "video/mp4"
        return "application/octet-stream"

    def _read_attachment_bytes(self, attachment: AttachmentRef) -> Optional[bytes]:
        if attachment.data_uri:
            decoded = self._decode_data_uri(attachment.data_uri)
            if decoded is not None:
                return decoded
        if attachment.local_path and os.path.exists(attachment.local_path):
            try:
                with open(attachment.local_path, "rb") as handle:
                    return handle.read()
            except OSError:
                return None
        return None

    def _decode_data_uri(self, data_uri: str) -> Optional[bytes]:
        if not data_uri.startswith("data:"):
            return None
        header, sep, data = data_uri.partition(",")
        if not sep:
            return None
        if ";base64" in header:
            try:
                return base64.b64decode(data)
            except (ValueError, binascii.Error):
                return None
        return data.encode("utf-8")

    def _bytes_to_text(self, data: bytes) -> str:
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("utf-8", errors="replace")

    def _text(self, text: str) -> Dict[str, Any]:
        return {"type": "text", "text": text}

    def _text_blocks(self, text: Optional[str]) -> List[Dict[str, Any]]:
        # The API rejects empty / whitespace-only text blocks.
        return [self._text(text)] if text and text.strip() else []

    @staticmethod
    def _block_attr(block: Any, name: str) -> Any:
        if isinstance(block, dict):
            return block.get(name)
        return getattr(block, name, None)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _deserialize_response(self, response: Any) -> Message:
        blocks: List[MessageBlock] = []
        tool_calls: List[ToolCallPayload] = []
        thinking_summaries: List[str] = []

        for block in getattr(response, "content", None) or []:
            block_type = self._block_attr(block, "type")
            if block_type == "text":
                text = self._block_attr(block, "text")
                if text:
                    blocks.append(MessageBlock(MessageBlockType.TEXT, text=text))
            elif block_type == "tool_use":
                tool_input = self._block_attr(block, "input") or {}
                tool_calls.append(
                    ToolCallPayload(
                        id=self._block_attr(block, "id") or f"toolu_{uuid.uuid4().hex}",
                        function_name=self._original_tool_name(self._block_attr(block, "name") or ""),
                        arguments=json.dumps(tool_input, ensure_ascii=False),
                        type="function",
                    )
                )
            elif block_type == "thinking":
                summary = self._block_attr(block, "thinking")
                if summary:
                    thinking_summaries.append(summary)
            # redacted_thinking, fallback and server-tool blocks only live in the raw turn.

        stop_reason = getattr(response, "stop_reason", None)
        metadata: Dict[str, Any] = {
            "provider": PROVIDER_NAME,
            "model": getattr(response, "model", self.model_name),
            "stop_reason": stop_reason,
        }
        if thinking_summaries:
            metadata["thinking"] = "\n\n".join(thinking_summaries)

        if stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            metadata["refusal_category"] = category
            tool_calls = []
            if not blocks:
                suffix = f" (category: {category})" if category else ""
                blocks.append(MessageBlock(MessageBlockType.TEXT, text=f"[Claude declined this request{suffix}]"))
        elif stop_reason == "max_tokens" and tool_calls:
            # The last tool call may be cut off mid-input; don't execute partial calls.
            logger.warning(
                "Claude hit max_tokens while writing a tool call (model %s); raise params.max_tokens.",
                self.model_name,
            )
            tool_calls = []
            blocks.append(MessageBlock(
                MessageBlockType.TEXT,
                text="[Response truncated at max_tokens before the tool call was complete]",
            ))

        return Message(
            role=MessageRole.ASSISTANT,
            content=blocks or "",
            tool_calls=tool_calls,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Token tracking
    # ------------------------------------------------------------------

    def _track_token_usage(self, response: Any) -> None:
        token_tracker = getattr(self.config, "token_tracker", None)
        if not token_tracker:
            return
        usage = self.extract_token_usage(response)
        if usage.input_tokens == 0 and usage.output_tokens == 0:
            return
        node_id = getattr(self.config, "node_id", "ALL")
        usage.node_id = node_id
        usage.model_name = self.model_name
        usage.workflow_id = token_tracker.workflow_id
        usage.provider = PROVIDER_NAME
        token_tracker.record_usage(node_id, self.model_name, usage, provider=PROVIDER_NAME)
