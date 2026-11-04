"""WebSocket endpoint routing."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agentdev.api.state import get_websocket_manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, session_id: str = "", client: str = "", seq: int = 0):
    manager = get_websocket_manager()
    sid = await manager.connect(websocket, session_id=session_id or None, client_id=client or None, seq=seq)
    try:
        while True:
            message = await websocket.receive_text()
            await manager.handle_message(sid, message)
    except WebSocketDisconnect:
        manager.disconnect(sid, websocket)
