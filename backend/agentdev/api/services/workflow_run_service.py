"""Service responsible for executing workflows for WebSocket sessions."""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from agentdev.validation.check import load_config
from agentdev.entity.graph_config import GraphConfig
from agentdev.entity.messages import Message
from agentdev.entity.enums import LogLevel
from agentdev.utils.exceptions import ValidationError, WorkflowCancelledError
from agentdev.utils.structured_logger import get_server_logger, LogType
from agentdev.utils.task_input import TaskInputBuilder
from agentdev.utils.workspace_paths import session_directory_name
from agentdev.workflow.graph_context import GraphContext

from agentdev.api.services.attachment_service import AttachmentService
from agentdev.api.services.conversation_turns import attachment_refs, compose_follow_up_prompt, make_turn
from agentdev.api.services.run_checkpoint import (
    STATE_COMPLETED,
    STATE_INTERRUPTED,
    STATE_RUNNING,
    RunCheckpointRecorder,
    build_resume_note,
    build_turn_resume_note,
    is_interrupted,
    is_resume_intent,
    new_checkpoint,
)
from agentdev.runtime.node.agent.team import (
    PLAN_PENDING_KEY,
    PLAN_PROPOSED_EVENT,
    team_digest_from_state,
    user_exchanges,
)
from agentdev.api.services.local_projects import opened_project_folder
from agentdev.api.services.session_execution import SessionExecutionController
from agentdev.api.services.session_store import SessionBusyError, SessionStatus, WorkflowSessionStore
from agentdev.api.services.websocket_executor import WebSocketGraphExecutor
from agentdev.api.services.workflow_storage import validate_workflow_filename
from agentdev.api.settings import WARE_HOUSE_DIR, YAML_DIR

RUN_IN_PROGRESS_CODE = "run_in_progress"
RUN_IN_PROGRESS_MESSAGE = "A run is already in progress in this session"


def run_in_progress(session) -> bool:
    """True while a graph is starting or running in ``session`` (a follow-up must wait for it)."""
    return session is not None and (session.executor is not None or bool(getattr(session, "starting", False)))


def run_error(message: str, code: str) -> Dict:
    """A fatal error: the run itself ended (see the contract in message_handler.py)."""
    return {"type": "error", "data": {"message": message, "code": code, "fatal": True}}


def _busy_error() -> Dict:
    return {"type": "error", "data": {"message": RUN_IN_PROGRESS_MESSAGE, "code": RUN_IN_PROGRESS_CODE, "fatal": False}}


class WorkflowRunService:
    def __init__(
        self,
        session_store: WorkflowSessionStore,
        session_controller: SessionExecutionController,
        attachment_service: AttachmentService,
    ) -> None:
        self.session_store = session_store
        self.session_controller = session_controller
        self.attachment_service = attachment_service
        self.logger = logging.getLogger(__name__)

    def request_cancel(self, session_id: str, *, reason: Optional[str] = None) -> bool:
        session = self.session_store.get_session(session_id)
        if not session:
            return False

        cancel_message = reason or "Cancellation requested"
        session.cancel_reason = cancel_message
        if not session.cancel_event.is_set():
            session.cancel_event.set()
            self.logger.info("Cancellation requested for session %s", session_id)

        if session.executor:
            try:
                session.executor.request_cancel(cancel_message)
            except Exception as exc:
                self.logger.warning("Failed to propagate cancellation to executor for %s: %s", session_id, exc)

        if run_in_progress(session):
            # The run is still alive: CANCELLED / workflow_cancelled come when it really ends.
            self.session_store.update_session_status(session_id, SessionStatus.CANCELLING, error_message=cancel_message)
        elif session.status in (SessionStatus.RUNNING, SessionStatus.WAITING_FOR_INPUT):
            self.session_store.update_session_status(session_id, SessionStatus.CANCELLED, error_message=cancel_message)
        return True

    async def start_workflow(
        self,
        session_id: str,
        yaml_file: str,
        task_prompt: str,
        websocket_manager,
        *,
        attachments: Optional[List[str]] = None,
        log_level: Optional[LogLevel] = None,
    ) -> None:
        normalized_yaml_name = (yaml_file or "").strip()
        existing = self.session_store.get_session(session_id)
        if run_in_progress(existing):
            # A follow-up must wait for the current run; never run two graphs in one session.
            await websocket_manager.send_message(session_id, _busy_error())
            return
        # NOTE: no await between the check above and ``session.starting = True`` below,
        # otherwise a second launch could pass the check too.
        session = None
        try:
            yaml_path = self._resolve_yaml_path(normalized_yaml_name)
            normalized_yaml_name = yaml_path.name

            attachments = attachments or []
            if (not task_prompt or not task_prompt.strip()) and not attachments:
                raise ValidationError(
                    "Task prompt cannot be empty",
                    details={"task_prompt_provided": bool(task_prompt)},
                )

            self.attachment_service.prepare_session_workspace(session_id)
            session = self.session_store.create_session(
                yaml_file=normalized_yaml_name,
                task_prompt=task_prompt,
                session_id=session_id,
                attachments=attachments,
                title_hint=None if (task_prompt or "").strip() else ", ".join(self._attachment_names(session_id, attachments)),
            )
            session.starting = True
            self.session_store.update_session_status(session_id, SessionStatus.RUNNING)
            self._begin_checkpoint(session_id, session, task_prompt, attachments)
            websocket_manager.record_user_message(session_id, task_prompt, attachments)

            await websocket_manager.send_message(
                session_id,
                {
                    "type": "workflow_started",
                    "data": {"yaml_file": normalized_yaml_name, "task_prompt": task_prompt},
                },
            )

            await self._execute_workflow_async(
                session_id,
                yaml_path,
                task_prompt,
                websocket_manager,
                attachments,
                log_level,
            )
        except SessionBusyError:
            # Another launch won the race; leave its session alone.
            await websocket_manager.send_message(session_id, _busy_error())
        except ValidationError as exc:
            self.logger.error(str(exc))
            logger = get_server_logger()
            logger.error(
                "Workflow validation error",
                log_type=LogType.WORKFLOW,
                session_id=session_id,
                yaml_file=normalized_yaml_name,
                validation_details=getattr(exc, "details", None),
            )
            self.session_store.set_session_error(session_id, str(exc))
            self._close_checkpoint(session_id, None, interrupted_reason=str(exc))
            self._release(session_id, session)
            await websocket_manager.send_message(session_id, run_error(str(exc), "validation_error"))
        except Exception as exc:
            self.logger.error(f"Error starting workflow for session {session_id}: {exc}")
            logger = get_server_logger()
            logger.log_exception(
                exc,
                "Error starting workflow",
                session_id=session_id,
                yaml_file=normalized_yaml_name,
            )
            self.session_store.set_session_error(session_id, str(exc))
            self._close_checkpoint(session_id, None, interrupted_reason=str(exc))
            self._release(session_id, session)
            await websocket_manager.send_message(session_id, run_error(f"Failed to start workflow: {exc}", "start_failed"))
        finally:
            self._release(session_id, session)

    async def _execute_workflow_async(
        self,
        session_id: str,
        yaml_path: Path,
        task_prompt: str,
        websocket_manager,
        attachments: List[str],
        log_level: LogLevel,
    ) -> None:
        session = self.session_store.get_session(session_id)
        cancel_event = session.cancel_event if session else None
        try:
            # Parsing the YAML, building the graph and the runtime, and reading attachments are
            # blocking work: keep them off the event loop so other sessions' sockets stay responsive.
            graph_context, executor, task_input = await asyncio.to_thread(
                self._prepare_run,
                session_id,
                session,
                yaml_path,
                task_prompt,
                websocket_manager,
                attachments,
                log_level,
                cancel_event,
            )
            await executor.execute_graph_async(task_input)

            # If cancellation was requested during execution but not raised inside threads,
            # treat the run as cancelled to avoid conflicting status.
            if cancel_event and cancel_event.is_set():
                reason = session.cancel_reason if session else "Cancellation requested"
                raise WorkflowCancelledError(reason, workflow_id=graph_context.name)

            results = executor.get_results()
            self.session_store.complete_session(session_id, results)
            self._remember_turn(session_id, task_prompt, attachments, executor)
            self._close_checkpoint(session_id, executor)
            summary =self._final_answer(executor) or graph_context.final_message()
            token_usage = executor.token_tracker.get_token_usage()
            plan = self._pending_plan(executor)
            # Free the session before announcing the end, so a follow-up sent right away is accepted.
            self._release(session_id, session)

            if plan is not None:
                # The lead submitted a plan and stopped: the UI shows it as awaiting approval.
                await websocket_manager.send_message(session_id, {"type": PLAN_PROPOSED_EVENT, "data": plan})

            await websocket_manager.send_message(
                session_id,
                {
                    "type": "workflow_completed",
                    "data": {
                        "results": results,
                        # The lead's / end node's answer is the delivered result; the generic
                        # "Workflow finished with N node outputs" line only when there is none.
                        "summary": summary,
                        "token_usage": token_usage,
                    },
                },
            )

            logger = get_server_logger()
            logger.info(
                "Workflow execution completed successfully",
                log_type=LogType.WORKFLOW,
                session_id=session_id,
                yaml_path=str(yaml_path),
                result_count=len(results) if isinstance(results, dict) else 0,
            )
        except WorkflowCancelledError as exc:
            await self._finish_cancelled(session_id, session, str(exc), task_prompt, attachments, websocket_manager, yaml_path)
        except ValidationError as exc:
            if cancel_event and cancel_event.is_set():
                # The run died because it was cancelled (e.g. its CLI was killed): report a cancel.
                await self._finish_cancelled(
                    session_id, session, session.cancel_reason or str(exc), task_prompt, attachments, websocket_manager, yaml_path
                )
                return
            self.session_store.set_session_error(session_id, str(exc))
            self._remember_turn(session_id, task_prompt, attachments, self._current_executor(session_id), status="error")
            self._close_checkpoint(session_id, self._current_executor(session_id), interrupted_reason=str(exc))
            self._release(session_id, session)
            await websocket_manager.send_message(session_id, run_error(str(exc), "validation_error"))
            logger = get_server_logger()
            logger.error(
                "Workflow validation error",
                log_type=LogType.WORKFLOW,
                session_id=session_id,
                yaml_path=str(yaml_path),
                validation_details=getattr(exc, "details", None),
            )
        except Exception as exc:
            if cancel_event and cancel_event.is_set():
                await self._finish_cancelled(
                    session_id, session, session.cancel_reason or str(exc), task_prompt, attachments, websocket_manager, yaml_path
                )
                return
            self.session_store.set_session_error(session_id, str(exc))
            self._remember_turn(session_id, task_prompt, attachments, self._current_executor(session_id), status="error")
            self._close_checkpoint(session_id, self._current_executor(session_id), interrupted_reason=str(exc))
            self._release(session_id, session)
            await websocket_manager.send_message(session_id, run_error(f"Workflow execution error: {exc}", "run_failed"))
            logger = get_server_logger()
            logger.log_exception(
                exc,
                f"Error executing workflow for session {session_id}",
                session_id=session_id,
                yaml_path=str(yaml_path),
            )
        finally:
            self._release(session_id, session)

    def _prepare_run(
        self,
        session_id: str,
        session,
        yaml_path: Path,
        task_prompt: str,
        websocket_manager,
        attachments: List[str],
        log_level: Optional[LogLevel],
        cancel_event,
    ):
        """Build the graph, the executor and the first task input (blocking; runs in a worker thread)."""
        design = load_config(yaml_path)
        graph_config = GraphConfig.from_definition(
            design.graph,
            name=session_directory_name(session_id),
            output_root=WARE_HOUSE_DIR,
            source_path=str(yaml_path),
            vars=design.vars,
        )
        if log_level:
            graph_config.log_level = log_level
            graph_config.definition.log_level = log_level
        graph_context = GraphContext(config=graph_config)

        executor = WebSocketGraphExecutor(
            graph_context,
            session_id,
            self.session_controller,
            self.attachment_service,
            websocket_manager,
            self.session_store,
            cancel_event=cancel_event,
            workspace_root=opened_project_folder(session),
        )

        if session:
            executor.checkpoint_recorder = self._make_recorder(session_id, executor)
            session.graph = graph_context
            session.executor = executor
            if session.cancel_event.is_set():
                executor.request_cancel(session.cancel_reason or "Cancellation requested")

        task_input = self._build_initial_task_input(
            session_id,
            graph_context,
            task_prompt,
            attachments,
            executor.attachment_store,
        )

        dispatcher = getattr(executor, "artifact_dispatcher", None)
        if dispatcher is not None:
            dispatcher.set_request(task_prompt)
        return graph_context, executor, task_input

    async def _finish_cancelled(
        self, session_id, session, reason, task_prompt, attachments, websocket_manager, yaml_path
    ) -> None:
        """The run has really ended after a cancel: only now report CANCELLED."""
        self.session_store.update_session_status(session_id, SessionStatus.CANCELLED, error_message=reason)
        self._remember_turn(session_id, task_prompt, attachments, self._current_executor(session_id), status="cancelled")
        self._close_checkpoint(
            session_id, self._current_executor(session_id), interrupted_reason=reason or "Stopped by the user"
        )
        self._release(session_id, session)
        await websocket_manager.send_message(session_id, {"type": "workflow_cancelled", "data": {"message": reason}})
        get_server_logger().info(
            "Workflow execution cancelled",
            log_type=LogType.WORKFLOW,
            session_id=session_id,
            yaml_path=str(yaml_path),
            cancellation_reason=reason,
        )

    def _release(self, session_id: str, session) -> None:
        """Mark ``session``'s run as over (idempotent).

        Works on the run's own session object: once released, a follow-up may already
        have replaced it in the store, and that new run must not be touched.
        """
        if session is None:
            return
        if self.session_store.get_session(session_id) is session and (session.executor is not None or session.starting):
            self.session_controller.cleanup_session(session_id)
        session.executor = None
        session.graph = None
        session.starting = False

    def _build_initial_task_input(
        self,
        session_id: str,
        graph_context: GraphContext,
        prompt: str,
        attachment_ids: List[str],
        store,
    ) -> Union[List[Message], str]:
        prompt = self._with_conversation_history(session_id, graph_context, prompt)
        if not attachment_ids:
            return prompt

        blocks = self.attachment_service.build_attachment_blocks(
            session_id,
            attachment_ids,
            target_store=store,
        )
        return TaskInputBuilder(store).build_from_blocks(prompt, blocks)

    def _with_conversation_history(self, session_id: str, graph_context: GraphContext, prompt: str) -> str:
        """Give a follow-up run the earlier turns of this session.

        Only for a single start node (e.g. a team lead): it is the one talking to the
        user, and with several entry points a shared transcript would be ambiguous.
        """
        session = self.session_store.get_session(session_id)
        if not session or not (session.turns or session.prior_checkpoint):
            return prompt
        start_nodes = list(getattr(graph_context.config.definition, "start_nodes", None) or [])
        if len(start_nodes) != 1:
            return prompt
        return compose_follow_up_prompt(session.turns, prompt, self._resume_note(session, prompt))

    @staticmethod
    def _resume_note(session, prompt: str) -> str:
        """What the interrupted run already did, for the prompt of the run that follows it ("" if none)."""
        resume = is_resume_intent(prompt)
        if session.prior_checkpoint:
            last = session.turns[-1] if session.turns else None
            # The stopped turn's own entry already lists the team's reports: do not repeat them.
            has_team = isinstance(last, dict) and bool(last.get("team"))
            return build_resume_note(session.prior_checkpoint, resume_requested=resume, include_team=not has_team)
        return build_turn_resume_note(session.turns) if resume else ""

    def _begin_checkpoint(self, session_id: str, session, prompt: str, attachment_ids: List[str]) -> None:
        """Start the run's checkpoint; a "continue" message carries the interrupted run's finished nodes over."""
        try:
            previous = session.checkpoint if is_interrupted(session.checkpoint) else None
            self.session_store.begin_checkpoint(
                session_id,
                new_checkpoint(
                    prompt,
                    self._attachment_names(session_id, attachment_ids),
                    previous=previous if is_resume_intent(prompt) else None,
                ),
            )
        except Exception as exc:  # never let the checkpoint break a launch
            self.logger.warning("Could not start checkpoint for session %s: %s", session_id, exc)

    def _make_recorder(self, session_id: str, executor) -> Optional[RunCheckpointRecorder]:
        session = self.session_store.get_session(session_id)
        if not session or not isinstance(session.checkpoint, dict):
            return None

        def team_source() -> Dict[str, List[Dict[str, str]]]:
            state = executor._get_execution_context().global_state
            return {"team": team_digest_from_state(state), "exchanges": self._plain_exchanges(state)}

        return RunCheckpointRecorder(
            session.checkpoint,
            lambda cp: self.session_store.save_checkpoint(session_id, cp),
            team_source,
        )

    @staticmethod
    def _plain_exchanges(global_state) -> List[Dict[str, str]]:
        return [e for e in user_exchanges(global_state) if e.get("kind") != "delegation"]

    def _close_checkpoint(self, session_id: str, executor, *, interrupted_reason: Optional[str] = None) -> None:
        """The run ended: ``completed``, or ``interrupted`` when ``interrupted_reason`` is given (idempotent)."""
        try:
            session = self.session_store.get_session(session_id)
            cp = getattr(session, "checkpoint", None)
            if not isinstance(cp, dict) or cp.get("state") != STATE_RUNNING:
                return
            recorder = getattr(executor, "checkpoint_recorder", None)
            if recorder is None or recorder.checkpoint is not cp:
                recorder = RunCheckpointRecorder(cp, lambda _cp: None)
            state = STATE_COMPLETED if interrupted_reason is None else STATE_INTERRUPTED
            self.session_store.save_checkpoint(session_id, recorder.finish(state, interrupted_reason or ""), persist_meta=True)
        except Exception as exc:  # best effort, like the turn history
            self.logger.warning("Could not close checkpoint for session %s: %s", session_id, exc)

    def _remember_turn(
        self,
        session_id: str,
        prompt: str,
        attachment_ids: List[str],
        executor,
        *,
        status: str = "completed",
    ) -> None:
        """Save the turn so a follow-up has context; also for cancelled/failed runs (partial answer)."""
        try:
            answer = ""
            exchanges: List[Dict[str, str]] = []
            if executor is not None:
                try:
                    answer = executor.get_final_output()
                except Exception as exc:  # history is best effort
                    self.logger.warning("Could not read final output for session %s: %s", session_id, exc)
                exchanges = self._user_exchanges(executor)
            answer = answer if isinstance(answer, str) else ""
            refs: List[Any] = []
            if attachment_ids:
                try:
                    refs = attachment_refs(
                        attachment_ids, self.attachment_service.list_attachment_manifests(session_id)
                    )
                except Exception:  # fall back to plain names
                    refs = list(self._attachment_names(session_id, attachment_ids))
            turn = make_turn(prompt, answer, refs, exchanges)
            turn["status"] = status  # how the run ended: completed / cancelled / error
            if status == "completed" and self._pending_plan(executor) is not None:
                turn["kind"] = "plan"  # the answer is a plan waiting for the user's approval
            self.session_store.add_turn(session_id, turn)
        except Exception as exc:  # never let history break the run's own error/cancel handling
            self.logger.warning("Could not save turn for session %s: %s", session_id, exc)

    def _current_executor(self, session_id: str):
        session = self.session_store.get_session(session_id)
        return getattr(session, "executor", None) if session else None

    def _attachment_names(self, session_id: str, attachment_ids: Optional[List[str]]) -> List[str]:
        names: List[str] = []
        if attachment_ids:
            try:
                manifest = self.attachment_service.list_attachment_manifests(session_id)
            except Exception:
                manifest = {}
            for attachment_id in attachment_ids:
                ref = (manifest.get(attachment_id) or {}).get("ref") or {}
                names.append(ref.get("name") or attachment_id)
        return names

    @staticmethod
    def _final_answer(executor) -> str:
        try:
            answer = executor.get_final_output()
        except Exception:  # noqa: BLE001 - summary is cosmetic
            return ""
        return answer.strip() if isinstance(answer, str) else ""

    @staticmethod
    def _pending_plan(executor) -> Optional[Dict[str, str]]:
        """The plan the lead submitted this run ({"node", "summary", "plan"}), or None."""
        if executor is None:
            return None
        try:
            plan = executor._get_execution_context().global_state.get(PLAN_PENDING_KEY)
        except Exception:  # best effort, like the turn history
            return None
        if not isinstance(plan, dict) or not plan.get("plan"):
            return None
        return {
            "node": str(plan.get("node") or ""),
            "summary": str(plan.get("summary") or ""),
            "plan": str(plan.get("plan") or ""),
        }

    def _user_exchanges(self, executor) -> List[Dict[str, str]]:
        """Questions the lead asked the user during the run (plan approvals, decisions) and the replies."""
        try:
            return user_exchanges(executor._get_execution_context().global_state)
        except Exception:  # best effort, like the rest of the turn history
            return []

    def _resolve_yaml_path(self, yaml_filename: str) -> Path:
        """Validate and resolve YAML paths inside the configured directory."""

        safe_name = validate_workflow_filename(yaml_filename, require_yaml_extension=True)
        yaml_path = YAML_DIR / safe_name
        if not yaml_path.exists():
            raise ValidationError("YAML file not found", details={"yaml_file": safe_name})
        return yaml_path
