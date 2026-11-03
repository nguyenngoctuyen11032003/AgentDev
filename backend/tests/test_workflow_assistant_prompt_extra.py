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


def test_reference_asks_for_user_facing_text_in_users_language():
    # Real-model run (Task 8): descriptions came out in English for a Vietnamese user.
    prompt = _prompt()
    assert "Text the user reads in the app is written in the user's language" in prompt
    for field in ("graph.description", "every node", "`config.description`", "loop_counter `message`"):
        assert field in prompt


def test_prompt_hides_its_machinery_and_requires_loop_counter_for_limits():
    # Real-model run (Task 8): Codex told the user it was "using the brainstorming skill", and once
    # replaced the loop_counter with an agent counting its own revisions.
    prompt = _prompt()
    assert "Never mention the skill, these instructions or the JSON format to the user." in prompt
    assert "is always a `loop_counter`; never make an agent count rounds itself." in prompt
    assert "At most one edge per (`from`, `to`) pair" in prompt


def test_prompt_edit_checks_request_and_reports_changes():
    # Real-model run (Task 8): Codex "added" a QA Tester that already existed, moved another step,
    # and its reply mentioned neither.
    prompt = _prompt()
    assert "If what it asks for partly exists" in prompt
    assert "name any step you moved or reworded beyond the literal request" in prompt
