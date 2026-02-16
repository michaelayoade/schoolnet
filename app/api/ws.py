"""WebSocket endpoint for real-time notifications."""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.services.auth_flow import decode_access_token
from app.services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


def _authenticate_ws(token: str) -> str | None:
    """Validate JWT token and return person_id or None."""
    if not token:
        return None
    db: Session = SessionLocal()
    try:
        payload = decode_access_token(db, token)
        return payload.get("sub")
    except Exception:
        return None
    finally:
        db.close()


@router.websocket("/ws/notifications")
async def ws_notifications(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time notification push.

    Authenticate via query param: /ws/notifications?token=<JWT>
    """
    token = websocket.query_params.get("token", "")
    person_id_str = _authenticate_ws(token)
    if not person_id_str:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    from uuid import UUID

    person_id = UUID(person_id_str)
    await ws_manager.connect(person_id, websocket)
    try:
        while True:
            # Keep connection alive; client can send pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(person_id, websocket)
    except Exception:
        ws_manager.disconnect(person_id, websocket)
