"""Agent node executor.

Responsible for running agent nodes, including
- memory retrieval
- thinking workflows
- agent invocation
- tool calling
"""

import asyncio
import base64
import contextvars
import copy
import json
import os
import threading
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from agentdev.connections import resolve_connection
from agentdev.entity.configs import Node
from agentdev.entity.configs.node.agent import AgentConfig, AgentRetryConfig
from agentdev.entity.enums import CallStage, AgentExecFlowStage, AgentInputMode
from agentdev.entity.messages import (
    AttachmentRef,
    FunctionCallOutputEvent,
    Message,
    MessageBlock,
    MessageRole,
    ToolCallPayload,
)
from agentdev.entity.tool_spec import ToolSpec
from agentdev.runtime.node.executor.base import NodeExecutor
from agentdev.runtime.node.agent.memory.memory_base import (
    MemoryContentSnapshot,
    MemoryRetrievalResult,
    MemoryWritePayload,
)
from agentdev.runtime.node.agent import ThinkingPayload
from agentdev.runtime.node.agent import ModelProvider, ProviderRegistry, ModelResponse
from agentdev.runtime.node.agent.skills import AgentSkillManager
from agentdev.runtime.node.agent.account_fallback import (
    account_label,
    default_model_for,
    get_fallback_state,
    is_exhaustion_error,
    is_quota_error,
    pick_fallback,
)
from agentdev.runtime.node.agent.providers._native import NativeRunContext
from agentdev.runtime.node.agent.team import (
    DELEGATE_PARALLEL_TOOL,
    DELEGATE_TOOL,
    MODEL_ERROR_PREFIX,
    PLAN_GATE_REFUSAL,
    PLAN_PENDING_KEY,
    SUBMIT_PLAN_TOOL,
    TEAM_TOOL_SOURCE,
    TeamDelegation,
    clip_middle,
    get_team_state,
    is_delegated_call,
    latest_user_message,
    newest_user_message,
    resolve_members,
    team_digest,
)
from agentdev.runtime.node.agent.interject import (
    INBOX_KEY,
    RunInbox,
    lead_injection,
    member_injection,
)
from agentdev.runtime.node.agent.providers.cli_cancel import CliCancelled, cli_cancel_scope, cli_idle_scope
from agentdev.runtime.node.agent.providers._native import describe_tool_failure
from agentdev.utils.code_execution import UNSAFE_CODE_EXECUTION_ENV, require_unsafe_code_execution
from agentdev.utils.exceptions import (
    SecurityError,
    ValidationError,
    WorkflowCancelledError,
    WorkflowExecutionError,
)
from agentdev.utils.workspace_paths import is_link, resolve_workspace_path, validate_path_component
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_random_exponential
from agentdev.runtime.node.agent.providers._cli_common import CliTimeoutError
from concurrent.futures import CancelledError as FutureCancelledError, ThreadPoolExecutor

# Extra attempts for a CLI call that ran into its timeout (see _execute_with_retry).
MAX_CLI_TIMEOUT_RETRIES = 1
LONG_CLI_CALL_SECONDS = 600  # a CLI timeout longer than this is not retried
# A native agent's failing built-in tool is shown in the chat only at this many failures in a row.
NATIVE_REPEATED_FAILURES = 3


# Guards lazy creation of the per-node state dicts below. Team leads run members from worker
# threads (delegate_parallel), so two threads may reach a lazy getter at the same time.
_NODE_STATE_LOCK = threading.Lock()

# The AgentDev checkout (<repo>/backend/agentdev/runtime/node/executor/this file): native agents never
# get it as their workspace unless the user opened it as the project folder.
AGENTDEV_INSTALL_ROOT = Path(__file__).resolve().parents[5]


MAX_ERROR_REASON_CHARS = 300

# Sent (with no tools offered) when the tool loop limit is hit and the last reply has no text for the user.
TOOL_LIMIT_STATUS_PROMPT = (
    "The tool call limit for this request has been reached, so no more tools can be used. "
    "Without calling any tool, give the user a concise status report: what has been done, what is still open, "
    "and what they could do next."
)
TOOL_LIMIT_SKIPPED_RESULT = "Not executed: the tool call limit for this request was reached."
# A tool result longer than this goes to the model clipped (start and end kept): one huge file or page
# would otherwise be re-read by every later model call of the loop.
def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


MAX_TOOL_RESULT_CHARS = _env_int("AGENTDEV_MAX_TOOL_RESULT_CHARS", 16_000)
# Inside one tool loop only the newest results stay in full; older ones are clipped to a short stub so
# every further model call does not resend them.
KEEP_RECENT_TOOL_RESULTS = _env_int("AGENTDEV_KEEP_RECENT_TOOL_RESULTS", 3)
OLD_TOOL_RESULT_CHARS = _env_int("AGENTDEV_OLD_TOOL_RESULT_CHARS", 1_500)
OLD_TOOL_RESULT_MARKER = "[older result trimmed; call the tool again if needed]"
# The same batch of tool calls (names and arguments) this many times in a row means the agent is stuck;
# the next identical batch is not run and the agent is told to change approach or answer.
MAX_IDENTICAL_TOOL_BATCHES = 3
REPEATED_TOOL_BATCH_RESULT = (
    "Not executed: you already made exactly this call {count} times in a row with the same result. Do not repeat "
    "it: use a different approach, or give your answer with what you have and say what is unresolved."
)

# The user equips an agent with skills (e.g. frontend design) so its work follows those standards.
# Treat them as the agent's professional playbook: load every skill that matches the task's domain
# before working, follow it, and check the result against it.
_SKILL_WORKFLOW = (
    "1. Before you start any real task (building, writing, designing, reviewing, analysing, planning), compare it "
    "with your skills. Skills under \"Loaded skills\" are already in these instructions. Every other skill whose "
    "domain matches the work you are about to do yourself (for "
    "example a frontend/UI skill for any UI, page, component or styling work) MUST be loaded first, all of them "
    "in one turn. Do not load skills for parts of the work you delegate (the member applies their own skills) or "
    "skills unrelated to the task: each loaded skill takes context for the rest of the task.\n"
    "2. Treat a loaded skill as your binding standard for that kind of work: follow its process, rules, "
    "conventions and checklists over your own habits. Your role and task description still set the scope; when "
    "they explicitly conflict with a skill, they win.\n"
    "3. Before you finish, check your result against your task description and each applied skill's rules and "
    "checklist, and fix what does not meet them.\n"
    "4. In your answer or report, name the skills you applied in one short line.\n"
    "Skip skills only for greetings, small talk and simple factual questions."
)
SKILL_USAGE_RULES = (
    "# Your skills (professional standards for your work)\n"
    "Load a skill with `activate_skill` (and `read_skill_file` for files it references). Never assume a skill's "
    "contents before loading it, and never claim to have used a skill you did not load.\n" + _SKILL_WORKFLOW
)
# Ticked skills that fit the preload budget go into the system prompt in full (see
# AgentSkillManager.preload): followed from the first call, no activate_skill round trip, prompt-cached.
LOADED_SKILLS_HEADING = (
    "# Loaded skills\n"
    "The user chose these skills for you; their full instructions follow (no need to load them). For work in "
    "their domain they are your binding working standards: follow them, and before finishing check your output "
    "against them."
)
# Every ticked skill is already preloaded (no on-demand catalog): nothing to compare and load first.
PRELOADED_SKILL_RULES = (
    "# Your skills (professional standards for your work)\n"
    "Your skills are loaded below. Follow them for work in their domain, check your result against them "
    "before you finish, and name the skills you applied in one short line. If a skill points to another file "
    "and you have a `read_skill_file` tool, use it to read that file. Skip skills for greetings, small talk and simple factual questions."
)
NATIVE_PRELOADED_SKILL_RULES = (
    "# Your skills (professional standards for your work)\n"
    "Your skills are loaded below (a skill's other files are in its folder, read-only). Follow them for work in "
    "their domain, check your result against them before you finish, and name the skills you applied in one "
    "short line. Skip skills for greetings, small talk and simple factual questions."
)
NATIVE_SKILL_USAGE_RULES = (
    "# Your skills (professional standards for your work)\n"
    "Load a skill by reading its SKILL.md file below (read-only reference; it may sit outside the project folder), "
    "plus any file it points to. Never assume a skill's contents before reading it.\n" + _SKILL_WORKFLOW
)


class ModelCallError(WorkflowExecutionError):
    """An agent's model call failed for good (after retries and account fallback)."""


def _short_error(exc: BaseException) -> str:
    """One line describing a model failure, without prompts or other payloads."""
    text = " ".join(str(exc).split()) or exc.__class__.__name__
    return text if len(text) <= MAX_ERROR_REASON_CHARS else text[: MAX_ERROR_REASON_CHARS - 1] + "…"


class _NodeToolContext(dict):
    """Tool ``_context`` for one node: a view of ``global_state`` with this node's ``node_id``.

    Writing ``global_state["node_id"]`` for the duration of a tool batch races when team members
    run in parallel, so each batch gets its own overlay. Other keys written by a tool still reach
    the shared ``global_state``.
    """

    def __init__(self, base: Dict[str, Any], node_id: str) -> None:
        super().__init__(base)
        dict.__setitem__(self, "node_id", node_id)
        self._base = base

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        if key != "node_id":
            self._base[key] = value

    def setdefault(self, key: str, default: Any = None) -> Any:
        if key not in self:
            self[key] = default
        return self[key]


class AgentNodeExecutor(NodeExecutor):
    """Executor that runs agent nodes."""

    def execute(self, node: Node, inputs: List[Message]) -> List[Message]:
        """Execute an agent node.

        Args:
            node: Agent node definition
            inputs: Input messages collected from upstream nodes

        Returns:
            Agent output messages
        """
        self._ensure_not_cancelled()
        if node.node_type != "agent":
            raise ValueError(f"Node {node.id} is not an agent node")

        base_config = node.as_config(AgentConfig)
        if not base_config:
            raise ValueError(f"Node {node.id} missing agent config")
        # Per-run copy: account binding and fallback switches must not change the node's saved config
        # (the user's chosen account and model stay as they were for the next run).
        agent_config = copy.copy(base_config)
        self._run_configs()[node.id] = agent_config
        provider: ModelProvider | None = None

        try:
            # Every agent runs on a signed-in account (see connections.autobind for older YAML).
            if not agent_config.connection:
                raise ValueError(
                    f"Agent node '{node.id}' has no account connection. "
                    "Sign in on the Connections page and pick the connection on this node."
                )
            # An account that ran out of quota earlier in this run is skipped straight away.
            fallback_state = get_fallback_state(self.context.global_state)
            replacement = fallback_state.replacement.get(agent_config.connection)
            if replacement and agent_config.connection in fallback_state.exhausted:
                self._switch_account(node, agent_config, replacement, notify=False)
            provider_class = self._bind_account(node, agent_config)

            input_data = self._inputs_to_text(inputs)
            input_payload = self._build_thinking_payload_from_inputs(inputs, input_data)
            memory_query_snapshot = self._build_memory_query_snapshot(inputs, input_data)
            input_mode = agent_config.input_mode or AgentInputMode.PROMPT
            external_tool_specs = self.tool_manager.get_tool_specs(agent_config.tooling)
            skill_manager = self._build_skill_manager(node, agent_config, external_tool_specs)
            team = self._build_team(node, agent_config, input_data)
            self._active_teams()[node.id] = team
            # Native mode: the vendor CLI's own agent works in the project folder; no AgentDev tools/skills.
            native = self._resolve_native_mode(node, agent_config, provider_class)
            native_skills: AgentSkillManager | None = None
            if native is not None:
                # The native CLI agent cannot call activate_skill: list the ticked skills' files instead.
                external_tool_specs, native_skills, skill_manager = [], skill_manager, None

            provider = provider_class(agent_config)
            client = provider.create_client()

            if input_mode is AgentInputMode.PROMPT:
                conversation = self._prepare_prompt_messages(node, input_data, skill_manager, native_skills)
            else:
                conversation = self._prepare_message_conversation(node, inputs, skill_manager, native_skills)
            call_options = self._prepare_call_options(node)
            tool_specs = self._merge_skill_tool_specs(external_tool_specs, skill_manager)
            if team is not None:
                existing = {spec.name for spec in tool_specs}
                tool_specs = tool_specs + [spec for spec in team.tool_specs() if spec.name not in existing]

            agent_invoker = self._build_agent_invoker(
                provider,
                client,
                call_options,
                tool_specs,
                node,
            )

            if agent_config.thinking:
                self._apply_pre_generation_thinking(
                    node,
                    conversation,
                    input_payload,
                    memory_query_snapshot,
                    AgentExecFlowStage.PRE_GEN_THINKING_STAGE,
                    agent_invoker,
                    input_mode,
                )

            self._apply_memory_retrieval(
                node,
                conversation,
                memory_query_snapshot,
                AgentExecFlowStage.GEN_STAGE,
                input_mode,
            )

            timeline = self._build_initial_timeline(conversation)
            response_obj = self._invoke_provider(
                provider,
                client,
                conversation,
                timeline,
                call_options,
                tool_specs,
                node,
                native=native,
            )

            if response_obj.has_tool_calls() or self._interjection_pending(node):
                response_message = self._handle_tool_calls(
                    node,
                    provider,
                    client,
                    conversation,
                    timeline,
                    call_options,
                    response_obj,
                    tool_specs,
                    skill_manager,
                )
            else:
                response_message = response_obj.message

            self._persist_message_attachments(response_message, node.id)

            final_message: Message | str = response_message

            # A submitted plan is the answer as written: no post-generation rewrite.
            if agent_config.thinking and not (team is not None and team.plan_submitted):
                gen_payload = self._build_thinking_payload_from_message(final_message, source="model_output")
                final_message = self._apply_post_generation_thinking(
                    node,
                    conversation,
                    memory_query_snapshot,
                    input_payload,
                    gen_payload,
                    AgentExecFlowStage.POST_GEN_THINKING_STAGE,
                    agent_invoker,
                    input_mode,
                )

            self._update_memory(node, input_data, inputs, final_message)

            if isinstance(final_message, Message):
                return [self._clone_with_source(final_message, node.id)]
            return [self._build_message(
                role=MessageRole.ASSISTANT,
                content=final_message,
                source=node.id,
            )]

        except (SecurityError, WorkflowCancelledError):
            raise
        except CliCancelled as exc:
            raise WorkflowCancelledError("Workflow execution cancelled") from exc
        except Exception as e:
            # Reached only after retries and account fallback (_invoke_provider) gave up.
            # An error is never passed on as if it were the agent's answer.
            traceback.print_exc()
            reason = _short_error(e)
            self.log_manager.error(f"[Node: {node.id}] Error calling model: {reason}", node_id=node.id)
            if is_delegated_call():
                # The lead gets a short, structured failure it can act on (retry, reassign, report).
                return [self._build_message(
                    role=MessageRole.ASSISTANT,
                    content=f"{MODEL_ERROR_PREFIX} {node.id} could not finish the task: the model call failed ({reason}).",
                    source=node.id,
                    metadata={"model_error": True, "error": reason},
                )]
            salvaged = self._team_failure_summary(node, reason)
            if salvaged is not None:
                return [salvaged]
            raise ModelCallError(
                f"Agent '{node.id}' could not get an answer from its model ({node.model_name}): {reason}",
                node_id=node.id,
                details={"model": node.model_name},
            ) from e
        finally:
            self._active_teams().pop(node.id, None)
            override = self._provider_overrides().pop(node.id, None)
            self._run_configs().pop(node.id, None)
            # CLI providers keep a working folder / resumable session for the run: release them now.
            for used in (provider, override[0] if override else None):
                close = getattr(used, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:  # cleanup is best effort
                        pass

    def _team_failure_summary(self, node: Node, reason: str) -> Message | None:
        """The top lead's model failed after its team did work: report that work instead of losing it."""
        team = self._active_teams().get(node.id)
        if team is None or is_delegated_call():
            return None
        digest = team_digest(team.state)
        if not digest:
            return None
        lines = [
            f"{MODEL_ERROR_PREFIX} {node.id} could not finish: the model call failed ({reason}).",
            "The team had already done this work:",
        ]
        for entry in digest:
            report = " ".join(str(entry.get("report") or "").split())
            lines.append(f"- {entry['member']}: {entry.get('task', '')}\n  Report: {report}")
        lines.append("Ask again to continue from here, or switch the lead to another account.")
        return self._build_message(
            role=MessageRole.ASSISTANT,
            content="\n".join(lines),
            source=node.id,
            metadata={"model_error": True, "error": reason, "partial_team_results": True},
        )

    def _prepare_prompt_messages(
        self,
        node: Node,
        input_data: str,
        skill_manager: AgentSkillManager | None,
        native_skills: AgentSkillManager | None = None,
    ) -> List[Message]:
        """Prepare the prompt-style message sequence."""
        messages: List[Message] = []

        system_prompt = self._build_system_prompt(node, skill_manager, native_skills)
        if system_prompt:
            messages.append(Message(role=MessageRole.SYSTEM, content=system_prompt))

        try:
            if isinstance(input_data, str):
                clean_input = input_data.encode("utf-8", errors="ignore").decode("utf-8")
            else:
                clean_input = str(input_data)
        except Exception as encoding_error:
            self.log_manager.error(f"[Node: {node.id}] Encoding error: {encoding_error}")
            clean_input = str(input_data)

        messages.append(Message(role=MessageRole.USER, content=clean_input))
        return messages

    def _prepare_message_conversation(
        self,
        node: Node,
        inputs: List[Message],
        skill_manager: AgentSkillManager | None,
        native_skills: AgentSkillManager | None = None,
    ) -> List[Message]:
        messages: List[Message] = []

        system_prompt = self._build_system_prompt(node, skill_manager, native_skills)
        if system_prompt:
            messages.append(Message(role=MessageRole.SYSTEM, content=system_prompt))

        normalized_inputs = self._coerce_inputs_to_messages(inputs)
        if normalized_inputs:
            messages.extend(normalized_inputs)
        else:
            messages.append(Message(role=MessageRole.USER, content=""))

        return messages

    def _prepare_call_options(self, node: Node) -> Dict[str, Any]:
        """Prepare model call options (excluding conversation messages)."""
        call_options: Dict[str, Any] = {}

        model = node.as_config(AgentConfig)
        if not model:
            raise ValueError(f"Node {node.id} missing model config")

        if model.params:
            call_options.update(model.params)

        # call_options.setdefault("temperature", 0.7)
        # call_options.setdefault("max_tokens", 4096)
        return call_options

    def _build_skill_manager(
        self,
        node: Node,
        agent_config: AgentConfig,
        external_tool_specs: List[ToolSpec],
    ) -> AgentSkillManager | None:
        skills_config = agent_config.skills
        if not skills_config or not skills_config.enabled:
            return None

        manager = AgentSkillManager(
            allow=skills_config.allow,
            available_tool_names=[spec.name for spec in external_tool_specs],
            warning_reporter=lambda message: self.log_manager.warning(message, node_id=node.id),
        )
        return manager

    def _build_system_prompt(
        self,
        node: Node,
        skill_manager: AgentSkillManager | None,
        native_skills: AgentSkillManager | None = None,
    ) -> str | None:
        parts: List[str] = []
        profile = self._agent_profile_section(node)
        if profile:
            parts.append(profile)

        # Prompt caching is prefix based: static content first, the small per-message block (plan rule,
        # language) last, so a changed message only invalidates the tail.
        team = self._active_teams().get(node.id)
        team_per_turn = ""
        if team is not None:
            team_static, team_per_turn = team.system_prompt_parts()
            parts.append(team_static)

        if skill_manager is not None:
            skill_manager.preload()
            loaded = skill_manager.build_preloaded_skills_section()
            skills_xml = skill_manager.build_available_skills_xml()
            if skills_xml or loaded:
                usage = SKILL_USAGE_RULES if skills_xml else PRELOADED_SKILL_RULES
                parts.append("\n".join(part for part in (usage, skills_xml) if part))
                if loaded:
                    parts.append(LOADED_SKILLS_HEADING + "\n\n" + loaded)
            else:
                warning_lines = skill_manager.discovery_warnings()
                warning_text = "\n".join(f"- {warning}" for warning in warning_lines[:5])
                parts.append(
                    "\n".join(
                        [
                            "Agent Skills are enabled for this node, but no compatible skills are currently available.",
                            "Do not claim to use or load any skill unless it appears in <available_skills>.",
                            warning_text,
                        ]
                    ).strip()
                )

        if native_skills is not None:
            native_skills.preload()
            loaded = native_skills.build_preloaded_skills_section(with_paths=True)
            listing = native_skills.build_skill_file_listing()
            if listing or loaded:
                native_usage = NATIVE_SKILL_USAGE_RULES if listing else NATIVE_PRELOADED_SKILL_RULES
                parts.append((native_usage + "\n" + listing).rstrip())
                if loaded:
                    parts.append(LOADED_SKILLS_HEADING + "\n\n" + loaded)

        rules = self._response_rules_section()
        if rules:
            parts.append(rules)

        if team_per_turn:
            parts.append(team_per_turn)

        if not parts:
            return None
        return "\n\n".join(part for part in parts if part)

    @staticmethod
    def _agent_profile_section(node: Node) -> str:
        """The agent's own brief: "Vai trò và nhiệm vụ" (role) and "Mô tả nhiệm vụ" (description).

        Both are written by the user to define how this agent works, so both reach the model as
        binding instructions, not only the role.
        """
        role = (node.role or "").strip()
        description = (node.description or "").strip()
        if not role and not description:
            return ""
        if role and not description:
            return role  # unchanged prompt for agents that only set a role
        sections = ["# Your role and responsibilities", role or "(see the task description below)"]
        if description and description != role:
            sections += [
                "# Your task description and working rules",
                "Set by the user for this agent. Follow it on every task: it defines your scope, how you work "
                "and what a correct result looks like.",
                description,
            ]
        return "\n\n".join(sections)

    @staticmethod
    def _response_rules_section() -> str:
        """Answer-quality rules for agents that talk to a person.

        Members briefed by a lead get MEMBER_PROTOCOL in their brief instead: they report to the
        lead, so the user-facing rules (language of the user's message, length) do not apply.
        """
        from agentdev.runtime.node.agent.team import USER_RESPONSE_RULES, is_delegated_call

        return "" if is_delegated_call() else USER_RESPONSE_RULES

    def _merge_skill_tool_specs(
        self,
        tool_specs: List[ToolSpec],
        skill_manager: AgentSkillManager | None,
    ) -> List[ToolSpec]:
        if skill_manager is None:
            return tool_specs

        skill_manager.preload()
        if not skill_manager.needs_skill_tool_specs():
            return tool_specs

        merged = list(tool_specs)
        existing_names = {spec.name for spec in merged}
        for spec in skill_manager.build_tool_specs():
            if spec.name in existing_names:
                raise ValueError(f"Tool name '{spec.name}' conflicts with a built-in skill tool")
            existing_names.add(spec.name)
            merged.append(spec)
        return merged

    def _build_agent_invoker(
        self,
        provider: ModelProvider,
        client: Any,
        base_call_options: Dict[str, Any],
        default_tool_specs: List[ToolSpec],
        node: Node,
    ) -> Callable[[List[Message]], Message]:
        """Create a callable that other components can use to invoke the model."""

        def invoke(
            conversation: List[Message],
            *,
            tools: Optional[List[ToolSpec]] = None,
            **overrides: Any,
        ) -> Message:
            call_options = dict(base_call_options)
            call_options.update(overrides)
            timeline = self._build_initial_timeline(conversation)
            response = self._invoke_provider(
                provider,
                client,
                conversation,
                timeline,
                call_options,
                tools if tools is not None else default_tool_specs,
                node,
            )
            return response.message

        return invoke

    def _invoke_provider(
        self,
        provider: ModelProvider,
        client: Any,
        conversation: List[Message],
        timeline: List[Any],
        call_options: Dict[str, Any],
        tool_specs: List[ToolSpec] | None,
        node: Node,
        *,
        native: NativeRunContext | None = None,
    ) -> ModelResponse:
        """Invoke provider with logging + token tracking.

        ``native`` (main generation call of a native-mode node only) makes a CLI provider run its own
        agent in the project folder; a fallback account whose provider lacks native support runs normally.
        """
        # Token usage is attributed through provider.config.node_id (see _bind_account), not a shared
        # "current node" attribute on the tracker, which parallel team members would overwrite.
        self._ensure_not_cancelled()

        agent_config = self._run_config(node)
        retry_policy = self._resolve_retry_policy(node, agent_config)
        cancel_event = getattr(self.context, "cancel_event", None)

        def _call_provider() -> ModelResponse:
            self._ensure_not_cancelled()
            active_provider, active_client = self._provider_overrides().get(node.id, (provider, client))
            extra = {"native": native} if native is not None and getattr(active_provider, "supports_native_mode", False) else {}
            try:
                # Lets a CLI provider kill its subprocess as soon as the run is stopped.
                with cli_cancel_scope(cancel_event), cli_idle_scope(self._idle_reporter(node)):
                    return active_provider.call_model(
                        active_client,
                        conversation=conversation,
                        timeline=timeline,
                        tool_specs=tool_specs or None,
                        **call_options,
                        **extra,
                    )
            except WorkflowCancelledError:
                raise
            except CliCancelled as exc:
                raise WorkflowCancelledError("Workflow execution cancelled") from exc
            except Exception as exc:
                # A call that failed because the run was stopped is a cancellation, not a model error.
                if cancel_event is not None and cancel_event.is_set():
                    raise WorkflowCancelledError("Workflow execution cancelled") from exc
                raise

        last_input = ''.join(msg.text_content() for msg in conversation) if conversation else ""
        self._record_model_call(node, last_input, None, CallStage.BEFORE)
        try:
            response = self._execute_with_retry(node, retry_policy, _call_provider)
        except WorkflowCancelledError:
            raise
        except Exception as first_exc:
            # Claude -> Codex -> Gemini ...: keep switching while accounts run out and another one is left.
            exc: BaseException = first_exc
            while True:
                if not is_exhaustion_error(exc) or not self._fail_over(node, agent_config, exc):
                    raise exc
                try:
                    response = self._execute_with_retry(node, retry_policy, _call_provider)
                    break
                except WorkflowCancelledError:
                    raise
                except Exception as next_exc:
                    exc = next_exc
        self.log_manager.debug(response.str_raw_response())
        self._record_model_call(node, last_input, response, CallStage.AFTER)
        return response

    def _record_model_call(
        self,
        node: Node,
        input_payload: str,
        response: ModelResponse | None,
        stage: CallStage = CallStage.AFTER,
    ) -> None:
        """Record model invocation to the log manager."""
        response_text = response.message.text_content() if response else None
        call_details = {"has_tool_calls": response.has_tool_calls()} if response else {}
        self.log_manager.record_model_call(
            node.id,
            node.model_name,
            input_payload,
            response_text,
            call_details,
            stage,
        )

    def _idle_reporter(self, node: Node):
        """Idle-watchdog listener: tells the UI (INFO log, ``event: cli_idle``) an agent has been silent for long."""

        def report(seconds: float, busy: bool, killed: bool) -> None:
            minutes = max(1, round(seconds / 60))
            if killed:
                message = f"[Node: {node.id}] No output for {minutes} min: stopped the stuck CLI and retrying."
            elif busy:
                message = f"[Node: {node.id}] A tool has been running for {minutes}+ min."
            else:
                message = f"[Node: {node.id}] Still thinking ({minutes}+ min without output)."
            self.log_manager.info(
                message,
                node_id=node.id,
                details={"event": "cli_idle", "idle_seconds": int(seconds), "busy": busy, "killed": killed},
            )

        return report

    def _execute_with_retry(
        self,
        node: Node,
        retry_config: AgentRetryConfig | None,
        func: Callable[[], ModelResponse],
    ) -> ModelResponse:
        if not retry_config or not retry_config.is_active:
            return func()

        wait = wait_random_exponential(
            min=retry_config.min_wait_seconds,
            max=retry_config.max_wait_seconds,
        )
        # Quota errors are not retried on the same account: _invoke_provider switches account instead.
        # A CLI call that hits its timeout already cost minutes: retry it once, not max_attempts times
        # (5 x 300 s would leave the user waiting ~25 minutes for an error).
        timeouts_seen = {"count": 0}

        def _should_retry(exc: BaseException) -> bool:
            if isinstance(exc, (WorkflowCancelledError, CliCancelled)):
                return False
            if is_exhaustion_error(exc) or not retry_config.should_retry(exc):
                return False
            if isinstance(exc, CliTimeoutError):
                # A call that already ran for many minutes (a native agent: up to 30) is not redone from
                # scratch: its files are on disk and a retry would double the wait and the spend.
                if (getattr(exc, "timeout_seconds", 0) or 0) > LONG_CLI_CALL_SECONDS:
                    return False
                timeouts_seen["count"] += 1
                return timeouts_seen["count"] <= MAX_CLI_TIMEOUT_RETRIES
            return True

        retry_condition = retry_if_exception(_should_retry)

        def _before_sleep(retry_state) -> None:
            exc = retry_state.outcome.exception()
            if exc is None:
                return
            attempt = retry_state.attempt_number
            details = {
                "attempt": attempt,
                "max_attempts": retry_config.max_attempts,
                "exception": exc.__class__.__name__,
            }
            self.log_manager.warning(
                f"[Node: {node.id}] Model call attempt {attempt} failed: {exc}",
                node_id=node.id,
                details=details,
            )

        retrier = Retrying(
            stop=stop_after_attempt(retry_config.max_attempts),
            wait=wait,
            retry=retry_condition,
            before_sleep=_before_sleep,
            reraise=True,
        )
        return retrier(func)

    def _resolve_retry_policy(
        self,
        node: Node,
        agent_config: AgentConfig | None,
    ) -> AgentRetryConfig | None:
        """Ensure every agent node has a retry policy even if config omits it."""
        if not agent_config:
            return None
        if agent_config.retry is not None:
            return agent_config.retry

        base_path = getattr(agent_config, "path", None) or getattr(node, "path", None) or "<runtime>"
        retry_path = f"{base_path}.retry" if base_path else "retry"
        default_retry = AgentRetryConfig(path=retry_path)
        agent_config.retry = default_retry
        return default_retry

    def _apply_pre_generation_thinking(
        self,
        node: Node,
        conversation: List[Message],
        input_payload: ThinkingPayload,
        query_snapshot: MemoryContentSnapshot,
        stage: AgentExecFlowStage,
        agent_invoker: Callable[[List[Message]], Message],
        input_mode: AgentInputMode,
    ) -> None:
        """Apply pre-generation thinking."""
        self._ensure_not_cancelled()
        thinking_manager = self.context.get_thinking_manager(node.id)
        if not thinking_manager or not conversation:
            return

        model = node.as_config(AgentConfig)

        with self.log_manager.thinking_timer(node.id, stage.value):
            retrieved_memory = self._retrieve_memory(node, query_snapshot, stage)
            memory_payload = self._memory_result_to_thinking_payload(retrieved_memory)
            thinking_result = thinking_manager.think(
                agent_invoker=agent_invoker,
                input_payload=input_payload,
                agent_role=node.role or "",
                memory=memory_payload,
                gen_payload=None,
            )

        mode_value = model.thinking.type if model and model.thinking else "unknown"
        self.log_manager.record_thinking_process(
            node.id,
            mode_value,
            thinking_result if isinstance(thinking_result, str) else "[message]",
            stage.value,
            {"has_memory": bool(retrieved_memory and retrieved_memory.items)},
        )

        if input_mode is AgentInputMode.MESSAGES:
            if isinstance(thinking_result, Message):
                self._persist_message_attachments(thinking_result, node.id)
                conversation.append(self._clone_with_source(thinking_result, node.id))
            else:
                self._append_user_message(conversation, thinking_result, node_id=node.id)
        else:
            content = thinking_result if isinstance(thinking_result, str) else thinking_result.text_content()
            conversation[-1] = conversation[-1].with_content(content)

    def _apply_memory_retrieval(
        self,
        node: Node,
        conversation: List[Message],
        query_snapshot: MemoryContentSnapshot,
        stage: AgentExecFlowStage,
        input_mode: AgentInputMode,
    ) -> None:
        """Apply memory retrieval side effects."""
        self._ensure_not_cancelled()
        if not conversation:
            return

        retrieved_memory = self._retrieve_memory(node, query_snapshot, stage)

        if retrieved_memory and retrieved_memory.formatted_text:
            if input_mode is AgentInputMode.MESSAGES:
                self._insert_memory_message(conversation, retrieved_memory.formatted_text, node_id=node.id)
            else:
                last_message = conversation[-1]
                merged_content = f"{retrieved_memory.formatted_text}\n\n{last_message.text_content()}"
                conversation[-1] = last_message.with_content(merged_content)

    def _retrieve_memory(
        self,
        node: Node,
        query_snapshot: MemoryContentSnapshot,
        stage: AgentExecFlowStage
    ) -> MemoryRetrievalResult | None:
        """Retrieve memory for the node."""
        memory_manager = self.context.get_memory_manager(node.id)
        if not memory_manager:
            return None

        with self.log_manager.memory_timer(node.id, "RETRIEVE", stage.value):
            retrieved_memory = memory_manager.retrieve(
                agent_role=node.role if node.role else "",
                query=query_snapshot,
                current_stage=stage,
            )

        preview_text = retrieved_memory.formatted_text if retrieved_memory else ""
        details = {
            "stage": stage.value,
            "item_count": len(retrieved_memory.items) if retrieved_memory else 0,
            "attachment_count": len(retrieved_memory.attachment_overview()) if retrieved_memory else 0,
        }

        self.log_manager.record_memory_operation(
            node.id,
            "RETRIEVE",
            stage.value,
            preview_text,
            details,
        )

        return retrieved_memory


    def _handle_tool_calls(
        self,
        node: Node,
        provider: ModelProvider,
        client: Any,
        conversation: List[Message],
        timeline: List[Any],
        call_options: Dict[str, Any],
        initial_response: ModelResponse,
        tool_specs: List[ToolSpec],
        skill_manager: AgentSkillManager | None,
    ) -> Message:
        """Handle tool calls until completion or until the loop limit is reached."""
        assistant_message = initial_response.message
        trace_messages: List[Message] = []
        loop_limit = self._get_tool_loop_limit(node)
        iteration = 0
        last_signature: str | None = None
        repeats = 0
        tool_loop_start = len(conversation)

        while True:
            self._ensure_not_cancelled()
            cloned_assistant = self._clone_with_source(assistant_message, node.id)
            conversation.append(cloned_assistant)
            trace_messages.append(cloned_assistant)

            if not assistant_message.tool_calls:
                # A note the user wrote while this answer was being generated: answer it before finishing
                if self._apply_interjections(node, conversation):
                    assistant_message = self._invoke_provider(
                        provider, client, conversation, timeline, call_options, tool_specs, node
                    ).message
                    continue
                return self._finalize_tool_trace(assistant_message, trace_messages, True, node.id)

            if iteration >= loop_limit:
                self.log_manager.warning(
                    f"[Node: {node.id}] Tool call limit {loop_limit} reached, returning last assistant response"
                )
                if not assistant_message.text_content().strip():
                    report = self._tool_limit_status_report(
                        node, provider, client, conversation, timeline, call_options, assistant_message
                    )
                    if report is not None:
                        trace_messages.append(self._clone_with_source(report, node.id))
                        return self._finalize_tool_trace(report, trace_messages, False, node.id)
                return self._finalize_tool_trace(assistant_message, trace_messages, False, node.id)

            iteration += 1

            signature = self._tool_batch_signature(assistant_message.tool_calls)
            repeats = repeats + 1 if signature == last_signature else 1
            last_signature = signature
            if repeats > MAX_IDENTICAL_TOOL_BATCHES:
                tool_call_messages, tool_events = self._refuse_repeated_batch(node, assistant_message.tool_calls, repeats - 1)
            else:
                tool_call_messages, tool_events = self._execute_tool_batch(
                    node,
                    assistant_message.tool_calls,
                    tool_specs,
                    skill_manager,
                )
            latest_batch_start = len(conversation)
            conversation.extend(tool_call_messages)
            timeline.extend(tool_events)
            trace_messages.extend(self._clone_with_source(msg, node.id) for msg in tool_call_messages)

            plan_message = self._submitted_plan_answer(node)
            if plan_message is not None:
                # Plan gate: the lead's turn ends here; the plan is the answer, no further model call.
                trace_messages.append(self._clone_with_source(plan_message, node.id))
                return self._finalize_tool_trace(plan_message, trace_messages, True, node.id)

            # Notes from the user sent meanwhile join the conversation before the next model call
            self._apply_interjections(node, conversation)
            # Only results the model already saw (earlier batches) may be clipped. A provider resuming
            # one CLI session keeps them anyway; clipping would break its resume and re-send everything.
            keeps_history = getattr(provider, "keeps_tool_history", None)
            if not (callable(keeps_history) and keeps_history(tool_specs)):
                self._compact_old_tool_results(conversation, tool_loop_start, latest_batch_start)

            follow_up_response = self._invoke_provider(
                provider,
                client,
                conversation,
                timeline,
                call_options,
                tool_specs,
                node,
            )
            assistant_message = follow_up_response.message

    @staticmethod
    def _compact_old_tool_results(conversation: List[Message], start: int, end: int | None = None) -> None:
        """Clip text tool results of this loop older than the newest KEEP_RECENT_TOOL_RESULTS ones.

        Only results before ``end`` (the start of the latest, still unseen batch) are eligible, so a
        large parallel batch is never clipped before the model has read it.
        Replaces list entries (the trace keeps its own full clones); only plain-text results are touched.
        """
        limit = len(conversation) if end is None else min(end, len(conversation))
        indexes = [
            i for i in range(start, len(conversation))
            if conversation[i].role == MessageRole.TOOL
        ]
        if len(indexes) <= KEEP_RECENT_TOOL_RESULTS:
            return
        old = indexes[:-KEEP_RECENT_TOOL_RESULTS] if KEEP_RECENT_TOOL_RESULTS else indexes
        for i in (i for i in old if i < limit):
            msg = conversation[i]
            content = msg.content
            if not isinstance(content, str) or content.endswith(OLD_TOOL_RESULT_MARKER):
                continue
            # A loaded skill body is the agent's instructions, never trimmed.
            if (msg.metadata or {}).get("tool_name") in ("activate_skill", "read_skill_file"):
                continue
            if len(content) <= OLD_TOOL_RESULT_CHARS:
                continue
            clipped = msg.clone()
            clipped.content = content[:OLD_TOOL_RESULT_CHARS] + "\n" + OLD_TOOL_RESULT_MARKER
            conversation[i] = clipped

    def _tool_batch_signature(self, tool_calls: List[ToolCallPayload]) -> str:
        """Names and arguments of a batch of tool calls, to spot an agent repeating itself."""
        return json.dumps(
            [[call.function_name, self._parse_tool_call_arguments(call.arguments)] for call in tool_calls],
            sort_keys=True,
            default=str,
        )

    def _refuse_repeated_batch(
        self, node: Node, tool_calls: List[ToolCallPayload], count: int
    ) -> tuple[List[Message], List[Any]]:
        """Answer a batch the agent has already made ``count`` times in a row without running it."""
        text = REPEATED_TOOL_BATCH_RESULT.format(count=count)
        self.log_manager.warning(
            f"[Node: {node.id}] Same tool calls {count} times in a row, not running them again", node_id=node.id
        )
        messages: List[Message] = []
        events: List[Any] = []
        for call in tool_calls:
            messages.append(
                Message(
                    role=MessageRole.TOOL,
                    content=text,
                    tool_call_id=call.id,
                    metadata={"tool_name": call.function_name, "source": node.id},
                )
            )
            events.append(
                FunctionCallOutputEvent(
                    call_id=call.id or call.function_name or "tool_call",
                    function_name=call.function_name,
                    output_text=f"error: {text}",
                )
            )
        return messages, events

    def _interjection_pending(self, node: Node) -> bool:
        """The lead (a node nobody delegated to) has a user note it has not seen yet."""
        if is_delegated_call():
            return False
        inbox = self.context.global_state.get(INBOX_KEY)
        return isinstance(inbox, RunInbox) and inbox.has_pending()

    def _apply_interjections(self, node: Node, conversation: List[Message]) -> bool:
        """Put the user's mid-run notes into ``conversation`` as the next user message; True when any was added.

        The lead takes them (and the user is told so); a running member only gets a read-only heads-up.
        """
        inbox = self.context.global_state.get(INBOX_KEY)
        if not isinstance(inbox, RunInbox):
            return False
        if is_delegated_call():
            notes = inbox.take_for_member(node.id)
            text = member_injection(notes) if notes else ""
        else:
            notes = inbox.take_for_lead(node.id)
            text = lead_injection(notes) if notes else ""
        if not text:
            return False
        self._append_user_message(conversation, text, node_id=node.id)
        return True

    def _submitted_plan_answer(self, node: Node) -> Message | None:
        """The plan as the lead's final answer once it called ``submit_plan`` (None otherwise)."""
        team = self._active_teams().get(node.id)
        if team is None or not team.plan_submitted:
            return None
        plan = dict(team.plan or {})
        self.context.global_state[PLAN_PENDING_KEY] = plan
        return Message(
            role=MessageRole.ASSISTANT,
            content=plan.get("plan", ""),
            metadata={"source": node.id, "kind": "plan", "plan_summary": plan.get("summary", "")},
        )

    def _tool_limit_status_report(
        self,
        node: Node,
        provider: ModelProvider,
        client: Any,
        conversation: List[Message],
        timeline: List[Any],
        call_options: Dict[str, Any],
        assistant_message: Message,
    ) -> Message | None:
        """One last call with no tools so the user gets a status report instead of an empty answer."""
        # Answer the pending tool calls first: API providers reject a tool call without a result.
        for call in assistant_message.tool_calls or []:
            conversation.append(
                Message(
                    role=MessageRole.TOOL,
                    content=TOOL_LIMIT_SKIPPED_RESULT,
                    tool_call_id=call.id,
                    metadata={"tool_name": call.function_name, "source": node.id},
                )
            )
            timeline.append(
                FunctionCallOutputEvent(
                    call_id=call.id or call.function_name or "tool_call",
                    function_name=call.function_name,
                    output_text=TOOL_LIMIT_SKIPPED_RESULT,
                )
            )
        prompt = Message(role=MessageRole.USER, content=TOOL_LIMIT_STATUS_PROMPT, metadata={"source": node.id})
        conversation.append(prompt)
        timeline.append(prompt)
        try:
            response = self._invoke_provider(provider, client, conversation, timeline, call_options, [], node)
        except WorkflowCancelledError:
            raise
        except Exception as exc:
            self.log_manager.warning(
                f"[Node: {node.id}] Status report after the tool call limit failed: {_short_error(exc)}",
                node_id=node.id,
            )
            return None
        message = response.message
        if message.tool_calls or not message.text_content().strip():
            text = message.text_content().strip()
            if not text:
                return None
            message = Message(role=MessageRole.ASSISTANT, content=text, metadata=dict(message.metadata or {}))
        return message

    def _parallel_delegations(
        self,
        node: Node,
        tool_calls: List[ToolCallPayload],
        spec_map: Dict[str, ToolSpec],
    ) -> Dict[int, tuple]:
        """Run 2+ ``delegate_task`` calls of one reply at the same time (as ``delegate_parallel`` does).

        Returns ``{index: (tool message, events)}``; results keep the order of the calls. Empty when the
        team runs one member at a time (``max_parallel`` 1) or there is only one delegation.
        """
        team = self._active_teams().get(node.id)
        if team is None:
            return {}
        indices = [
            idx
            for idx, call in enumerate(tool_calls)
            if call.function_name == DELEGATE_TOOL
            and (spec_map.get(call.function_name) is not None)
            and spec_map[call.function_name].metadata.get("source") == TEAM_TOOL_SOURCE
        ]
        workers = min(int(getattr(team, "max_parallel", 1) or 1), len(indices))
        if len(indices) < 2 or workers < 2:
            return {}
        cancel_event = getattr(self.context, "cancel_event", None)

        def run_one(idx: int) -> tuple:
            # contextvars do not cross threads: each worker enters the cancel scope itself.
            with cli_cancel_scope(cancel_event):
                call = tool_calls[idx]
                events: List[Any] = []
                arguments = self._parse_tool_call_arguments(call.arguments)
                message = self._run_team_tool(node, call, call.function_name, arguments, events)
                return message, events

        results: Dict[int, tuple] = {}
        cancelled: Optional[BaseException] = None
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"lead-{node.id}") as pool:
            # A fresh context copy per worker: it keeps the delegation depth of this call chain.
            futures = [(idx, pool.submit(contextvars.copy_context().run, run_one, idx)) for idx in indices]
            for idx, future in futures:
                try:
                    results[idx] = future.result()
                except (WorkflowCancelledError, CliCancelled) as exc:
                    cancelled = cancelled or exc
                    for _, pending in futures:
                        pending.cancel()
                except FutureCancelledError:
                    pass
        if cancelled is not None:
            if isinstance(cancelled, WorkflowCancelledError):
                raise cancelled
            raise WorkflowCancelledError("Workflow execution cancelled") from cancelled
        return results

    def _execute_tool_batch(
        self,
        node: Node,
        tool_calls: List[ToolCallPayload],
        tool_specs: List[ToolSpec],
        skill_manager: AgentSkillManager | None,
    ) -> tuple[List[Message], List[Any]]:
        """Execute a batch of tool calls and return conversation + timeline events."""
        messages: List[Message] = []
        events: List[Any] = []
        model = node.as_config(AgentConfig)

        # Build map for fast lookup
        spec_map = {spec.name: spec for spec in tool_specs}
        configs = model.tooling if model else []
        # Skill instructions go after every tool result of the batch (a tool result must directly
        # follow its call), as the last message of the conversation.
        skill_followups: List[Message] = []
        # Plan gate: a reply that submits a plan runs no team work at all (not even calls before it).
        plan_in_batch = any(
            call.function_name == SUBMIT_PLAN_TOOL
            and (spec_map.get(call.function_name) is not None)
            and spec_map[call.function_name].metadata.get("source") == TEAM_TOOL_SOURCE
            for call in tool_calls
        )
        delegated = {} if plan_in_batch else self._parallel_delegations(node, tool_calls, spec_map)

        with self._node_tool_context(node) as tool_context:
            for call_index, tool_call in enumerate(tool_calls):
                self._ensure_not_cancelled()
                tool_name = tool_call.function_name
                arguments = self._parse_tool_call_arguments(tool_call.arguments)

                # Resolve tool config
                spec = spec_map.get(tool_name)
                tool_config = None
                execution_name = tool_name

                if spec:
                    idx = spec.metadata.get("_config_index")
                    if idx is not None and 0 <= idx < len(configs):
                        tool_config = configs[idx]
                    # Use original name if prefixed
                    execution_name = spec.metadata.get("original_name", tool_name)

                if spec and spec.metadata.get("source") == TEAM_TOOL_SOURCE:
                    if plan_in_batch and tool_name in (DELEGATE_TOOL, DELEGATE_PARALLEL_TOOL):
                        messages.append(self._refuse_team_tool(node, tool_call, tool_name, events))
                        continue
                    if call_index in delegated:
                        team_message, team_events = delegated[call_index]
                        messages.append(team_message)
                        events.extend(team_events)
                        continue
                    messages.append(self._run_team_tool(node, tool_call, tool_name, arguments, events))
                    continue

                if spec and spec.metadata.get("source") == "agent_skill_internal":
                    try:
                        self.log_manager.record_tool_call(
                            node.id,
                            tool_name,
                            None,
                            None,
                            {"arguments": arguments},
                            CallStage.BEFORE,
                        )
                        with self.log_manager.tool_timer(node.id, tool_name):
                            raw_result = self._execute_skill_tool(tool_name, arguments, skill_manager)
                        result, followup = self._skill_tool_result(tool_name, raw_result, node.id)

                        tool_message = self._build_tool_message(
                            result,
                            tool_call,
                            node_id=node.id,
                            tool_name=tool_name,
                        )
                        events.append(self._build_function_call_output_event(tool_call, result))
                        if followup is not None:
                            skill_followups.append(followup)
                        self.log_manager.record_tool_call(
                            node.id,
                            tool_name,
                            True,
                            self._serialize_tool_result(result),
                            {"arguments": arguments},
                            CallStage.AFTER,
                        )
                    except WorkflowCancelledError:
                        raise
                    except CliCancelled as exc:
                        raise WorkflowCancelledError("Workflow execution cancelled") from exc
                    except Exception as exc:
                        self.log_manager.record_tool_call(
                            node.id,
                            tool_name,
                            False,
                            None,
                            {"error": str(exc), "arguments": arguments},
                            CallStage.AFTER,
                        )
                        tool_message = Message(
                            role=MessageRole.TOOL,
                            content=f"Tool {tool_name} error: {exc}",
                            tool_call_id=tool_call.id,
                            metadata={"tool_name": tool_name, "source": node.id},
                        )
                        events.append(
                            FunctionCallOutputEvent(
                                call_id=tool_call.id or tool_call.function_name or "tool_call",
                                function_name=tool_call.function_name,
                                output_text=f"error: {exc}",
                            )
                        )

                    messages.append(tool_message)
                    continue

                # Only allowed-tools entries naming tools of this agent are enforced; the rest
                # (Claude Code syntax such as "Bash(npx x *)", unknown names) are advisory. With several
                # skills active, their lists combine (see allowed_tools_for_active).
                enforced_tools = skill_manager.allowed_tools_for_active() if skill_manager is not None else ()
                if enforced_tools and execution_name not in enforced_tools:
                    error_msg = (
                        f"Tool '{tool_name}' is not allowed by the active skills. "
                        f"Allowed tools: {list(enforced_tools)}"
                    )
                    self.log_manager.record_tool_call(
                        node.id,
                        tool_name,
                        False,
                        None,
                        {"error": error_msg, "arguments": arguments},
                        CallStage.AFTER,
                    )
                    tool_message = Message(
                        role=MessageRole.TOOL,
                        content=f"Error: {error_msg}",
                        tool_call_id=tool_call.id,
                        metadata={"tool_name": tool_name, "source": node.id},
                    )
                    events.append(
                        FunctionCallOutputEvent(
                            call_id=tool_call.id or tool_call.function_name or "tool_call",
                            function_name=tool_call.function_name,
                            output_text=f"error: {error_msg}",
                        )
                    )
                    messages.append(tool_message)
                    continue

                if not tool_config:
                     # Fallback check: if we have 1 config, maybe it's that one? 
                     # But strict routing is safer. If spec not found, it's a hallucination or error.
                     # We proceed and let tool_manager raise error or handle it.
                     # But execute_tool requires tool_config. 

                     # Construct a helpful error message
                     error_msg = f"Tool '{tool_name}' configuration not found."
                     self.log_manager.record_tool_call(
                        node.id,
                        tool_name,
                        False,
                        None,
                        {"error": error_msg, "arguments": arguments},
                        CallStage.AFTER,
                    )
                     tool_message = Message(
                        role=MessageRole.TOOL,
                        content=f"Error: {error_msg}",
                        tool_call_id=tool_call.id,
                        metadata={"tool_name": tool_name, "source": node.id},
                    )
                     events.append(
                        FunctionCallOutputEvent(
                            call_id=tool_call.id or tool_call.function_name or "tool_call",
                            function_name=tool_call.function_name,
                            output_text=f"error: {error_msg}",
                        )
                    )
                     messages.append(tool_message)
                     continue

                try:
                    self.log_manager.record_tool_call(
                        node.id,
                        tool_name,
                        None,
                        None,
                        {"arguments": arguments},
                        CallStage.BEFORE,
                    )
                    with self.log_manager.tool_timer(node.id, tool_name):
                        result = asyncio.run(
                            self.tool_manager.execute_tool(
                                execution_name,
                                arguments,
                                tool_config,
                                tool_context=tool_context,
                            )
                        )

                    tool_message = self._build_tool_message(
                        result,
                        tool_call,
                        node_id=node.id,
                        tool_name=tool_name,
                    )
                    events.append(
                        self._build_function_call_output_event(
                            tool_call,
                            result,
                        )
                    )

                    self.log_manager.record_tool_call(
                        node.id,
                        tool_name,
                        True,
                        self._serialize_tool_result(result),
                        {"arguments": arguments},
                        CallStage.AFTER,
                    )
                except WorkflowCancelledError:
                    raise
                except CliCancelled as exc:
                    raise WorkflowCancelledError("Workflow execution cancelled") from exc
                except Exception as exc:
                    self.log_manager.record_tool_call(
                        node.id,
                        tool_name,
                        False,
                        None,
                        {"error": str(exc), "arguments": arguments},
                        CallStage.AFTER,
                    )
                    tool_message = Message(
                        role=MessageRole.TOOL,
                        content=f"Tool {tool_name} error: {exc}",
                        tool_call_id=tool_call.id,
                        metadata={"tool_name": tool_name, "source": node.id},
                    )
                    events.append(
                        FunctionCallOutputEvent(
                            call_id=tool_call.id or tool_call.function_name or "tool_call",
                            function_name=tool_call.function_name,
                            output_text=f"error: {exc}",
                        )
                    )

                messages.append(tool_message)

        for followup in skill_followups:
            messages.append(followup)
            events.append(followup)
        return messages, events

    @contextmanager
    def _node_tool_context(self, node: Node):
        """Per-batch tool ``_context``: ``global_state`` plus this node's ``node_id``, without mutating it."""
        state = self.context.global_state
        yield _NodeToolContext(state, node.id) if state is not None else None

    def _provider_overrides(self) -> Dict[str, tuple]:
        overrides = getattr(self, "_overrides_by_node", None)
        if overrides is None:
            with _NODE_STATE_LOCK:
                overrides = getattr(self, "_overrides_by_node", None)
                if overrides is None:
                    overrides = {}
                    self._overrides_by_node = overrides
        return overrides

    def _run_configs(self) -> Dict[str, AgentConfig]:
        configs = getattr(self, "_run_configs_by_node", None)
        if configs is None:
            with _NODE_STATE_LOCK:
                configs = getattr(self, "_run_configs_by_node", None)
                if configs is None:
                    configs = {}
                    self._run_configs_by_node = configs
        return configs

    def _run_config(self, node: Node) -> AgentConfig | None:
        """This run's copy of the node's agent config (account switches live here), else the saved one."""
        return self._run_configs().get(node.id) or node.as_config(AgentConfig)

    def _bind_account(self, node: Node, agent_config: AgentConfig):
        creds = resolve_connection(agent_config.connection)
        agent_config.provider = creds.provider or creds.vendor
        agent_config.api_key = creds.token
        agent_config.base_url = creds.base_url or ""
        provider_class = ProviderRegistry.get_provider(agent_config.provider)
        if not provider_class:
            raise ValueError(f"Provider '{agent_config.provider}' not found")
        agent_config.token_tracker = self.context.get_token_tracker()
        agent_config.node_id = node.id
        return provider_class

    def _resolve_native_mode(self, node: Node, agent_config: AgentConfig, provider_class: Any) -> NativeRunContext | None:
        """Native agent mode for this call, or None to run normally (AgentDev tools through the prompt).

        Team leads always run normally: they need the AgentDev team tools (delegate, ask_user), which the
        native CLI agent cannot call. Shell commands need both ``allow_commands`` and the server opt-in.
        """
        cfg = getattr(agent_config, "native_mode", None)
        if cfg is None or not cfg.enabled:
            return None
        if agent_config.team is not None and agent_config.team.enabled:
            self.log_manager.warning(
                f"[Node: {node.id}] native_mode is ignored on a team lead; the lead runs in normal mode.",
                node_id=node.id,
            )
            return None
        if not getattr(provider_class, "supports_native_mode", False):
            self.log_manager.warning(
                f"[Node: {node.id}] native_mode needs a Claude or Codex CLI account; running in normal mode.",
                node_id=node.id,
            )
            return None
        workspace = self._native_workspace_root()
        allow_commands = False
        if cfg.allow_commands:
            try:
                require_unsafe_code_execution("Shell commands for native agents")
                allow_commands = True
            except SecurityError:
                self.log_manager.info(
                    f"[Node: {node.id}] native agent runs without shell commands "
                    f"({UNSAFE_CODE_EXECUTION_ENV} is not enabled on the server).",
                    node_id=node.id,
                )

        failures: Dict[str, int] = {}

        def on_tool(stage: str, name: str, success: Any, result: Any, details: Dict[str, Any]) -> None:
            extra: Dict[str, Any] = {}
            if stage != "before":
                if success is False:
                    # A failed built-in tool (a Bash command with a non-zero exit, a grep with no match, a
                    # failing test) is fed back to the agent, which handles it. Keep it a timeline entry with
                    # the real reason; raise it to the chat only when the same tool keeps failing.
                    failures[name] = failures.get(name, 0) + 1
                    extra["error"] = describe_tool_failure(name, result, details.get("arguments"))
                    extra["recoverable"] = failures[name] != NATIVE_REPEATED_FAILURES
                    if not extra["recoverable"]:
                        extra["error"] += f" (failed {failures[name]} times in a row)"
                elif success:
                    failures.pop(name, None)
            self.log_manager.record_tool_call(
                node.id, name, success, result, {**details, **extra, "native": True},
                CallStage.BEFORE if stage == "before" else CallStage.AFTER,
            )

        return NativeRunContext(
            workspace=str(workspace),
            allow_commands=allow_commands,
            max_turns=cfg.max_turns,
            on_tool=on_tool,
        )

    def _native_workspace_root(self) -> Path:
        """The run's project workspace: the folder the user opened, else the session's ``code_workspace``.

        The AgentDev installation itself is refused unless the user explicitly opened it as the project.
        """
        state = self.context.global_state or {}
        raw = state.get("python_workspace_root")
        if not raw:
            raise SecurityError("Native agent mode needs a project workspace, but this run has none")
        root = Path(raw).resolve()
        if not root.is_dir():
            raise SecurityError(f"Project workspace not found: {root}")
        graph_dir = state.get("graph_directory")
        default_root = Path(graph_dir, "code_workspace").resolve() if graph_dir else None
        opened_by_user = default_root is None or root != default_root
        install_root = AGENTDEV_INSTALL_ROOT
        if not opened_by_user and (root == install_root or install_root.is_relative_to(root)):
            raise SecurityError("Native agent mode refuses to work on the AgentDev installation folder")
        return root

    def _switch_account(self, node: Node, agent_config: AgentConfig, conn_id: str, *, notify: bool) -> None:
        from agentdev.connections.store import get_store

        # agent_config is this run's copy (see execute): the node's saved config is never changed.
        store = get_store()
        conn = store.get(conn_id)
        previous = agent_config.connection
        agent_config.connection = conn_id
        if conn is not None:
            original = node.as_config(AgentConfig)
            original_vendor = getattr(store.get(getattr(original, "connection", None) or ""), "vendor", None)
            previous_vendor = getattr(store.get(previous or ""), "vendor", None)
            if original is not None and original is not agent_config and conn.vendor == original_vendor:
                # Back on the vendor the user picked: use the model the user chose, not a default.
                agent_config.name = original.name
            elif conn.vendor != previous_vendor:
                # The model name belongs to the old vendor; use the new account's default model.
                agent_config.name = default_model_for(conn) or agent_config.name
        if notify:
            self.log_manager.warning(
                f"[Node: {node.id}] Account '{account_label(previous or '')}' reached its usage limit; "
                f"continuing on '{account_label(conn_id)}' ({agent_config.name}).",
                node_id=node.id,
                details={
                    "event": "account_fallback",
                    "from": account_label(previous or ""),
                    "to": account_label(conn_id),
                    "model": agent_config.name,
                },
            )

    def _fail_over(self, node: Node, agent_config: AgentConfig | None, exc: BaseException) -> bool:
        """Move this node to another signed-in account after a quota error. False when none is left."""
        if agent_config is None or not agent_config.connection:
            return False
        state = get_fallback_state(self.context.global_state)
        exhausted_id = agent_config.connection
        state.exhausted.add(exhausted_id)
        fallback = pick_fallback(
            exhausted_id,
            needs_tools=bool(agent_config.tooling) or agent_config.team is not None,
            exhausted=state.exhausted,
        )
        if fallback is None:
            self.log_manager.error(
                f"[Node: {node.id}] Account '{account_label(exhausted_id)}' reached its usage limit and no other "
                f"signed-in account is available. Sign in to another account on the Connections page.",
                node_id=node.id,
                details={"event": "account_exhausted", "from": account_label(exhausted_id)},
            )
            return False
        state.replacement[exhausted_id] = fallback.id
        for key, value in list(state.replacement.items()):
            if value == exhausted_id:
                state.replacement[key] = fallback.id
        self._switch_account(node, agent_config, fallback.id, notify=True)
        provider_class = self._bind_account(node, agent_config)
        provider = provider_class(agent_config)
        self._provider_overrides()[node.id] = (provider, provider.create_client())
        return True

    def _active_teams(self) -> Dict[str, TeamDelegation | None]:
        # One executor instance serves every agent node, and a lead's execute() runs its members
        # inside it, so per-node state is keyed by node id instead of a single attribute.
        teams = getattr(self, "_teams_by_node", None)
        if teams is None:
            with _NODE_STATE_LOCK:
                teams = getattr(self, "_teams_by_node", None)
                if teams is None:
                    teams = {}
                    self._teams_by_node = teams
        return teams

    def _build_team(self, node: Node, agent_config: AgentConfig, input_text: str = "") -> TeamDelegation | None:
        team_config = agent_config.team
        if not team_config or not team_config.enabled:
            return None
        runner = self.context.delegate_runner
        if runner is None:
            self.log_manager.warning(f"[Node: {node.id}] Team lead configured but no delegate runner is available")
            return None
        members = resolve_members(node.id, team_config.members, self.context.graph_nodes or {})
        missing = [m for m in team_config.members if m not in {mem.node_id for mem in members}]
        if missing:
            self.log_manager.warning(f"[Node: {node.id}] Team members not found or not agents: {missing}", node_id=node.id)
        cancel_event = getattr(self.context, "cancel_event", None)
        state = get_team_state(self.context.global_state, cancel_event=cancel_event)
        delegated = is_delegated_call()
        if not delegated:
            # The lead talking to the user sets the language members write user-facing text in.
            # ``newest``: the message itself (not an earlier one picked for its language) drives the
            # small-talk fast path and the plan-approval check.
            state.set_user_language(latest_user_message(input_text), newest=newest_user_message(input_text))
        return TeamDelegation(
            lead_id=node.id,
            members=members,
            runner=runner,
            # A sub-lead (a lead briefed by another lead) reports to that lead and never asks the user.
            prompt_service=None if delegated else self.context.get_human_prompt_service(),
            state=state,
            delegated=delegated,
            max_delegations=team_config.max_delegations,
            max_review_rounds=team_config.max_review_rounds,
            plan_approval=team_config.plan_approval,
            max_parallel=team_config.max_parallel,
            cancel_event=cancel_event,
        )

    def _refuse_team_tool(self, node: Node, tool_call: ToolCallPayload, tool_name: str, events: List[Any]) -> Message:
        """Answer a delegation the plan gate does not allow, without running it."""
        self.log_manager.record_tool_call(
            node.id, tool_name, False, None, {"error": PLAN_GATE_REFUSAL, "refused": "plan_pending"}, CallStage.AFTER
        )
        events.append(
            FunctionCallOutputEvent(
                call_id=tool_call.id or tool_call.function_name or "tool_call",
                function_name=tool_call.function_name,
                output_text=f"error: {PLAN_GATE_REFUSAL}",
            )
        )
        return Message(
            role=MessageRole.TOOL,
            content=f"Tool {tool_name} error: {PLAN_GATE_REFUSAL}",
            tool_call_id=tool_call.id,
            metadata={"tool_name": tool_name, "source": node.id},
        )

    def _run_team_tool(
        self,
        node: Node,
        tool_call: ToolCallPayload,
        tool_name: str,
        arguments: Dict[str, Any],
        events: List[Any],
    ) -> Message:
        team = self._active_teams().get(node.id)
        self.log_manager.record_tool_call(node.id, tool_name, None, None, {"arguments": arguments}, CallStage.BEFORE)
        try:
            if team is None:
                raise ValueError("This agent does not lead a team")
            with self.log_manager.tool_timer(node.id, tool_name):
                result = team.execute(tool_name, arguments)
        except WorkflowCancelledError:
            raise
        except CliCancelled as exc:
            raise WorkflowCancelledError("Workflow execution cancelled") from exc
        except Exception as exc:
            self.log_manager.record_tool_call(
                node.id, tool_name, False, None, {"error": str(exc), "arguments": arguments}, CallStage.AFTER
            )
            events.append(
                FunctionCallOutputEvent(
                    call_id=tool_call.id or tool_call.function_name or "tool_call",
                    function_name=tool_call.function_name,
                    output_text=f"error: {exc}",
                )
            )
            return Message(
                role=MessageRole.TOOL,
                content=f"Tool {tool_name} error: {exc}",
                tool_call_id=tool_call.id,
                metadata={"tool_name": tool_name, "source": node.id},
            )
        events.append(self._build_function_call_output_event(tool_call, result))
        self.log_manager.record_tool_call(
            node.id, tool_name, True, self._serialize_tool_result(result), {"arguments": arguments}, CallStage.AFTER
        )
        return self._build_tool_message(result, tool_call, node_id=node.id, tool_name=tool_name)

    def _skill_tool_result(self, tool_name: str, result: Any, node_id: str) -> tuple[Any, Message | None]:
        """(tool result, follow-up message) for a skill tool.

        ``activate_skill`` answers with a short acknowledgement; the skill text goes once, in the
        follow-up message. Re-activating a skill that is already loaded adds nothing.
        """
        if tool_name != "activate_skill" or not isinstance(result, dict):
            return result, None
        name = result.get("skill_name", "unknown-skill")
        ack: Dict[str, Any] = {"skill": name, "loaded": True}
        if result.get("already_active"):
            ack["already_active"] = True
            return ack, None
        return ack, self._build_skill_followup_message(tool_name, result, node_id)

    def _build_skill_followup_message(
        self,
        tool_name: str,
        result: Any,
        node_id: str,
    ) -> Message | None:
        if tool_name != "activate_skill" or not isinstance(result, dict):
            return None

        instructions = result.get("instructions")
        skill_name = result.get("skill_name", "unknown-skill")
        allowed_tools = result.get("allowed_tools")
        if not isinstance(instructions, str) or not instructions.strip():
            return None

        tool_constraint = ""
        if isinstance(allowed_tools, list) and allowed_tools:
            tool_constraint = f"\n\nOnly use these external tools while this skill is active: {allowed_tools}"
        files = result.get("files")
        if isinstance(files, list) and files:
            tool_constraint += (
                "\n\nFiles in this skill (read the ones its instructions point to, or that fit the task, with "
                f"`read_skill_file`): {', '.join(str(item) for item in files)}"
            )

        # A user-role message, not SYSTEM: CLI providers hoist system messages to the top of the prompt,
        # while the skill belongs at the end of the conversation, after the call that loaded it.
        return Message(
            role=MessageRole.USER,
            content=(
                f"[Skill instructions: {skill_name}]\n"
                f"Activated Agent Skill `{skill_name}`. "
                "Follow its instructions for the current task until they are completed or no longer relevant.\n\n"
                f"{instructions}{tool_constraint}\n[End skill instructions]"
            ),
            metadata={"source": node_id, "skill_name": skill_name, "skill_activation": True},
        )

    def _execute_skill_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        skill_manager: AgentSkillManager | None,
    ) -> Dict[str, Any]:
        if skill_manager is None:
            raise ValueError("Agent Skills are not enabled for this node")

        if tool_name == "activate_skill":
            skill_name = str(arguments.get("skill_name", "")).strip()
            if not skill_name:
                raise ValueError("skill_name is required")
            # A preloaded skill is already in the system prompt: acknowledge it without repeating its text.
            already_active = skill_manager.is_activated(skill_name) or skill_manager.is_preloaded(skill_name)
            result = dict(skill_manager.activate_skill(skill_name))
            if already_active:
                result["already_active"] = True
            return result

        if tool_name == "read_skill_file":
            skill_name = str(arguments.get("skill_name", "")).strip()
            relative_path = str(arguments.get("relative_path", "")).strip()
            if not skill_name:
                raise ValueError("skill_name is required")
            if not relative_path:
                raise ValueError("relative_path is required")
            return skill_manager.read_skill_file(skill_name, relative_path)

        raise ValueError(f"Unsupported skill tool '{tool_name}'")

    def _build_function_call_output_event(
        self,
        tool_call: ToolCallPayload,
        result: Any,
    ) -> FunctionCallOutputEvent:
        call_id = tool_call.id or tool_call.function_name or "tool_call"
        blocks = self._coerce_tool_result_to_blocks(result)
        if blocks:
            return FunctionCallOutputEvent(
                call_id=call_id,
                function_name=tool_call.function_name,
                output_blocks=blocks,
            )
        return FunctionCallOutputEvent(
            call_id=call_id,
            function_name=tool_call.function_name,
            output_text=self._stringify_tool_result(result),
        )

    def _stringify_tool_result(self, result: Any) -> str:
        if isinstance(result, Message):
            return result.text_content()
        if isinstance(result, list) and all(isinstance(item, MessageBlock) for item in result):
            parts = [block.describe() for block in result if block.describe()]
            return "\n".join(parts)
        if isinstance(result, (dict, list)):
            try:
                return json.dumps(result, ensure_ascii=False)
            except Exception:
                return str(result)
        return str(result)

    def _serialize_tool_result(self, result: Any) -> Any:
        """Convert tool outputs into JSON-serializable structures for logging."""
        from agentdev.utils.attachments import AttachmentRecord  # local import to avoid cycles

        if result is None:
            return None
        if isinstance(result, Message):
            return result.to_dict(include_data=False)
        if isinstance(result, MessageBlock):
            return result.to_dict(include_data=False)
        if isinstance(result, AttachmentRecord):
            return result.to_dict()
        if isinstance(result, list):
            return [self._serialize_tool_result(item) for item in result]
        if isinstance(result, dict):
            return {
                str(key): self._serialize_tool_result(value)
                for key, value in result.items()
            }
        if hasattr(result, "to_dict"):
            try:
                return self._serialize_tool_result(result.to_dict())
            except Exception:
                return str(result)
        return result if isinstance(result, (str, int, float, bool)) else str(result)

    def _build_tool_message(
        self,
        result: Any,
        tool_call: ToolCallPayload,
        *,
        node_id: str,
        tool_name: str,
    ) -> Message:
        base_metadata = {"tool_name": tool_name, "source": node_id}
        if isinstance(result, Message):
            msg = result.clone()
            msg = msg.with_role(MessageRole.TOOL)
            msg.tool_call_id = tool_call.id
            metadata = dict(base_metadata)
            metadata.update(msg.metadata)
            msg.metadata = metadata
            return msg

        from agentdev.utils.attachments import AttachmentRecord  # local import

        if isinstance(result, AttachmentRecord):
            content = [result.as_message_block()]
        elif isinstance(result, list) and all(isinstance(item, MessageBlock) for item in result):
            content = [block.copy() for block in result]
        else:
            content = result
            if isinstance(result, dict):
                # Compact JSON: every later model call of the loop re-reads this text.
                content = json.dumps(self._serialize_tool_result(content), ensure_ascii=False, separators=(",", ":"))
            elif not isinstance(result, str):
                content = str(result)
            if isinstance(content, str) and len(content) > MAX_TOOL_RESULT_CHARS:
                content = clip_middle(content, MAX_TOOL_RESULT_CHARS, head_ratio=0.7)

        return Message(
            role=MessageRole.TOOL,
            content=content,
            tool_call_id=tool_call.id,
            metadata=base_metadata,
        )

    def _build_initial_timeline(self, conversation: List[Message]) -> List[Any]:
        return [msg.clone() for msg in conversation]

    def _finalize_tool_trace(
        self,
        message: Message,
        trace_messages: List[Message],
        complete: bool,
        node_id: str,
    ) -> Message:
        final_message = self._clone_with_source(message, node_id)
        if trace_messages:
            metadata = dict(final_message.metadata)
            metadata["context_trace"] = [item.to_dict() for item in trace_messages]
            metadata["context_trace_complete"] = complete
            final_message.metadata = metadata
        return final_message

    def _clone_with_source(self, message: Message, node_id: str) -> Message:
        cloned = message.clone()
        metadata = dict(cloned.metadata)
        metadata.setdefault("source", node_id)
        cloned.metadata = metadata
        return cloned

    def _coerce_tool_result_to_blocks(self, result: Any) -> List[MessageBlock]:
        """Convert supported tool outputs into MessageBlock sequences."""
        if result is None:
            return []
        if isinstance(result, Message):
            return [block.copy() for block in result.blocks()]
        if isinstance(result, MessageBlock):
            return [result.copy()]

        from agentdev.utils.attachments import AttachmentRecord  # local import to avoid cycles

        if isinstance(result, AttachmentRecord):
            return [result.as_message_block()]

        if isinstance(result, Sequence) and not isinstance(result, (str, bytes, bytearray)):
            blocks: List[MessageBlock] = []
            for item in result:
                blocks.extend(self._coerce_tool_result_to_blocks(item))
            return blocks

        return []

    def _parse_tool_call_arguments(self, raw_arguments: Any) -> Dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if not raw_arguments:
            return {}
        if isinstance(raw_arguments, str):
            try:
                parsed = json.loads(raw_arguments)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _get_tool_loop_limit(self, node: Node) -> int:
        default_limit = 50
        model = node.as_config(AgentConfig)
        if not model or not model.params:
            return default_limit
        custom_limit = model.params.get("tool_loop_limit")
        if isinstance(custom_limit, int) and custom_limit > 0:
            return custom_limit
        return default_limit

    def _persist_message_attachments(self, message: Message, node_id: str) -> None:
        """Register attachments produced by model outputs to the attachment store."""
        store = self.context.global_state.get("attachment_store")
        if store is None:
            return
        for block in message.blocks():
            attachment = block.attachment
            if not attachment:
                continue
            try:
                self._persist_single_attachment(store, block, node_id)
            except SecurityError:
                raise
            except Exception as exc:
                raise RuntimeError(f"Failed to persist attachment '{attachment.name or attachment.attachment_id}': {exc}") from exc

    def _persist_single_attachment(self, store: Any, block: MessageBlock, node_id: str) -> None:
        attachment = block.attachment
        if attachment is None:
            return
        attachment.mime_type = attachment.mime_type or self._guess_mime_from_data_uri(attachment.data_uri)
        try:
            validate_path_component(node_id, field="node_id")
            if attachment.attachment_id:
                validate_path_component(attachment.attachment_id, field="attachment_id")
            filename = validate_path_component(self._make_generated_filename(attachment), field="attachment name")
        except ValidationError as exc:
            raise SecurityError(f"Invalid generated attachment path: {exc}") from exc
        if attachment.remote_file_id and not attachment.data_uri and not attachment.local_path:
            record = store.register_remote_file(
                remote_file_id=attachment.remote_file_id,
                name=attachment.name or attachment.attachment_id or "remote_file",
                mime_type=attachment.mime_type,
                size=attachment.size,
                kind=block.type,
                attachment_id=attachment.attachment_id,
            )
            block.attachment = record.ref
            return

        workspace_root = self.context.global_state.get("python_workspace_root")
        if workspace_root is None or not node_id:
            raise RuntimeError("Workspace or node context missing for attachment persistence")

        workspace_root = Path(workspace_root).resolve()
        try:
            target_path = resolve_workspace_path(workspace_root, "generated", node_id, filename)
            current = workspace_root
            for part in ("generated", node_id, filename):
                current = current / part
                if is_link(current):
                    raise SecurityError("Generated attachment paths must not contain symbolic links")
        except (ValidationError, OSError, RuntimeError) as exc:
            raise SecurityError(f"Invalid generated attachment path: {exc}") from exc

        data_bytes = self._decode_data_uri(attachment.data_uri) if attachment.data_uri else None
        if data_bytes is None and attachment.local_path:
            try:
                source = Path(attachment.local_path).resolve()
                if not source.is_relative_to(workspace_root) or not source.is_file():
                    raise SecurityError("Generated attachment source must stay inside the workspace")
            except (OSError, RuntimeError, ValueError) as exc:
                raise SecurityError("Invalid generated attachment source") from exc
            target_path.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            if source != target_path:
                shutil.copy2(source, target_path)
        elif data_bytes is not None:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "wb") as handle:
                handle.write(data_bytes)
        else:
            raise ValueError("Attachment missing data for persistence")

        record = store.register_file(
            target_path,
            kind=block.type,
            display_name=attachment.name or target_path.name,
            mime_type=attachment.mime_type,
            attachment_id=attachment.attachment_id,
            copy_file=False,
            persist=True,
        )
        block.attachment = record.ref

    def _decode_data_uri(self, data_uri: Optional[str]) -> Optional[bytes]:
        if not data_uri:
            return None
        if not data_uri.startswith("data:"):
            return None
        header, _, payload = data_uri.partition(",")
        if not _:
            return None
        if ";base64" in header:
            return base64.b64decode(payload)
        return payload.encode("utf-8")

    def _make_generated_filename(self, attachment: AttachmentRef) -> str:
        """Generate a filename based on mime type or attachment id."""
        name = attachment.name
        if name:
            return name
        mime = attachment.mime_type or ""
        ext = ""
        if "/" in mime:
            subtype = mime.split("/", 1)[1]
            if subtype:
                ext = f".{subtype.split('+')[0]}"
        if not ext:
            ext = ".bin"
        return f"{attachment.attachment_id or 'generated'}{ext}"

    def _guess_mime_from_data_uri(self, data_uri: Optional[str]) -> Optional[str]:
        if not data_uri or not data_uri.startswith("data:"):
            return None
        header = data_uri.split(",", 1)[0]
        if ":" in header:
            header = header.split(":", 1)[1]
        return header.split(";")[0] if ";" in header else header


    def _apply_post_generation_thinking(
        self,
        node: Node,
        conversation: List[Message],
        query_snapshot: MemoryContentSnapshot,
        input_payload: ThinkingPayload,
        gen_payload: ThinkingPayload,
        stage: AgentExecFlowStage,
        agent_invoker: Callable[[List[Message]], Message],
        input_mode: AgentInputMode,
    ) -> Message | str:
        """Apply post-generation thinking."""
        self._ensure_not_cancelled()
        thinking_manager = self.context.get_thinking_manager(node.id)
        if not thinking_manager:
            return gen_payload.raw if gen_payload.raw is not None else gen_payload.text

        model = node.as_config(AgentConfig)

        with self.log_manager.thinking_timer(node.id, stage.value):
            retrieved_memory = self._retrieve_memory(node, query_snapshot, stage)
            memory_payload = self._memory_result_to_thinking_payload(retrieved_memory)
            result = thinking_manager.think(
                agent_invoker=agent_invoker,
                input_payload=input_payload,
                agent_role=node.role or "",
                memory=memory_payload,
                gen_payload=gen_payload,
            )

        mode_value = model.thinking.type if model and model.thinking else "unknown"
        self.log_manager.record_thinking_process(
            node.id,
            mode_value,
            result if isinstance(result, str) else "[message]",
            stage.value,
            {"has_memory": bool(retrieved_memory and retrieved_memory.items)},
        )

        if input_mode is AgentInputMode.MESSAGES:
            if isinstance(result, Message):
                self._persist_message_attachments(result, node.id)
                self._reset_conversation_with_user_result(conversation, result, node_id=node.id)
            else:
                self._reset_conversation_with_user_result(conversation, result, node_id=node.id)

        return result

    def _coerce_inputs_to_messages(self, inputs: List[Message]) -> List[Message]:
        return [message.clone() for message in inputs if isinstance(message, Message)]

    def _append_user_message(self, conversation: List[Message], content: str, *, node_id: str) -> None:
        conversation.append(
            Message(role=MessageRole.USER, content=content, metadata={"source": node_id})
        )

    def _insert_memory_message(self, conversation: List[Message], content: str, *, node_id: str) -> None:
        last_user_idx = self._find_last_user_index(conversation)
        insert_idx = last_user_idx if last_user_idx is not None else len(conversation)
        conversation.insert(
            insert_idx,
            Message(role=MessageRole.USER, content=content, metadata={"source": node_id}),
        )

    def _find_last_user_index(self, conversation: List[Message]) -> Optional[int]:
        for idx in range(len(conversation) - 1, -1, -1):
            if conversation[idx].role is MessageRole.USER:
                return idx
        return None

    def _reset_conversation_with_user_result(self, conversation: List[Message], content: Message | str, *, node_id: str) -> None:
        system_messages = [msg.clone() for msg in conversation if msg.role is MessageRole.SYSTEM]
        conversation.clear()
        conversation.extend(system_messages)
        if isinstance(content, Message):
            conversation.append(self._clone_with_source(content.with_role(MessageRole.USER), node_id))
        else:
            conversation.append(
                Message(role=MessageRole.USER, content=content, metadata={"source": node_id})
            )

    def _update_memory(self, node: Node, input_data: str, inputs: List[Message], result: Message | str) -> None:
        """Update the memory store with the latest conversation."""
        memory_manager = self.context.get_memory_manager(node.id)
        if not memory_manager:
            return

        stage = AgentExecFlowStage.FINISHED_STAGE

        input_snapshot = MemoryContentSnapshot.from_messages(inputs)
        output_snapshot = MemoryContentSnapshot.from_message(result)
        payload = MemoryWritePayload(
            agent_role=node.role if node.role else "",
            inputs_text=input_data,
            input_snapshot=input_snapshot,
            output_snapshot=output_snapshot,
        )

        with self.log_manager.memory_timer(node.id, "UPDATE", stage.value):
            memory_manager.update(payload)

        # Record the memory update
        normalized_result = result.text_content() if isinstance(result, Message) else str(result)
        self.log_manager.record_memory_operation(
            node.id,
            "UPDATE",
            stage.value,
            normalized_result,
            {
                "stage": stage.value,
                "input_size": len(str(input_data)),
                "output_size": len(normalized_result),
                "attachment_count": len(output_snapshot.attachment_overview()) if output_snapshot else 0,
            }
        )

    def _build_thinking_payload_from_inputs(self, inputs: List[Message], input_text: str) -> ThinkingPayload:
        blocks: List[MessageBlock] = []
        for message in inputs:
            blocks.extend(message.blocks())
        return ThinkingPayload(
            text=input_text,
            blocks=blocks,
            metadata={"source": "inputs"},
            raw=input_text,
        )

    def _build_memory_query_snapshot(
        self,
        inputs: List[Message],
        input_text: str,
    ) -> MemoryContentSnapshot:
        base_snapshot = MemoryContentSnapshot.from_messages(inputs)
        blocks = list(base_snapshot.blocks) if base_snapshot else []
        return MemoryContentSnapshot(text=input_text, blocks=blocks)

    def _build_thinking_payload_from_message(self, message: Message | str | None, *, source: str) -> ThinkingPayload:
        if isinstance(message, Message):
            return ThinkingPayload(
                text=message.text_content(),
                blocks=message.blocks(),
                metadata={"source": source},
                raw=message,
            )
        text = "" if message is None else str(message)
        return ThinkingPayload(text=text, blocks=[], metadata={"source": source}, raw=text)

    def _memory_result_to_thinking_payload(
        self,
        result: MemoryRetrievalResult | None,
    ) -> ThinkingPayload | None:
        if not result:
            return None
        blocks: List[MessageBlock] = []
        for item in result.items:
            if item.output_snapshot:
                blocks.extend(item.output_snapshot.to_message_blocks())
            if item.input_snapshot:
                blocks.extend(item.input_snapshot.to_message_blocks())
        metadata = {
            "source": "memory",
            "has_multimodal": result.has_multimodal(),
            "attachment_count": len(result.attachment_overview()),
        }
        return ThinkingPayload(text=result.formatted_text, blocks=blocks, metadata=metadata)
