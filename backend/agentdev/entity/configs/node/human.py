"""Human node configuration."""

from dataclasses import dataclass
from typing import Any, Mapping

from agentdev.entity.configs.base import BaseConfig, ConfigFieldSpec, optional_bool, optional_str, require_mapping


@dataclass
class HumanConfig(BaseConfig):
    description: str | None = None
    # The step after this gate costs money or cannot be undone (paid render, purchase, publishing, deleting).
    # An automatic answer (Lab) never approves such a gate: it is refused and recorded as skipped.
    paid: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None, *, path: str) -> "HumanConfig":
        if data is None:
            return cls(description=None, path=path)
        mapping = require_mapping(data, path)
        description = optional_str(mapping, "description", path)
        paid = bool(optional_bool(mapping, "paid", path, default=False))
        return cls(description=description, paid=paid, path=path)

    FIELD_SPECS = {
        "description": ConfigFieldSpec(
            name="description",
            display_name="Human Task Description",
            type_hint="text",
            required=False,
            description="Description of the task for human to complete",
        ),
        "paid": ConfigFieldSpec(
            name="paid",
            display_name="Paid / Irreversible Step",
            type_hint="bool",
            required=False,
            default=False,
            description="The step after this approval costs money or cannot be undone; "
            "automatic answers never approve it.",
        ),
    }
