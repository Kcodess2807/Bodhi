"""Proctoring API endpoints — integrated with Bodhi interview sessions."""

from __future__ import annotations

import uuid
import numpy as np
import cv2
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from loguru import logger
from typing import Dict, Optional
from datetime import datetime, timezone
import json
import asyncio

router = APIRouter(prefix="/api/proctoring", tags=["Proctoring"])

# ── In-memory stores ──────────────────────────────────────────────────────────
# candidate_id -> numpy BGR image (reference photos)
_enrolled_photos: Dict[str, np.ndarray] = {}

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


# ── Enrollment Endpoints ──────────────────────────────────────────────────────

@router.post("/enroll-photo")
async def enroll_photo(
    request: Request,
    candidate_id: str = Form(None),
    file: UploadFile = File(..., description="Reference photo of the candidate (jpg/png)"),
):
    """
    Upload a reference photo for a candidate.
    
    - If `candidate_id` is not provided, one will be generated.
    - Returns the `candidate_id` to use in the WebSocket session.
    - The photo is stored in memory (will move to S3 later).
    """
    from procturing_backend.services.proctoring.identity_detection import IdentityVerifier

    # Validate file type
    if file.content_type not in ("image/jpeg", "image/png", "image/jpg", "image/webp"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {file.content_type}. Must be jpeg or png."
        )

    # Read and decode image
    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    img_array = np.frombuffer(contents, dtype=np.uint8)
    image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    if image is None:
        raise HTTPException(status_code=400, detail="Could not decode image. Please upload a valid photo.")

    # Generate candidate_id if not provided
    if not candidate_id:
        candidate_id = f"candidate-{uuid.uuid4().hex[:10]}"

    # Verify face is present using the shared identity verifier
    identity_verifier: IdentityVerifier = request.app.state.identity_verifier

    # Try to enroll
    success = identity_verifier.enroll(image, candidate_id)

    if not success:
        raise HTTPException(
            status_code=422,
            detail="No face detected in the uploaded photo. Please upload a clear, well-lit front-facing photo."
        )

    # Store in memory for WebSocket sessions to use
    _enrolled_photos[candidate_id] = image

    logger.info(f"Photo enrolled via REST | candidate_id={candidate_id} | file={file.filename}")

    return {
        "success": True,
        "candidate_id": candidate_id,
        "message": "Reference photo enrolled successfully.",
        "instructions": {
            "next_step": "Use this candidate_id in your WebSocket enroll message or interview session.",
            "websocket_url": f"/api/proctoring/ws/{{session_id}}",
        }
    }


@router.post("/verify-photo")
async def verify_photo(
    request: Request,
    candidate_id: str = Form(..., description="candidate_id returned from /enroll-photo"),
    file: UploadFile = File(..., description="Live photo to verify against the enrolled reference"),
):
    """
    Verify a live photo against the enrolled reference photo.
    
    This simulates exactly what the WebSocket proctoring pipeline does every 30 seconds.
    """
    from deepface import DeepFace
    from procturing_backend.config import settings

    if not candidate_id:
        raise HTTPException(status_code=400, detail="candidate_id is required.")

    # Check if candidate is enrolled
    if candidate_id not in _enrolled_photos:
        raise HTTPException(
            status_code=404,
            detail=f"No reference photo found for candidate_id: {candidate_id}. Call /enroll-photo first."
        )

    # Validate and decode live photo
    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    img_array = np.frombuffer(contents, dtype=np.uint8)
    live_image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    if live_image is None:
        raise HTTPException(status_code=400, detail="Could not decode live photo.")

    try:
        reference_image = _enrolled_photos[candidate_id]

        result = DeepFace.verify(
            img1_path=reference_image,
            img2_path=live_image,
            model_name=settings.FACE_RECOGNITION_MODEL,
            detector_backend="opencv",
            enforce_detection=False,
            align=True,
            normalization="ArcFace",
        )

        distance  = float(result["distance"])
        threshold = float(result["threshold"])
        verified  = distance <= settings.FACE_SIMILARITY_THRESHOLD
        confidence = max(0.0, min(1.0, 1.0 - (distance / (settings.FACE_SIMILARITY_THRESHOLD * 2))))

        logger.info(
            f"Photo verification via REST | candidate_id={candidate_id} "
            f"distance={distance:.4f} threshold={settings.FACE_SIMILARITY_THRESHOLD} "
            f"verified={verified} confidence={round(confidence, 3)}"
        )

        return {
            "candidate_id": candidate_id,
            "verified": verified,
            "confidence": round(confidence, 3),
            "distance": round(distance, 4),
            "our_threshold": settings.FACE_SIMILARITY_THRESHOLD,
            "model_threshold": round(threshold, 4),
            "model_used": settings.FACE_RECOGNITION_MODEL,
            "verdict": "✅ Same person" if verified else "❌ Different person or face not detected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Verification error | candidate_id={candidate_id} | {e}")
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")


@router.get("/enrolled-candidates")
async def list_enrolled_candidates():
    """List all currently enrolled candidates (in-memory)."""
    return {
        "count": len(_enrolled_photos),
        "candidate_ids": list(_enrolled_photos.keys()),
    }


@router.delete("/enrolled-candidates/{candidate_id}")
async def clear_candidate(candidate_id: str):
    """Remove an enrolled candidate from memory."""
    if candidate_id not in _enrolled_photos:
        raise HTTPException(status_code=404, detail=f"candidate_id not found: {candidate_id}")

    del _enrolled_photos[candidate_id]
    logger.info(f"Cleared enrolled photo for candidate_id={candidate_id}")

    return {"success": True, "message": f"Candidate {candidate_id} removed."}


# ── WebSocket Proctoring ──────────────────────────────────────────────────────

@router.websocket("/ws/{session_id}")
async def proctoring_websocket(websocket: WebSocket, session_id: str):
    """
    Main WebSocket endpoint for the proctoring pipeline.
    
    URL: ws://host/api/proctoring/ws/{session_id}
    
    One WebSocket connection per active assessment session.
    The frontend connects here as soon as the session starts,
    sends frames every 2-3 seconds, and listens for violation events.
    """
    from procturing_backend.services.proctoring.orchestrator import ProctoringOrchestrator
    from procturing_backend.services.proctoring.identity_detection import IdentityVerifier
    from procturing_backend.services.models.violation import ViolationType
    from procturing_backend.config import settings

    await websocket.accept()
    logger.info(f"Proctoring WebSocket connected | session={session_id}")

    orchestrator: Optional[ProctoringOrchestrator] = None

    try:
        while True:
            # Receive message
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

            # Route message type
            if msg_type == "enroll":
                orchestrator = await _handle_enroll(websocket, message, session_id)

            elif msg_type == "frame":
                if orchestrator is None:
                    await _send_error(websocket, "Session not enrolled. Send 'enroll' message first.")
                    continue
                await _handle_frame(websocket, message, orchestrator)

            elif msg_type == "client_violation":
                if orchestrator is None:
                    await _send_error(websocket, "Session not enrolled.")
                    continue
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
        # Clean up
        if orchestrator:
            orchestrator.end_session()
        _active_proctoring_sessions.pop(session_id, None)
        logger.info(f"Proctoring session cleaned up | session={session_id}")


# ── WebSocket Message Handlers ────────────────────────────────────────────────

async def _handle_enroll(
    websocket: WebSocket,
    message: dict,
    session_id: str,
):
    """Handle the enroll message."""
    from procturing_backend.services.proctoring.orchestrator import ProctoringOrchestrator
    from procturing_backend.services.proctoring.identity_detection import IdentityVerifier

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

        # Create orchestrator for this session
        orchestrator = ProctoringOrchestrator(
            session_id=session_id,
            candidate_id=candidate_id,
            face_detector=app_state.face_detector,
            gaze_analyzer=app_state.gaze_analyzer,
            object_detector=app_state.object_detector,
            identity_verifier=app_state.identity_verifier,
        )

        # Enroll the reference image
        success = await asyncio.get_running_loop().run_in_executor(
            None, orchestrator.enroll_reference, reference_image
        )

        if success:
            _active_proctoring_sessions[session_id] = orchestrator
            await websocket.send_text(_dumps({
                "type": "enrolled",
                "success": True,
                "message": "Reference image enrolled successfully. Proctoring is active.",
            }))
            logger.info(f"Proctoring session enrolled | session={session_id} | candidate={candidate_id}")
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


async def _handle_frame(websocket: WebSocket, message: dict, orchestrator):
    """Handle an incoming video frame."""
    from procturing_backend.config import settings

    frame_id = message.get("frame_id", "unknown")
    frame_b64 = message.get("frame")

    if not frame_b64:
        await _send_error(websocket, "Frame message requires 'frame' field.")
        return

    # Run CV pipeline in thread pool
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
