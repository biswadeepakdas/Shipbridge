from typing import List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import structlog

router = APIRouter(prefix="/api/v1/ws", tags=["websocket"])
logger = structlog.get_logger()


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("websocket_connected", client_host=websocket.client.host)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info("websocket_disconnected", client_host=websocket.client.host)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)
        logger.info("websocket_broadcast", message=message, connections=len(self.active_connections))


manager = ConnectionManager()


@router.websocket("/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, or handle incoming messages if needed
            # For now, we just accept and keep it open for broadcasting from server
            await websocket.receive_text() # This will block until a message is received
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("websocket_client_disconnected", client_id=client_id)
    except Exception as e:
        logger.error("websocket_error", client_id=client_id, error=str(e))
        manager.disconnect(websocket)
