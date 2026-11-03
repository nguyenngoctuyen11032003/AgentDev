"""Workflow assistant prompt: chat vendor hint."""

from agentdev.api.services.workflow_assistant_prompt import build_system_prompt


def _prompt(**overrides):
    kwargs = dict(current_yaml=None, current_name=None, pending_yaml=None, existing_files=[],
                  skills=[], tools=[], models={"anthropic": ["claude-opus-5-5"], "openai": ["gpt-6.1-sol"]})
    kwargs.update(overrides)
    return build_system_prompt(**kwargs)


def test_prompt_states_chat_vendor():
    assert ("The user is chatting with Codex (vendor openai); default new agents to that vendor's models."
            in _prompt(chat_vendor="openai"))
    assert "The user is chatting with Claude (vendor anthropic)" in _prompt(chat_vendor="anthropic")
    assert "The user is chatting with" not in _prompt()
