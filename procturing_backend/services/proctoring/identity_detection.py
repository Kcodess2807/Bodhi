import numpy as np
import cv2
import base64
from deepface import DeepFace
from loguru import logger
from dataclasses import dataclass
from typing import Optional
from ...config import settings


@dataclass
class IdentityVerificationResult:
    verified: bool
    confidence: float                    # 0.0 to 1.0, higher = more confident it's the same person
    distance: float                      # Raw model distance, lower = more similar
    threshold: float                     # Model's threshold used for this comparison
    model_used: str
    error: Optional[str] = None          # Set if verification failed due to an error


class IdentityVerifier:
    """
    Verifies whether the person in the current frame matches
    the reference photo uploaded at the start of the session.

    Uses DeepFace with configurable backend model.

    Two modes:
      1. enroll()  — called once at session start, stores the reference embedding
      2. verify()  — called periodically during session, compares live frame to reference

    We store the reference image in memory as a numpy array.
    No DB interaction here — that's handled by the orchestrator/session layer later.
    """

    def __init__(self):
        logger.info(f"Initializing IdentityVerifier (model: {settings.FACE_RECOGNITION_MODEL})...")
        self._model_name = settings.FACE_RECOGNITION_MODEL
        self._threshold = settings.FACE_SIMILARITY_THRESHOLD

        # Reference image stored per session in memory
        # In production this will be keyed by session_id
        # For now it's a single reference (one active session per verifier instance)
        self._reference_image: Optional[np.ndarray] = None
        self._reference_session_id: Optional[str] = None

        # Warm up the model — DeepFace lazy loads on first call
        # We trigger it here at startup so the first verify() isn't slow
        self._warmup()
        logger.info("IdentityVerifier ready.")

    def _warmup(self):
        """
        Force DeepFace to load the model weights at startup.
        Creates a blank dummy image and runs a single verification to trigger model load.
        """
        try:
            logger.info(f"Warming up DeepFace model: {self._model_name}...")
            dummy = np.zeros((224, 224, 3), dtype=np.uint8)
            # This will fail (no face in blank image) but still loads the model weights
            DeepFace.represent(
                img_path=dummy,
                model_name=self._model_name,
                enforce_detection=False,
            )
            logger.info("DeepFace model warmed up.")
        except Exception as e:
            # Expected to fail on blank image, that's fine
            logger.info(f"Warmup complete (expected error suppressed): {type(e).__name__}")

    def enroll(self, reference_image: np.ndarray, session_id: str) -> bool:
        """
        Store the reference image for a session.
        Called once when the candidate uploads their photo and session begins.

        Args:
            reference_image: BGR numpy array of the reference photo
            session_id: The active session ID

        Returns:
            True if a face was detected in the reference image, False otherwise
        """
        try:
            # First try strict detection
            try:
                faces = DeepFace.extract_faces(
                    img_path=reference_image,
                    detector_backend="opencv",
                    enforce_detection=True,
                )
                if not faces:
                    raise ValueError("No faces returned")
            except Exception:
                # Fall back to lenient detection — still enroll but log the warning
                logger.warning(
                    f"Strict face detection failed for session {session_id}. "
                    f"Falling back to lenient detection."
                )
                faces = DeepFace.extract_faces(
                    img_path=reference_image,
                    detector_backend="opencv",
                    enforce_detection=False,
                )
                if not faces:
                    logger.warning(f"No face found in reference image for session {session_id}")
                    return False

            self._reference_image = reference_image.copy()
            self._reference_session_id = session_id
            logger.info(f"Reference image enrolled for session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Enrollment failed for session {session_id}: {e}")
            return False

    def verify(self, live_frame: np.ndarray, session_id: str) -> IdentityVerificationResult:
        """
        Compare the live frame against the enrolled reference image.

        Args:
            live_frame: BGR numpy array of the current camera frame
            session_id: Must match the enrolled session

        Returns:
            IdentityVerificationResult with match details
        """
        # ── Guard checks ─────────────────────────────────────
        if self._reference_image is None:
            return IdentityVerificationResult(
                verified=False,
                confidence=0.0,
                distance=1.0,
                threshold=self._threshold,
                model_used=self._model_name,
                error="No reference image enrolled. Call enroll() first.",
            )

        if self._reference_session_id != session_id:
            return IdentityVerificationResult(
                verified=False,
                confidence=0.0,
                distance=1.0,
                threshold=self._threshold,
                model_used=self._model_name,
                error=f"Session mismatch. Enrolled: {self._reference_session_id}, Got: {session_id}",
            )

        try:
            result = DeepFace.verify(
                img1_path=self._reference_image,
                img2_path=live_frame,
                model_name=self._model_name,
                detector_backend="opencv",   # Fastest detector backend
                enforce_detection=True,      # Must find a face in both images
                align=True,                  # Align faces before comparison (improves accuracy)
            )

            distance = float(result["distance"])
            threshold = float(result["threshold"])
            verified = result["verified"]

            # Convert distance to a 0-1 confidence score
            # Distance 0.0 = identical, threshold = boundary, above = different person
            # We map: 0 distance → 1.0 confidence, threshold distance → 0.5 confidence
            confidence = max(0.0, min(1.0, 1.0 - (distance / (threshold * 2))))

            return IdentityVerificationResult(
                verified=verified,
                confidence=round(confidence, 3),
                distance=round(distance, 4),
                threshold=round(threshold, 4),
                model_used=self._model_name,
            )

        except ValueError as e:
            # DeepFace raises ValueError when no face is detected in the live frame
            error_msg = str(e)
            logger.warning(f"No face detected in live frame for session {session_id}: {error_msg}")
            return IdentityVerificationResult(
                verified=False,
                confidence=0.0,
                distance=1.0,
                threshold=self._threshold,
                model_used=self._model_name,
                error="no_face_in_frame",
            )

        except Exception as e:
            logger.error(f"Identity verification error for session {session_id}: {e}")
            return IdentityVerificationResult(
                verified=False,
                confidence=0.0,
                distance=1.0,
                threshold=self._threshold,
                model_used=self._model_name,
                error=str(e),
            )

    def clear_session(self, session_id: str):
        """
        Clear the enrolled reference image when a session ends.
        """
        if self._reference_session_id == session_id:
            self._reference_image = None
            self._reference_session_id = None
            logger.info(f"Cleared reference image for session {session_id}")

    @staticmethod
    def decode_base64_image(base64_str: str) -> np.ndarray:
        """
        Utility: Decode a base64 encoded image string to a BGR numpy array.
        Useful for decoding the reference photo uploaded from the frontend.
        """
        try:
            # Strip data URL prefix if present (e.g. "data:image/jpeg;base64,...")
            if "," in base64_str:
                base64_str = base64_str.split(",")[1]

            img_bytes = base64.b64decode(base64_str)
            img_array = np.frombuffer(img_bytes, dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if frame is None:
                raise ValueError("Failed to decode image from base64")

            return frame

        except Exception as e:
            logger.error(f"Base64 image decode error: {e}")
            raise