"""Register built-in agent providers.

Models run only through a signed-in account: the local Claude Code / Codex CLIs, or
Gemini with Google sign-in. There are no API-key providers.
"""

from agentdev.runtime.node.agent.providers.base import ProviderRegistry
from agentdev.runtime.node.agent.providers.claude_cli_provider import ClaudeCliProvider
from agentdev.runtime.node.agent.providers.codex_cli_provider import CodexCliProvider

ProviderRegistry.register(
    "claude_cli",
    ClaudeCliProvider,
    label="Claude (account sign-in)",
    summary="Runs on the Claude account signed in to the local `claude` CLI. Supports tools.",
)
ProviderRegistry.register(
    "codex_cli",
    CodexCliProvider,
    label="OpenAI Codex (account sign-in)",
    summary="Runs on the ChatGPT account signed in to the local `codex` CLI. Supports tools.",
)

try:
    from agentdev.runtime.node.agent.providers.gemini_provider import GeminiProvider
except ImportError:
    GeminiProvider = None

if GeminiProvider is not None:
    ProviderRegistry.register(
        "gemini",
        GeminiProvider,
        label="Google Gemini (Google sign-in)",
        summary="Google Gemini models with a Google account sign-in.",
    )
