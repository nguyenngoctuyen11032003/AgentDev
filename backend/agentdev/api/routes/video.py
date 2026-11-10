"""Video helpers that need no Google API: per-shot prompts to paste into Google Flow ("Prompt cho Flow").

A Google AI subscription includes Veo only inside Flow and the Gemini app, not through the API AgentDev renders
with. This turns a production package into the exact prompts AgentDev would send to Veo, so the user can make the
clips in Flow with the plan they already pay for. Pure text in, text out: free, no model call.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from agentdev.connections.security import require_local_origin
from agentdev.utils.video_package import flow_prompts

MAX_TEXT = 2_000_000  # a production package is a few dozen KB; this only stops abuse


def _local_pages_only(request: Request) -> None:
    require_local_origin(request)


router = APIRouter(prefix="/api/video", tags=["video"], dependencies=[Depends(_local_pages_only)])


class FlowPromptsRequest(BaseModel):
    package: str = Field(..., max_length=MAX_TEXT)  # goi_san_xuat.md
    bible: str = Field("", max_length=MAX_TEXT)  # series/ho_so_nhan_vat.md (character looks), when there is one


@router.post("/flow-prompts")
async def video_flow_prompts(payload: FlowPromptsRequest) -> Dict[str, Any]:
    return await run_in_threadpool(flow_prompts, payload.package, payload.bible)
