"""Router: /api/test/behavioral-analysis and /api/test/health."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from behavioral_analysis.schemas.analysis import AnalysisResponse
from behavioral_analysis.services import posture_service, speech_service

router = APIRouter(prefix="/api/test", tags=["behavioral-analysis"])

# ── Input validation helpers ──────────────────────────────────────────────────

_AUDIO_EXTS = {".wav", ".webm", ".mp3", ".ogg", ".m4a"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def _check_audio(file: UploadFile) -> None:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _AUDIO_EXTS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported audio format '{ext}'. "
                f"Accepted: {', '.join(sorted(_AUDIO_EXTS))}"
            ),
        )


def _check_image(file: UploadFile) -> None:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _IMAGE_EXTS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported image format '{ext}'. "
                f"Accepted: {', '.join(sorted(_IMAGE_EXTS))}"
            ),
        )


# ── Health endpoint ───────────────────────────────────────────────────────────


@router.get("/health", summary="Model readiness check")
def health() -> dict:
    """Returns the load status of all models and whether Sarvam is configured.

    Call this before running analysis to confirm everything is initialised.
    Hit once to trigger lazy loading — subsequent calls return instantly.
    """
    # Trigger model loading if not already done
    speech_service.load_models()
    posture_service.load_models()

    speech_ok = speech_service.models_ready()
    posture_ok = posture_service.models_ready()

    return {
        "status": "ok" if (speech_ok and posture_ok) else "degraded",
        "models": {
            "speech_emotion": "loaded" if speech_ok else "not_loaded",
            "speech_sentiment": "loaded" if speech_ok else "not_loaded",
            "mediapipe_pose": "loaded" if posture_ok else "not_loaded",
            "mediapipe_face_mesh": "loaded" if posture_ok else "not_loaded",
        },
        "sarvam_configured": bool(os.getenv("SARVAM_API_KEY")),
    }


# ── Main analysis endpoint ────────────────────────────────────────────────────


@router.post(
    "/behavioral-analysis",
    response_model=AnalysisResponse,
    summary="Run speech + posture analysis on an audio/image pair",
)
async def behavioral_analysis(
    audio_file: UploadFile = File(..., description=".wav or .webm audio file"),
    image_file: UploadFile = File(..., description=".jpg or .png webcam frame"),
) -> AnalysisResponse:
    """Analyse a candidate's audio response and webcam frame in one request.

    Both analyses run independently — if one fails, the other still returns
    and the failure message appears in the `errors` field of the response.

    **Request** (multipart/form-data):
    - `audio_file` — recorded speech (.wav recommended, .webm supported)
    - `image_file` — single webcam frame (.jpg or .png)

    **Response** — unified JSON with `speech`, `posture`, and `errors` keys.
    """
    # Validate file types before reading content
    _check_audio(audio_file)
    _check_image(image_file)

    audio_bytes = await audio_file.read()
    image_bytes = await image_file.read()

    errors: dict[str, str] = {}
    speech_result = None
    posture_result = None

    # ── Speech analysis ───────────────────────────────────────────────────────
    try:
        speech_data = speech_service.analyze_speech(
            audio_bytes, audio_file.filename or "audio.wav"
        )
        from behavioral_analysis.schemas.analysis import SpeechResult
        speech_result = SpeechResult(**speech_data)
    except Exception as exc:
        errors["speech"] = str(exc)

    # ── Posture analysis ──────────────────────────────────────────────────────
    try:
        posture_data = posture_service.analyze_posture(image_bytes)
        from behavioral_analysis.schemas.analysis import PostureResult
        posture_result = PostureResult(**posture_data)
    except Exception as exc:
        errors["posture"] = str(exc)

    return AnalysisResponse(
        status="ok" if not errors else "partial",
        speech=speech_result,
        posture=posture_result,
        errors=errors,
    )
