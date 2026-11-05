"""WebSocket endpoint routing."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agentdev.connections.security import origin_allowed
from agentdev.api.state import get_websocket_manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, session_id: str = "", client: str = "", seq: int = 0):
    if not origin_allowed(websocket.headers.get("origin")):
        await websocket.close(code=1008)
        return
    manager = get_websocket_manager()
    sid = await manager.connect(websocket, session_id=session_id or None, client_id=client or None, seq=seq)
    try:
        while True:
            message = await websocket.receive_text()
            await manager.handle_message(sid, message)
    except WebSocketDisconnect:
        manager.disconnect(sid, websocket)
