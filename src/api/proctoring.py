"""Proctoring API endpoints — integrated with Bodhi interview sessions."""

from __future__ import annotations

import numpy as np
import cv2
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from loguru import logger
from typing import Dict, Optional
from datetime import datetime, timezone
import json
import asyncio

router = APIRouter(prefix="/api/proctoring", tags=["Proctoring"])

# session_id -> ProctoringOrchestrator (active proctoring sessions)
_active_proctoring_sessions: Dict[str, any] = {}


class _NumpyEncoder(json.JSONEncoder):
    """Handles numpy scalar types that CV models return."""
    def default(self, obj):
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def _dumps(obj) -> str:
    return json.dumps(obj, cls=_NumpyEncoder)


# ── WebSocket Proctoring ──────────────────────────────────────────────────────

@router.websocket("/ws/{session_id}")
async def proctoring_websocket(websocket: WebSocket, session_id: str):
    """
    Main WebSocket endpoint for the proctoring pipeline.

    URL: ws://host/api/proctoring/ws/{session_id}

    One WebSocket connection per active assessment session.
    The frontend connects here as soon as the session starts,
    sends frames every 2-3 seconds, and listens for violation events.
    No enrollment step required — identity comparison is disabled.
    """
    from procturing_backend.services.proctoring.orchestrator import ProctoringOrchestrator

    await websocket.accept()
    logger.info(f"Proctoring WebSocket connected | session={session_id}")

    app_state = websocket.app.state
    orchestrator = ProctoringOrchestrator(
        session_id=session_id,
        candidate_id=session_id,
        face_detector=app_state.face_detector,
        gaze_analyzer=app_state.gaze_analyzer,
        object_detector=app_state.object_detector,
    )
    _active_proctoring_sessions[session_id] = orchestrator

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await _send_error(websocket, "Invalid JSON format.")
                continue

            msg_type = message.get("type")

            if not msg_type:
                await _send_error(websocket, "Message missing 'type' field.")
                continue

            if msg_type == "frame":
                await _handle_frame(websocket, message, orchestrator)

            elif msg_type == "client_violation":
                await _handle_client_violation(websocket, message, orchestrator)

            elif msg_type == "ping":
                await websocket.send_text(_dumps({"type": "pong"}))

            elif msg_type == "end_session":
                await _handle_end_session(websocket, orchestrator, session_id)
                break

            else:
                await _send_error(websocket, f"Unknown message type: {msg_type}")

    except WebSocketDisconnect:
        logger.info(f"Proctoring WebSocket disconnected | session={session_id}")

    except Exception as e:
        logger.error(f"Proctoring WebSocket error | session={session_id} | error={e}")
        try:
            await _send_error(websocket, f"Internal server error: {str(e)}")
        except Exception:
            pass

    finally:
        if orchestrator:
            orchestrator.end_session()
        _active_proctoring_sessions.pop(session_id, None)
        logger.info(f"Proctoring session cleaned up | session={session_id}")


# ── WebSocket Message Handlers ────────────────────────────────────────────────

async def _handle_frame(websocket: WebSocket, message: dict, orchestrator):
    """Handle an incoming video frame."""
    from procturing_backend.config import settings

    frame_id = message.get("frame_id", "unknown")
    frame_b64 = message.get("frame")

    if not frame_b64:
        await _send_error(websocket, "Frame message requires 'frame' field.")
        return

    result = await asyncio.get_running_loop().run_in_executor(
        None, orchestrator.analyze_frame, frame_b64, frame_id
    )

    violations_payload = [
        {
            "violation_type": v.violation_type.value,
            "severity": v.severity.value,
            "message": v.message,
            "timestamp": v.timestamp.isoformat(),
        }
        for v in result.violations
    ]

    response = {
        "type": "frame_result",
        "frame_id": result.frame_id,
        "has_violations": result.has_violations,
        "violations": violations_payload,
        "session_flagged": result.session_flagged,
        "processing_time_ms": result.processing_time_ms,
        "analysis": result.analysis if settings.DEBUG else None,
    }

    await websocket.send_text(_dumps(response))

    if result.session_flagged:
        summary = orchestrator.get_session_summary()
        await websocket.send_text(_dumps({
            "type": "session_flagged",
            "summary": summary,
        }))


async def _handle_client_violation(websocket: WebSocket, message: dict, orchestrator):
    """Handle violations detected client-side."""
    from procturing_backend.services.models.violation import ViolationType

    violation_type_str = message.get("violation_type")

    if not violation_type_str:
        await _send_error(websocket, "client_violation message requires 'violation_type'.")
        return

    try:
        violation_type = ViolationType(violation_type_str)
    except ValueError:
        await _send_error(websocket, f"Unknown violation type: {violation_type_str}")
        return

    violation = orchestrator._violation_builder.build(
        session_id=orchestrator.session_id,
        candidate_id=orchestrator.candidate_id,
        violation_type=violation_type,
        metadata={"source": "client"},
    )

    await websocket.send_text(_dumps({
        "type": "client_violation_ack",
        "violation_type": violation_type.value,
        "severity": violation.severity.value,
        "session_flagged": orchestrator._violation_builder.is_session_flagged(
            orchestrator.session_id
        ),
    }))

    logger.info(
        f"Client violation logged | session={orchestrator.session_id} "
        f"type={violation_type.value}"
    )


async def _handle_end_session(websocket: WebSocket, orchestrator, session_id: str):
    """Handle session end. Send summary and clean up."""
    if orchestrator:
        summary = orchestrator.get_session_summary()
        await websocket.send_text(_dumps({
            "type": "session_summary",
            "summary": summary,
        }))
        logger.info(f"Proctoring session ended | session={session_id} | summary={summary}")
    else:
        await websocket.send_text(_dumps({
            "type": "session_summary",
            "summary": {},
        }))


async def _send_error(websocket: WebSocket, message: str):
    try:
        await websocket.send_text(_dumps({
            "type": "error",
            "message": message,
        }))
    except Exception:
        pass


# ── Session Management ────────────────────────────────────────────────────────

@router.get("/active-sessions")
async def get_active_proctoring_sessions():
    """Get all active proctoring sessions (admin/debug use)."""
    return {
        "active_session_count": len(_active_proctoring_sessions),
        "session_ids": list(_active_proctoring_sessions.keys()),
    }


@router.get("/session/{session_id}/summary")
async def get_session_summary(session_id: str):
    """Get proctoring summary for a specific session."""
    if session_id not in _active_proctoring_sessions:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found or already ended.")

    orchestrator = _active_proctoring_sessions[session_id]
    summary = orchestrator.get_session_summary()

    return {
        "session_id": session_id,
        "summary": summary,
    }
