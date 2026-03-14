import json
import asyncio
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from typing import Dict
from dataclasses import asdict
from datetime import datetime, timezone

from ..services.proctoring.orchestrator import ProctoringOrchestrator
from ..services.proctoring.identity_detection import IdentityVerifier
from ..services.models.violation import ViolationEvent
from ..config import settings

proctoring_router = APIRouter(prefix="/proctoring", tags=["Proctoring"])


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

# ── Active session registry ───────────────────────────────────────────────────
# Keeps track of all active WebSocket sessions in memory
# active_sessions[session_id] = ProctoringOrchestrator
active_sessions: Dict[str, ProctoringOrchestrator] = {}


# ── Message types (contract between frontend and backend) ─────────────────────
# Frontend → Backend:
#   { "type": "enroll",       "session_id": "...", "candidate_id": "...", "image": "base64..." }
#   { "type": "frame",        "frame_id": "...",   "frame": "base64..." }
#   { "type": "client_violation", "violation_type": "tab_switch" | "fullscreen_exit" | ... }
#   { "type": "end_session" }
#
# Backend → Frontend:
#   { "type": "enrolled",     "success": true/false, "message": "..." }
#   { "type": "frame_result", "frame_id": "...", "has_violations": bool, "violations": [...], ... }
#   { "type": "session_flagged", "summary": {...} }
#   { "type": "session_summary", "summary": {...} }
#   { "type": "error",        "message": "..." }
#   { "type": "pong" }


@proctoring_router.websocket("/ws/{session_id}")
async def proctoring_websocket(websocket: WebSocket, session_id: str):
    """
    Main WebSocket endpoint for the proctoring pipeline.

    URL: ws://host/proctoring/ws/{session_id}

    One WebSocket connection per active assessment session.
    The frontend connects here as soon as the session starts,
    sends frames every 2-3 seconds, and listens for violation events.
    """
    await websocket.accept()
    logger.info(f"WebSocket connected | session={session_id}")

    orchestrator: ProctoringOrchestrator = None

    try:
        while True:
            # ── Receive message ───────────────────────────────
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

            # ── Route message type ────────────────────────────

            # 1. Enroll reference image
            if msg_type == "enroll":
                orchestrator = await _handle_enroll(
                    websocket, message, session_id
                )

            # 2. Analyze a frame
            elif msg_type == "frame":
                if orchestrator is None:
                    await _send_error(websocket, "Session not enrolled. Send 'enroll' message first.")
                    continue
                await _handle_frame(websocket, message, orchestrator)

            # 3. Client-side violation (tab switch, fullscreen exit, etc.)
            elif msg_type == "client_violation":
                if orchestrator is None:
                    await _send_error(websocket, "Session not enrolled.")
                    continue
                await _handle_client_violation(websocket, message, orchestrator)

            # 4. Ping / keepalive
            elif msg_type == "ping":
                await websocket.send_text(_dumps({"type": "pong"}))

            # 5. End session
            elif msg_type == "end_session":
                await _handle_end_session(websocket, orchestrator, session_id)
                break

            else:
                await _send_error(websocket, f"Unknown message type: {msg_type}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected | session={session_id}")

    except Exception as e:
        logger.error(f"WebSocket error | session={session_id} | error={e}")
        try:
            await _send_error(websocket, f"Internal server error: {str(e)}")
        except Exception:
            pass

    finally:
        # Always clean up regardless of how the connection ended
        if orchestrator:
            orchestrator.end_session()
        active_sessions.pop(session_id, None)
        logger.info(f"Session cleaned up | session={session_id}")


# ── Message handlers ──────────────────────────────────────────────────────────

async def _handle_enroll(
    websocket: WebSocket,
    message: dict,
    session_id: str,
) -> ProctoringOrchestrator:
    """
    Handle the enroll message.
    Creates the orchestrator for this session and enrolls the reference image.
    """
    candidate_id = message.get("candidate_id")
    reference_image_b64 = message.get("image")

    if not candidate_id or not reference_image_b64:
        await _send_error(websocket, "Enroll message requires 'candidate_id' and 'image'.")
        return None

    try:
        # Decode the reference image
        reference_image = IdentityVerifier.decode_base64_image(reference_image_b64)

        # Access shared CV models via websocket.app.state
        app_state = websocket.app.state

        # Create orchestrator for this session, injecting the shared CV models
        orchestrator = ProctoringOrchestrator(
            session_id=session_id,
            candidate_id=candidate_id,
            face_detector=app_state.face_detector,
            gaze_analyzer=app_state.gaze_analyzer,
            object_detector=app_state.object_detector,
            identity_verifier=app_state.identity_verifier,
        )

        # Enroll the reference image
        # Run in thread pool since DeepFace is CPU-bound / blocking
        success = await asyncio.get_running_loop().run_in_executor(
            None, orchestrator.enroll_reference, reference_image
        )

        if success:
            active_sessions[session_id] = orchestrator
            await websocket.send_text(_dumps({
                "type": "enrolled",
                "success": True,
                "message": "Reference image enrolled successfully. Session is ready.",
            }))
            logger.info(f"Session enrolled | session={session_id} | candidate={candidate_id}")
            return orchestrator
        else:
            await websocket.send_text(_dumps({
                "type": "enrolled",
                "success": False,
                "message": "No face detected in reference image. Please upload a clearer photo.",
            }))
            return None

    except Exception as e:
        logger.error(f"Enroll error | session={session_id} | {e}")
        await _send_error(websocket, f"Enrollment failed: {str(e)}")
        return None


async def _handle_frame(
    websocket: WebSocket,
    message: dict,
    orchestrator: ProctoringOrchestrator,
):
    """
    Handle an incoming video frame.
    Runs the full CV pipeline and sends back the result.
    """
    frame_id = message.get("frame_id", "unknown")
    frame_b64 = message.get("frame")

    if not frame_b64:
        await _send_error(websocket, "Frame message requires 'frame' field.")
        return

    # Run CV pipeline in thread pool — all CV ops are synchronous/CPU-bound
    # This prevents blocking the FastAPI event loop
    result = await asyncio.get_running_loop().run_in_executor(
        None, orchestrator.analyze_frame, frame_b64, frame_id
    )

    # Serialize violations
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

    # If session just got flagged, send a dedicated flagged event
    if result.session_flagged:
        summary = orchestrator.get_session_summary()
        await websocket.send_text(_dumps({
            "type": "session_flagged",
            "summary": summary,
        }))


async def _handle_client_violation(
    websocket: WebSocket,
    message: dict,
    orchestrator: ProctoringOrchestrator,
):
    """
    Handle violations detected client-side (tab switch, fullscreen exit, copy-paste).
    These come directly from the frontend — we log them via the violation builder.
    """
    from ..services.models.violation import ViolationType, VIOLATION_SEVERITY_MAP
    from ..services.proctoring.violation_builder import VIOLATION_MESSAGES

    violation_type_str = message.get("violation_type")

    if not violation_type_str:
        await _send_error(websocket, "client_violation message requires 'violation_type'.")
        return

    try:
        violation_type = ViolationType(violation_type_str)
    except ValueError:
        await _send_error(websocket, f"Unknown violation type: {violation_type_str}")
        return

    # Build and record the violation
    violation = orchestrator._violation_builder.build(
        session_id=orchestrator.session_id,
        candidate_id=orchestrator.candidate_id,
        violation_type=violation_type,
        metadata={"source": "client"},
    )

    # Acknowledge back to frontend
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


async def _handle_end_session(
    websocket: WebSocket,
    orchestrator: ProctoringOrchestrator,
    session_id: str,
):
    """
    Handle session end. Send summary and clean up.
    """
    if orchestrator:
        summary = orchestrator.get_session_summary()
        await websocket.send_text(_dumps({
            "type": "session_summary",
            "summary": summary,
        }))
        logger.info(f"Session ended | session={session_id} | summary={summary}")
    else:
        await websocket.send_text(_dumps({
            "type": "session_summary",
            "summary": {},
        }))


# ── Utility ───────────────────────────────────────────────────────────────────

async def _send_error(websocket: WebSocket, message: str):
    try:
        await websocket.send_text(_dumps({
            "type": "error",
            "message": message,
        }))
    except Exception:
        pass  # If we can't send the error, the connection is already broken


# ── REST endpoint to get active sessions (admin/debug use) ────────────────────

@proctoring_router.get("/active-sessions")
async def get_active_sessions():
    return {
        "active_session_count": len(active_sessions),
        "session_ids": list(active_sessions.keys()),
    }