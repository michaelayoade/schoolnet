"""WebSocket endpoint for real-time notifications."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.services.auth_flow import decode_access_token
from app.services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


def _token_from_subprotocol(websocket: WebSocket) -> str:
    """Return the first WebSocket subprotocol value as bearer token."""
    offered = websocket.scope.get("subprotocols")
    if not isinstance(offered, list):
        return ""
    for value in offered:
        if isinstance(value, str) and value:
            return value
    return ""


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

    Authenticate via Sec-WebSocket-Protocol subprotocol value.
    """
    token = _token_from_subprotocol(websocket)
    person_id_str = _authenticate_ws(token)
    if not person_id_str:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    person_id = UUID(person_id_str)
    await ws_manager.connect(person_id, websocket, subprotocol=token)
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
