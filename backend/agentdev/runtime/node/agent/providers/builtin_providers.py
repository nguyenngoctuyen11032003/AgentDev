"""Register built-in agent providers."""

from agentdev.runtime.node.agent.providers.base import ProviderRegistry

from agentdev.runtime.node.agent.providers.openai_provider import OpenAIProvider

ProviderRegistry.register(
    "openai",
    OpenAIProvider,
    label="OpenAI",
    summary="OpenAI models via the official OpenAI SDK (responses API)",
)

try:
    from agentdev.runtime.node.agent.providers.gemini_provider import GeminiProvider
except ImportError:
    GeminiProvider = None

if GeminiProvider is not None:
    ProviderRegistry.register(
        "gemini",
        GeminiProvider,
        label="Google Gemini",
        summary="Google Gemini models via google-genai",
    )
else:
    print("Gemini provider not registered: google-genai library not found.")

from agentdev.runtime.node.agent.providers.claude_cli_provider import ClaudeCliProvider
from agentdev.runtime.node.agent.providers.codex_cli_provider import CodexCliProvider

ProviderRegistry.register(
    "claude_cli",
    ClaudeCliProvider,
    label="Claude (CLI sign-in)",
    summary="Use your logged-in local `claude` CLI; no API key. Text only, tools unsupported.",
)
ProviderRegistry.register(
    "codex_cli",
    CodexCliProvider,
    label="OpenAI Codex (CLI sign-in)",
    summary="Use your logged-in local `codex` CLI; no API key. Text only. Codex can read local files: use only with trusted inputs.",
)

try:
    from agentdev.runtime.node.agent.providers.anthropic_provider import AnthropicProvider
except ImportError:
    AnthropicProvider = None

if AnthropicProvider is not None:
    ProviderRegistry.register(
        "anthropic",
        AnthropicProvider,
        label="Anthropic Claude",
        summary="Anthropic Claude models via the official anthropic SDK (Messages API)",
    )
else:
    print("Anthropic provider not registered: anthropic library not found.")
