import pytest

import agentdev.runtime.node.builtin_nodes  # noqa: F401 - registers node types
from agentdev.entity.configs.base import ConfigError
from agentdev.entity.configs.node.node import MASCOT_COUNT, Node

BASE = {"id": "A", "type": "passthrough", "config": {}}


def test_mascot_is_optional_and_parsed():
    assert Node.from_dict(BASE, path="n").mascot is None
    assert Node.from_dict({**BASE, "mascot": 5}, path="n").mascot == 5
    assert Node.from_dict({**BASE, "mascot": "7"}, path="n").mascot == 7


@pytest.mark.parametrize("value", [0, MASCOT_COUNT + 1, "x", True, 2.5])
def test_invalid_mascot_is_rejected(value):
    with pytest.raises(ConfigError):
        Node.from_dict({**BASE, "mascot": value}, path="n")


def test_mascot_field_is_exposed_to_the_editor():
    spec = Node.field_specs()["mascot"]
    assert spec.required is False
    assert spec.enum == list(range(1, MASCOT_COUNT + 1))
