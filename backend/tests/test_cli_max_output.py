"""A6-5: YAML ``params.max_tokens`` reaches the Claude CLI as CLAUDE_CODE_MAX_OUTPUT_TOKENS (flag AGENTDEV_CLI_MAX_OUTPUT)."""

import pytest

from agentdev.runtime.node.agent.providers import _cli_common as cc


def test_flag_off_sends_nothing(monkeypatch):
    monkeypatch.setenv("AGENTDEV_CLI_MAX_OUTPUT", "0")
    assert cc.max_output_env({"max_tokens": 8000}) == {}


@pytest.mark.parametrize("value,expected", [(8000, "8000"), ("16000", "16000"), (999999, "64000")])
def test_flag_on_passes_the_cap(monkeypatch, value, expected):
    monkeypatch.setenv("AGENTDEV_CLI_MAX_OUTPUT", "1")
    assert cc.max_output_env({"max_tokens": value}) == {cc.MAX_OUTPUT_ENV: expected}


@pytest.mark.parametrize("params", [None, {}, {"max_tokens": True}, {"max_tokens": "x"}, {"max_tokens": 10}, {"max_tokens": None}])
def test_unusable_values_are_ignored(monkeypatch, params):
    monkeypatch.setenv("AGENTDEV_CLI_MAX_OUTPUT", "1")
    assert cc.max_output_env(params) == {}


def test_run_cli_merges_extra_env(monkeypatch, tmp_path):
    seen = {}

    def fake_capture(cmd, **kwargs):
        seen.update(kwargs["env"])
        return None

    monkeypatch.setattr(cc.cli_auth, "run_capture", fake_capture)
    cc.run_cli(["x"], "p", 5, "fake", str(tmp_path), extra_env={cc.MAX_OUTPUT_ENV: "8000"})
    assert seen[cc.MAX_OUTPUT_ENV] == "8000"
