import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState
import structlog

from app.services.auth import JWTError, decode_access_token

router = APIRouter(prefix="/api/v1/ws", tags=["websocket"])
logger = structlog.get_logger()


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info("websocket_connected", client_host=websocket.client.host if websocket.client else "unknown")

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            try:
                self.active_connections.remove(websocket)
            except ValueError:
                pass
        logger.info("websocket_disconnected", client_host=websocket.client.host if websocket.client else "unknown")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        async with self._lock:
            connections = list(self.active_connections)
        for connection in connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass
        logger.info("websocket_broadcast", connections=len(connections))


manager = ConnectionManager()


@router.websocket("/{client_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str,
    token: str = Query(default=""),
):
    # Authenticate before accepting the connection
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    try:
        payload = decode_access_token(token)
    except (JWTError, KeyError, Exception) as exc:
        await websocket.close(code=4001, reason="Invalid or expired token")
        logger.warning("websocket_auth_failed", client_id=client_id, error=str(exc))
        return

    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
        logger.info("websocket_client_disconnected", client_id=client_id, user_id=payload.sub)
    except Exception as e:
        logger.error("websocket_error", client_id=client_id, error=str(e))
        await manager.disconnect(websocket)
