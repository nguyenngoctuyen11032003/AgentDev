"""Lead-agent team configuration: the agents a lead (CTO / PM / CEO) may delegate to."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping

from agentdev.entity.configs.base import (
    BaseConfig,
    ConfigError,
    ConfigFieldSpec,
    extend_path,
    optional_bool,
    require_mapping,
)

DEFAULT_MAX_DELEGATIONS = 30
DEFAULT_MAX_REVIEW_ROUNDS = 3
DEFAULT_MAX_PARALLEL = 3


@dataclass
class AgentTeamConfig(BaseConfig):
    """Makes an agent a team lead.

    The lead talks to the user and decides at run time which members to call, how often and
    in what order (``delegate_task`` / ``delegate_parallel`` tools). Members are other agent nodes of the same workflow;
    with ``members`` empty, every agent node that has no edges ("staff" nodes) is a member.
    """

    enabled: bool = False
    members: List[str] = field(default_factory=list)
    plan_approval: bool = True
    max_delegations: int = DEFAULT_MAX_DELEGATIONS
    max_review_rounds: int = DEFAULT_MAX_REVIEW_ROUNDS
    max_parallel: int = DEFAULT_MAX_PARALLEL

    FIELD_SPECS = {
        "enabled": ConfigFieldSpec(
            name="enabled",
            display_name="Lead a team",
            type_hint="bool",
            required=False,
            default=False,
            description="This agent is the team lead: it talks to the user and delegates work to the members.",
        ),
        "members": ConfigFieldSpec(
            name="members",
            display_name="Members",
            type_hint="list[str]",
            required=False,
            description="Node IDs of the agents this lead may delegate to. Empty = every agent node with no edges.",
        ),
        "plan_approval": ConfigFieldSpec(
            name="plan_approval",
            display_name="Ask before building",
            type_hint="bool",
            required=False,
            default=True,
            description="For new work, present the plan (stack, architecture, tasks) and wait for the user's approval "
            "unless the user said to go ahead without it.",
        ),
        "max_delegations": ConfigFieldSpec(
            name="max_delegations",
            display_name="Max delegations per request",
            type_hint="int",
            required=False,
            default=DEFAULT_MAX_DELEGATIONS,
            description="Upper bound on delegate_task calls in one turn, to cap token use.",
            advance=True,
        ),
        "max_review_rounds": ConfigFieldSpec(
            name="max_review_rounds",
            display_name="Max fix/review rounds",
            type_hint="int",
            required=False,
            default=DEFAULT_MAX_REVIEW_ROUNDS,
            description="How many times failed work may go back for fixes before the lead reports to the user.",
            advance=True,
        ),
        "max_parallel": ConfigFieldSpec(
            name="max_parallel",
            display_name="Max members working at once",
            type_hint="int",
            required=False,
            default=DEFAULT_MAX_PARALLEL,
            description="How many members the lead may run at the same time for independent tasks "
            "(delegate_parallel), e.g. backend + frontend + data. 1 = members always work one after another.",
            advance=True,
        ),
    }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, path: str) -> "AgentTeamConfig":
        mapping = require_mapping(data, path)
        enabled = optional_bool(mapping, "enabled", path, default=False)
        plan_approval = optional_bool(mapping, "plan_approval", path, default=True)

        raw_members = mapping.get("members")
        members: List[str] = []
        if raw_members is not None:
            if not isinstance(raw_members, list):
                raise ConfigError("members must be a list of node IDs", extend_path(path, "members"))
            for idx, item in enumerate(raw_members):
                if not isinstance(item, str) or not item.strip():
                    raise ConfigError("member must be a non-empty node ID", extend_path(path, f"members[{idx}]"))
                if item.strip() not in members:
                    members.append(item.strip())

        def _positive_int(key: str, default: int) -> int:
            value = mapping.get(key)
            if value is None:
                return default
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ConfigError(f"{key} must be a positive integer", extend_path(path, key))
            return value

        return cls(
            enabled=bool(enabled),
            members=members,
            plan_approval=True if plan_approval is None else bool(plan_approval),
            max_delegations=_positive_int("max_delegations", DEFAULT_MAX_DELEGATIONS),
            max_review_rounds=_positive_int("max_review_rounds", DEFAULT_MAX_REVIEW_ROUNDS),
            max_parallel=_positive_int("max_parallel", DEFAULT_MAX_PARALLEL),
            path=path,
        )

    @classmethod
    def field_specs(cls) -> Dict[str, ConfigFieldSpec]:
        return super().field_specs()
