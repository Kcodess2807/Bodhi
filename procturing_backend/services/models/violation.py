from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum


class ViolationType(str, Enum):
    # face related
    NO_FACE_DETECTED = "no_face_detected"
    MULTIPLE_FACES = "multiple_faces"
    FACE_NOT_CENTERED = "face_not_centered"
    IDENTITY_MISMATCH = "identity_mismatch"

    # gaze related
    GAZE_DEVIATION = "gaze_deviation"
    LOOKING_AWAY = "looking_away"

    # object detection
    PHONE_DETECTED = "phone_detected"
    BOOK_DETECTED = "book_detected"
    UNAUTHORIZED_OBJECT = "unauthorized_object"

    # gestures/shortcuts/tab-switch
    TAB_SWITCH = "tab_switch"
    FULLSCREEN_EXIT = "fullscreen_exit"
    COPY_PASTE_ATTEMPT = "copy_paste_attempt"
    KEYBOARD_SHORTCUT = "keyboard_shortcut"


class ViolationSeverity(str, Enum):
    LOW = "low"       # warn the user and log it
    MEDIUM = "medium" # warn user prominently, log it
    HIGH = "high"     # warn user, flag session for review


# severity level for each violation type
VIOLATION_SEVERITY_MAP: Dict[ViolationType, ViolationSeverity] = {
    ViolationType.FACE_NOT_CENTERED:   ViolationSeverity.LOW,
    ViolationType.KEYBOARD_SHORTCUT:   ViolationSeverity.LOW,
    ViolationType.GAZE_DEVIATION:      ViolationSeverity.LOW,

    ViolationType.LOOKING_AWAY:        ViolationSeverity.MEDIUM,
    ViolationType.BOOK_DETECTED:       ViolationSeverity.MEDIUM,
    ViolationType.UNAUTHORIZED_OBJECT: ViolationSeverity.MEDIUM,
    ViolationType.COPY_PASTE_ATTEMPT:  ViolationSeverity.MEDIUM,
    ViolationType.NO_FACE_DETECTED:    ViolationSeverity.MEDIUM,

    ViolationType.IDENTITY_MISMATCH:   ViolationSeverity.HIGH,
    ViolationType.MULTIPLE_FACES:      ViolationSeverity.HIGH,
    ViolationType.PHONE_DETECTED:      ViolationSeverity.HIGH,
    ViolationType.TAB_SWITCH:          ViolationSeverity.HIGH,
    ViolationType.FULLSCREEN_EXIT:     ViolationSeverity.HIGH,
}


class Violation(BaseModel):
    session_id: str
    candidate_id: str
    violation_type: ViolationType
    severity: ViolationSeverity
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message: str
    snapshot_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ViolationEvent(BaseModel):
    # Lightweight payload sent to the frontend over WebSocket
    violation_type: ViolationType
    severity: ViolationSeverity
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FrameAnalysisResult(BaseModel):
    # Aggregated result of the full CV pipeline for a single frame
    has_face: bool = False
    face_count: int = 0
    face_centered: bool = False
    identity_verified: Optional[bool] = None
    gaze_deviation: Optional[float] = None
    looking_away: bool = False
    detected_objects: list = []
    violations: List[ViolationType] = []
