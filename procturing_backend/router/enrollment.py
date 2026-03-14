import uuid
import numpy as np
import cv2
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger
from typing import Dict
from datetime import datetime, timezone

from procturing_backend.services.proctoring.identity_detection import IdentityVerifier

enrollment_router = APIRouter(prefix="/proctoring", tags=["Identity Enrollment"])

# ── In-memory store ───────────────────────────────────────────────────────────
# candidate_id -> numpy BGR image
# This will be replaced with S3 + MongoDB later
_enrolled_photos: Dict[str, np.ndarray] = {}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@enrollment_router.post("/enroll-photo")
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

    **Test flow via /docs:**
    1. Call this endpoint with your photo → get back a `candidate_id`
    2. Open the WebSocket at `/proctoring/ws/{session_id}`
    3. Send enroll message with the returned `candidate_id`
    """

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
            "next_step": "Use this candidate_id in your WebSocket enroll message.",
            "websocket_url": f"ws://localhost:8000/proctoring/ws/{{session_id}}",
            "enroll_message": {
                "type": "enroll",
                "candidate_id": candidate_id,
                "image": "<base64 encoded live frame from webcam>",
            }
        }
    }


@enrollment_router.post("/verify-photo")
async def verify_photo(
    request: Request,
    candidate_id: str = Form(..., description="candidate_id returned from /enroll-photo"),
    file: UploadFile = File(..., description="Live photo to verify against the enrolled reference"),
):
    """
    Verify a live photo against the enrolled reference photo.

    **Test flow via /docs:**
    1. First call `/enroll-photo` with your reference photo
    2. Then call this endpoint with a different (live) photo of yourself
    3. See the verification result — distance, confidence, and verified status

    This simulates exactly what the WebSocket proctoring pipeline does every 30 seconds.
    """

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

    # Directly compare stored reference image against live image
    # We bypass the verifier's internal session state since this is a REST endpoint
    # and do a direct DeepFace comparison instead
    try:
        from deepface import DeepFace
        from procturing_backend.config import settings

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


@enrollment_router.post("/debug-verify")
async def debug_verify(
    reference: UploadFile = File(..., description="Reference photo"),
    live: UploadFile = File(..., description="Live photo to compare"),
):
    """
    Raw DeepFace comparison — no session state, no threshold logic.
    Upload both photos directly and get the raw distance back.
    Use this to find the right threshold for your conditions.
    """
    from deepface import DeepFace
    from procturing_backend.config import settings

    # Decode both images
    ref_bytes = await reference.read()
    live_bytes = await live.read()

    ref_arr  = np.frombuffer(ref_bytes, dtype=np.uint8)
    live_arr = np.frombuffer(live_bytes, dtype=np.uint8)

    ref_img  = cv2.imdecode(ref_arr, cv2.IMREAD_COLOR)
    live_img = cv2.imdecode(live_arr, cv2.IMREAD_COLOR)

    if ref_img is None or live_img is None:
        raise HTTPException(status_code=400, detail="Could not decode one or both images.")

    results = {}

    # Test all 3 best models so you can compare
    for model in ["Facenet512", "SFace", "GhostFaceNet"]:
        try:
            r = DeepFace.verify(
                img1_path=ref_img,
                img2_path=live_img,
                model_name=model,
                detector_backend="opencv",
                enforce_detection=False,
                align=True,
            )
            results[model] = {
                "distance":        round(float(r["distance"]), 4),
                "model_threshold": round(float(r["threshold"]), 4),
                "deepface_says":   r["verified"],
            }
        except Exception as e:
            results[model] = {"error": str(e)}

    return {
        "instruction": "Look at the distances. Same person should be low (~0.3-0.5), different person should be high (~0.7+). Set your threshold between the two.",
        "current_our_threshold": settings.FACE_SIMILARITY_THRESHOLD,
        "models": results,
    }
@enrollment_router.get("/enrolled-candidates")
async def list_enrolled_candidates():
    """
    List all currently enrolled candidates (in-memory).
    Useful for debugging during development.
    """
    return {
        "count": len(_enrolled_photos),
        "candidate_ids": list(_enrolled_photos.keys()),
    }


@enrollment_router.delete("/enrolled-candidates/{candidate_id}")
async def clear_candidate(candidate_id: str):
    """
    Remove an enrolled candidate from memory.
    """
    if candidate_id not in _enrolled_photos:
        raise HTTPException(status_code=404, detail=f"candidate_id not found: {candidate_id}")

    del _enrolled_photos[candidate_id]
    logger.info(f"Cleared enrolled photo for candidate_id={candidate_id}")

    return {"success": True, "message": f"Candidate {candidate_id} removed."}