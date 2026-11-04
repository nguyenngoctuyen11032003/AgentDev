"""GraphExecutor variant that reports results over WebSocket."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List

from agentdev.runtime.node.agent.team import CONVERSATION_TURNS_KEY
from agentdev.utils.logger import WorkflowLogger
from agentdev.workflow.graph import GraphExecutor
from agentdev.workflow.graph_context import GraphContext

from agentdev.api.services.attachment_service import AttachmentService
from agentdev.api.services.artifact_dispatcher import ArtifactDispatcher
from agentdev.api.services.prompt_channel import WebPromptChannel
from agentdev.api.services.session_store import WorkflowSessionStore
from agentdev.api.services.session_execution import SessionExecutionController
from agentdev.workflow.hooks.workspace_artifact import WorkspaceArtifact, WorkspaceArtifactHook
from agentdev.utils.run_mode import DEFAULT_RUN_MODE, RUN_MODE_KEY, normalize_run_mode


# A run holds its worker thread for minutes. On the loop's shared default pool (a handful of
# threads) a few live runs would starve everything else that uses it: artifact long-polls,
# file reads, run building. Runs get their own pool.
_RUN_POOL = ThreadPoolExecutor(max_workers=32, thread_name_prefix="agentdev-run")



class WebSocketGraphExecutor(GraphExecutor):
    """GraphExecutor subclass that emits events via WebSocket."""

    def __init__(
        self,
        graph: GraphContext,
        session_id: str,
        session_controller: SessionExecutionController,
        attachment_service: AttachmentService,
        websocket_manager,
        session_store: WorkflowSessionStore,
        cancel_event=None,
        workspace_root=None,
        run_mode=DEFAULT_RUN_MODE,
    ):
        self.session_id = session_id
        # How much this turn asks the user before acting (the chat's mode menu)
        self.run_mode = normalize_run_mode(run_mode)
        self.session_controller = session_controller
        self.attachment_service = attachment_service
        self.websocket_manager = websocket_manager
        self.session_store = session_store
        self.results = {}
        # Set by WorkflowRunService: keeps the run's resume checkpoint up to date from log events.
        self.checkpoint_recorder = None
        self.artifact_dispatcher = ArtifactDispatcher(session_id, session_store, websocket_manager, local_root=workspace_root)

        def hook_factory(runtime_context):
            prompt_channel = WebPromptChannel(
                session_id=session_id,
                session_controller=session_controller,
                websocket_manager=websocket_manager,
                attachment_service=attachment_service,
                attachment_store=runtime_context.attachment_store,
                run_mode=self.run_mode,
            )
            return WorkspaceArtifactHook(
                attachment_store=runtime_context.attachment_store,
                emit_callback=self._handle_workspace_artifacts,
                prompt_channel=prompt_channel,
            )

        super().__init__(
            graph,
            session_id=session_id,
            workspace_hook_factory=hook_factory,
            cancel_event=cancel_event,
            workspace_root=workspace_root,
        )
        # Earlier turns of this session (this run's turn is added when it finishes): team leads
        # repeat a member's earlier reports in its brief (see team.get_team_state).
        self.runtime_context.global_state[RUN_MODE_KEY] = self.run_mode
        session = session_store.get_session(session_id) if session_store else None
        turns = list(getattr(session, "turns", None) or [])
        if turns:
            self.runtime_context.global_state[CONVERSATION_TURNS_KEY] = turns

    def _create_logger(self) -> WorkflowLogger:
        from agentdev.api.services.websocket_logger import WebSocketLogger

        return WebSocketLogger(
            self.websocket_manager,
            self.session_id,
            self.graph.name,
            self.graph.log_level,
            on_entry=self._on_log_entry,
        )

    def _on_log_entry(self, entry) -> None:
        recorder = getattr(self, "checkpoint_recorder", None)
        if recorder is not None:
            recorder.on_log(entry)

    async def execute_graph_async(self, task_prompt):
        await asyncio.get_running_loop().run_in_executor(_RUN_POOL, self._execute, task_prompt)

    def get_results(self):
        return self.outputs

    def _handle_workspace_artifacts(self, artifacts: List[WorkspaceArtifact]) -> None:
        self.artifact_dispatcher.emit_workspace_artifacts(artifacts)
