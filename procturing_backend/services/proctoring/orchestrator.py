import numpy as np
import cv2
import base64
import time
from loguru import logger
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field

from .face_detection import FaceDetector, FaceDetectionResult
from .gaze_analysis import GazeAnalyzer, GazeAnalysisResult
from .object_detection import ObjectDetector, ObjectDetectionResult
from .identity_detection import IdentityVerifier, IdentityVerificationResult
from .violation_builder import ViolationBuilder
from ..models.violation import (
    Violation,
    ViolationEvent,
    ViolationType,
    FrameAnalysisResult,
)
from ...config import settings


@dataclass
class OrchestratorResult:
    """
    The final result returned after analyzing a single frame.
    This is what gets serialized and sent back to the frontend over WebSocket.
    """
    frame_id: str                               # Echo back so frontend can match response to request
    session_id: str
    violations: List[ViolationEvent] = field(default_factory=list)
    has_violations: bool = False
    session_flagged: bool = False
    analysis: Optional[Dict[str, Any]] = None  # Debug info (can be stripped in production)
    processing_time_ms: float = 0.0


class ProctoringOrchestrator:
    """
    The central coordinator of the CV pipeline.

    Per frame it:
      1. Decodes the incoming base64 frame
      2. Runs face detection (every frame)
      3. Runs gaze analysis (every frame)
      4. Runs object detection (every frame)
      5. Runs identity verification (every N seconds)
      6. Collects all violations
      7. Builds violation events for the frontend
      8. Returns a structured OrchestratorResult

    One orchestrator instance is created per active WebSocket session.
    """

    def __init__(
        self,
        session_id: str,
        candidate_id: str,
        face_detector: FaceDetector,
        gaze_analyzer: GazeAnalyzer,
        object_detector: ObjectDetector,
        identity_verifier: IdentityVerifier,
    ):
        self.session_id = session_id
        self.candidate_id = candidate_id

        # Injected from app.state (shared across sessions, models are stateless)
        self._face_detector = face_detector
        self._gaze_analyzer = gaze_analyzer
        self._object_detector = object_detector
        self._identity_verifier = identity_verifier

        # Each session gets its own violation builder (tracks state per session)
        self._violation_builder = ViolationBuilder(
            auto_flag_threshold=settings.VIOLATION_AUTO_FLAG_COUNT
        )

        # Identity re-verification timing
        self._last_identity_check: float = 0.0
        self._identity_reverify_interval = settings.IDENTITY_REVERIFY_INTERVAL

        # Consecutive gaze deviation counter
        # We only flag gaze after N consecutive deviations to avoid false positives
        self._consecutive_gaze_deviations = 0
        self._gaze_deviation_trigger = 3   # Flag after 3 consecutive deviations

        # Consecutive no-face counter
        self._consecutive_no_face = 0
        self._no_face_trigger = 2          # Flag after 2 consecutive no-face frames

        logger.info(f"ProctoringOrchestrator initialized for session {session_id}")

    # ── Public API ────────────────────────────────────────────────────────────

    def enroll_reference(self, reference_image: np.ndarray) -> bool:
        """
        Enroll the candidate's reference photo.
        Must be called before analyze_frame().
        """
        success = self._identity_verifier.enroll(reference_image, self.session_id)
        if success:
            logger.info(f"Reference image enrolled for session {self.session_id}")
        else:
            logger.warning(f"Reference image enrollment failed for session {self.session_id}")
        return success

    def analyze_frame(self, frame_b64: str, frame_id: str) -> OrchestratorResult:
        """
        Main entry point. Takes a base64 encoded frame from the frontend,
        runs the full CV pipeline, and returns an OrchestratorResult.
        """
        start_time = time.perf_counter()

        try:
            # ── 1. Decode frame ───────────────────────────────
            frame = self._decode_frame(frame_b64)
            if frame is None:
                return self._error_result(frame_id, "Failed to decode frame")

            # ── 2. Run CV pipeline ────────────────────────────
            face_result = self._face_detector.analyze(frame)
            gaze_result = self._gaze_analyzer.analyze(frame)
            object_result = self._object_detector.analyze(frame)
            identity_result = self._run_identity_check(frame)

            # ── 3. Collect violations ─────────────────────────
            violation_types = self._collect_violations(
                face_result, gaze_result, object_result, identity_result
            )

            # ── 4. Build violation objects ────────────────────
            violations_full = self._violation_builder.build_multiple(
                session_id=self.session_id,
                candidate_id=self.candidate_id,
                violation_types=violation_types,
                metadata=self._build_metadata(face_result, gaze_result, object_result),
            )

            violation_events = self._violation_builder.build_events_from_violations(
                violations_full
            )

            # ── 5. Build result ───────────────────────────────
            processing_time = (time.perf_counter() - start_time) * 1000

            return OrchestratorResult(
                frame_id=frame_id,
                session_id=self.session_id,
                violations=violation_events,
                has_violations=len(violation_events) > 0,
                session_flagged=self._violation_builder.is_session_flagged(self.session_id),
                analysis=self._build_analysis_debug(
                    face_result, gaze_result, object_result, identity_result
                ),
                processing_time_ms=round(processing_time, 2),
            )

        except Exception as e:
            logger.error(f"Orchestrator error for session {self.session_id}: {e}")
            return self._error_result(frame_id, str(e))

    def get_session_summary(self) -> Dict[str, Any]:
        return self._violation_builder.get_session_summary(self.session_id)

    def end_session(self):
        """Clean up all in-memory state for this session."""
        self._violation_builder.clear_session(self.session_id)
        self._identity_verifier.clear_session(self.session_id)
        logger.info(f"Session {self.session_id} ended and cleaned up.")

    # ── CV Pipeline steps ─────────────────────────────────────────────────────

    def _run_identity_check(self, frame: np.ndarray) -> Optional[IdentityVerificationResult]:
        """
        Only run identity verification every IDENTITY_REVERIFY_INTERVAL seconds.
        Returns None if it's not time to check yet.
        """
        now = time.time()
        if now - self._last_identity_check < self._identity_reverify_interval:
            return None

        self._last_identity_check = now
        result = self._identity_verifier.verify(frame, self.session_id)
        logger.debug(
            f"Identity check | session={self.session_id} "
            f"verified={result.verified} confidence={result.confidence}"
        )
        return result

    def _collect_violations(
        self,
        face: FaceDetectionResult,
        gaze: GazeAnalysisResult,
        objects: ObjectDetectionResult,
        identity: Optional[IdentityVerificationResult],
    ) -> List[ViolationType]:
        """
        Evaluate all CV results and return a list of ViolationTypes for this frame.
        This is where all the decision logic lives.
        """
        violations = []

        # ── Face checks ───────────────────────────────────────
        if not face.has_face:
            self._consecutive_no_face += 1
            if self._consecutive_no_face >= self._no_face_trigger:
                violations.append(ViolationType.NO_FACE_DETECTED)
        else:
            self._consecutive_no_face = 0  # Reset on face detected

        if face.has_face and face.face_count > 1:
            violations.append(ViolationType.MULTIPLE_FACES)

        if face.has_face and not face.is_centered:
            violations.append(ViolationType.FACE_NOT_CENTERED)

        # ── Gaze checks ───────────────────────────────────────
        if not gaze.is_looking_at_screen:
            self._consecutive_gaze_deviations += 1
            if self._consecutive_gaze_deviations >= self._gaze_deviation_trigger:
                # Distinguish between a glance and actively looking away
                if abs(gaze.horizontal_deviation) > settings.GAZE_DEVIATION_THRESHOLD * 1.5:
                    violations.append(ViolationType.LOOKING_AWAY)
                else:
                    violations.append(ViolationType.GAZE_DEVIATION)
        else:
            self._consecutive_gaze_deviations = 0  # Reset on attention restored

        # ── Object detection checks ───────────────────────────
        if objects.multiple_people:
            # Already caught by face_count > 1 in most cases,
            # but YOLO gives us a second signal — use the stricter one
            if ViolationType.MULTIPLE_FACES not in violations:
                violations.append(ViolationType.MULTIPLE_FACES)

        for obj in objects.prohibited_objects:
            violation_type_str = self._object_detector.PROHIBITED_CLASSES.get(obj.label)
            if violation_type_str:
                try:
                    vtype = ViolationType(violation_type_str)
                    if vtype not in violations:
                        violations.append(vtype)
                except ValueError:
                    violations.append(ViolationType.UNAUTHORIZED_OBJECT)

        # ── Identity check ────────────────────────────────────
        if identity is not None:
            if identity.error == "no_face_in_frame":
                # Already handled by face detection above
                pass
            elif not identity.verified:
                violations.append(ViolationType.IDENTITY_MISMATCH)

        return violations

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _decode_frame(self, frame_b64: str) -> Optional[np.ndarray]:
        """Decode a base64 frame string to a BGR numpy array."""
        try:
            if "," in frame_b64:
                frame_b64 = frame_b64.split(",")[1]
            img_bytes = base64.b64decode(frame_b64)
            img_array = np.frombuffer(img_bytes, dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            return frame
        except Exception as e:
            logger.error(f"Frame decode error: {e}")
            return None

    def _build_metadata(
        self,
        face: FaceDetectionResult,
        gaze: GazeAnalysisResult,
        objects: ObjectDetectionResult,
    ) -> Dict[str, Any]:
        """Build metadata dict attached to violation records for audit trail."""
        return {
            "face_count": face.face_count,
            "face_centered": face.is_centered,
            "face_confidence": face.confidence,
            "gaze_direction": gaze.gaze_direction,
            "horizontal_deviation": gaze.horizontal_deviation,
            "vertical_deviation": gaze.vertical_deviation,
            "attention_score": gaze.attention_score,
            "detected_objects": [obj.label for obj in objects.detected_objects],
        }

    def _build_analysis_debug(
        self,
        face: FaceDetectionResult,
        gaze: GazeAnalysisResult,
        objects: ObjectDetectionResult,
        identity: Optional[IdentityVerificationResult],
    ) -> Dict[str, Any]:
        """
        Full debug analysis payload — useful during development.
        In production you may want to strip this or gate it behind a DEBUG flag.
        """
        return {
            "face": {
                "has_face": face.has_face,
                "face_count": face.face_count,
                "is_centered": face.is_centered,
                "confidence": face.confidence,
                "center_offset": face.center_offset,
            },
            "gaze": {
                "is_looking_at_screen": gaze.is_looking_at_screen,
                "gaze_direction": gaze.gaze_direction,
                "horizontal_deviation": gaze.horizontal_deviation,
                "vertical_deviation": gaze.vertical_deviation,
                "head_pose": gaze.head_pose,
                "attention_score": gaze.attention_score,
            },
            "objects": {
                "detected": [
                    {"label": o.label, "confidence": o.confidence, "prohibited": o.is_prohibited}
                    for o in objects.detected_objects
                ],
                "prohibited_count": len(objects.prohibited_objects),
                "person_count": objects.person_count,
            },
            "identity": {
                "checked_this_frame": identity is not None,
                "verified": identity.verified if identity else None,
                "confidence": identity.confidence if identity else None,
                "error": identity.error if identity else None,
            } if identity else {"checked_this_frame": False},
        }

    def _error_result(self, frame_id: str, error_msg: str) -> OrchestratorResult:
        return OrchestratorResult(
            frame_id=frame_id,
            session_id=self.session_id,
            violations=[],
            has_violations=False,
            session_flagged=False,
            analysis={"error": error_msg},
            processing_time_ms=0.0,
        )