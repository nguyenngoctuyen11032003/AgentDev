"""Secret masking shared by the Lab evidence, the judge prompt and the platform report."""

import pytest

from agentdev.api.services import workflow_lab
from agentdev.api.services.lab_diagnosis import build_platform_report
from agentdev.utils.redact import redact_secrets

SECRETS = [
    ("password=hunter2", "hunter2"),
    ("api_key=abc123", "abc123"),
    ('{"password": "pa55word"}', "pa55word"),
    ("X-Api-Key: k3yvalue", "k3yvalue"),
    ("Authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
    ("Authorization: Bearer eyJhbGciOi.payload.sig", "eyJhbGciOi"),
    ("token=abc", "abc"),
    ("clone ghp_" + "A" * 36 + " done", "ghp_" + "A" * 36),
    ("github_pat_" + "B1_" * 10, "github_pat_" + "B1_" * 10),
    ("key AIza" + "C" * 35, "AIza" + "C" * 35),
    ("slack xoxb-1234567890-abcdefghij", "xoxb-1234567890-abcdefghij"),
    ("slack xoxp-1234567890-abcdefghij", "xoxp-1234567890-abcdefghij"),
    ("sk-" + "d" * 20, "sk-" + "d" * 20),
]


@pytest.mark.parametrize("text,secret", SECRETS)
def test_redact_secrets_masks_common_credentials(text, secret):
    out = redact_secrets(text)
    assert secret not in out and "[REDACTED]" in out


def test_redact_keeps_ordinary_text():
    text = "Tool read_file raised KeyError: 'name' at line 12 (exit code 1)"
    assert redact_secrets(text) == text


def test_workflow_lab_uses_the_shared_redaction():
    assert "hunter2" not in workflow_lab._redact("password=hunter2")
    assert "ghp_" + "A" * 36 not in workflow_lab._redact("ghp_" + "A" * 36)


@pytest.mark.parametrize("text,secret", SECRETS)
def test_platform_report_masks_secrets(text, secret):
    class Scenario:
        name = "sc"
        prompt = "deploy with " + text

    runs = [{"scenario": 0, "repeat": 1, "status": "error", "error": "boom " + text, "error_kind": "internal",
             "evidence": [{"node": "n", "tool": "run", "ok": False, "command": "curl -H '" + text + "'"}]}]
    findings = [{"code": "platform_error", "layer": "platform", "scenario": 0, "repeat": 1, "severity": "fail",
                 "detail": "d"}]
    report = build_platform_report("wf.yaml", runs, [Scenario()], findings)
    assert report and secret not in report
