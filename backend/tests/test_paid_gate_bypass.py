"""A paid gate is never approved on the user's behalf, in any run mode; silence is never approval."""

import itertools
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from agentdev.api.services.prompt_channel import WebPromptChannel
from agentdev.api.services.session_execution import NO_REPLY_TEXT
from agentdev.api.services.workflow_patterns.graph_analysis import Graph
from agentdev.utils.run_mode import RUN_MODE_AUTO_ANSWER, RUN_MODES, answers_automatically

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("mode, paid", list(itertools.product(RUN_MODES, (True, False))))
def test_answers_automatically_never_for_a_paid_gate(mode, paid):
    got = answers_automatically(mode, {"node_type": "human", "paid": paid})
    assert got is (mode == "bypass" and not paid)


@pytest.mark.parametrize("mode", RUN_MODES)
def test_prompt_channel_waits_for_the_person_at_a_paid_gate(mode):
    sent, waited = [], []

    class Controller:
        def set_waiting_for_input(self, *a):
            waited.append(a)

        def wait_for_human_input(self, session_id):
            return {"text": NO_REPLY_TEXT, "attachments": [], "timed_out": True}

    channel = WebPromptChannel(session_id="s", session_controller=Controller(), websocket_manager=None,
                               attachment_service=SimpleNamespace(), attachment_store=None, run_mode=mode)
    channel._send = sent.append
    channel._notify_human_prompt = lambda *a, **k: None
    result = channel.request(node_id="Gate", task="ok?", inputs="x", metadata={"node_type": "human", "paid": True})
    assert waited, "the paid gate must wait for the person"
    assert result.text == NO_REPLY_TEXT and RUN_MODE_AUTO_ANSWER not in result.text
    assert not any(m.get("type") == "auto_answered" for m in sent)


def _workflows():
    folders = [ROOT / "workspace" / "workflows", ROOT / "backend" / "agentdev" / "api" / "services" / "workflow_patterns"]
    return sorted(p for f in folders for p in f.glob("*.yaml"))


def _with_gates():
    return [p for p in _workflows() if "type: human" in p.read_text(encoding="utf-8")]


# The silence notice, and text that merely contains it next to an approval word
VARIANTS = [NO_REPLY_TEXT, NO_REPLY_TEXT + " OK", NO_REPLY_TEXT + " Approved", "OK " + NO_REPLY_TEXT]


def test_gate_workflows_are_found():
    names = {p.name for p in _with_gates()}
    assert {"support.yaml", "video.yaml", "video_production.yaml"} <= names


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("path", _with_gates(), ids=lambda p: p.name)
def test_silence_never_takes_an_approve_branch(path, variant):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    bad = Graph.from_workflow(data).humans_approving_silence(variant)
    assert bad == [], f"{path.name}: {bad}"


def test_every_workflow_ignores_silence():
    for path in _workflows():
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert Graph.from_workflow(data).humans_approving_silence(NO_REPLY_TEXT) == [], path.name
