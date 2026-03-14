from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from loguru import logger

from ..models.violation import (
    Violation,
    ViolationEvent,
    ViolationType,
    ViolationSeverity,
    VIOLATION_SEVERITY_MAP,
)


# Human readable messages for each violation type
# These are shown directly to the candidate as warnings
VIOLATION_MESSAGES: Dict[ViolationType, str] = {
    ViolationType.NO_FACE_DETECTED:     "Your face is not visible. Please position yourself in front of the camera.",
    ViolationType.MULTIPLE_FACES:       "Multiple faces detected. Only the candidate should be visible on camera.",
    ViolationType.FACE_NOT_CENTERED:    "Please center your face in the camera frame.",
    ViolationType.IDENTITY_MISMATCH:    "Face verification failed. Please ensure you are the registered candidate.",
    ViolationType.GAZE_DEVIATION:       "Please keep your eyes focused on the screen.",
    ViolationType.LOOKING_AWAY:         "You appear to be looking away from the screen.",
    ViolationType.PHONE_DETECTED:       "A mobile phone has been detected. Please remove it from view.",
    ViolationType.BOOK_DETECTED:        "A book or notebook has been detected. Please remove it from view.",
    ViolationType.UNAUTHORIZED_OBJECT:  "An unauthorized object has been detected in your camera view.",
    ViolationType.TAB_SWITCH:           "Tab switching is not allowed during the assessment.",
    ViolationType.FULLSCREEN_EXIT:      "Please remain in fullscreen mode during the assessment.",
    ViolationType.COPY_PASTE_ATTEMPT:   "Copy and paste is not allowed during the assessment.",
    ViolationType.KEYBOARD_SHORTCUT:    "Unauthorized keyboard shortcut detected.",
}


class ViolationBuilder:
    """
    Builds standardized Violation and ViolationEvent objects.

    Responsibilities:
      - Takes raw signals from the CV pipeline
      - Constructs properly structured violation objects
      - Tracks violation counts per session (in memory for now)
      - Determines if a session should be auto-flagged

    Does NOT write to DB — that's deferred to later.
    Does NOT send to frontend — that's the orchestrator's job.
    """

    def __init__(self, auto_flag_threshold: int = 5):
        # violation_counts[session_id][violation_type] = count
        self._violation_counts: Dict[str, Dict[str, int]] = {}
        self._auto_flag_threshold = auto_flag_threshold
        # flagged_sessions[session_id] = True if session has been auto-flagged
        self._flagged_sessions: Dict[str, bool] = {}

    # ── Core builder ─────────────────────────────────────────────────────────

    def build(
        self,
        session_id: str,
        candidate_id: str,
        violation_type: ViolationType,
        snapshot_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Violation:
        """
        Build a full Violation object (for logging/DB later).
        """
        severity = VIOLATION_SEVERITY_MAP.get(violation_type, ViolationSeverity.LOW)
        message = VIOLATION_MESSAGES.get(violation_type, "A violation was detected.")

        violation = Violation(
            session_id=session_id,
            candidate_id=candidate_id,
            violation_type=violation_type,
            severity=severity,
            timestamp=datetime.now(timezone.utc),
            message=message,
            snapshot_url=snapshot_url,
            metadata=metadata,
        )

        # Track count
        self._increment_count(session_id, violation_type)

        return violation

    def build_event(self, violation_type: ViolationType) -> ViolationEvent:
        """
        Build a lightweight ViolationEvent (sent back to frontend over WebSocket).
        """
        severity = VIOLATION_SEVERITY_MAP.get(violation_type, ViolationSeverity.LOW)
        message = VIOLATION_MESSAGES.get(violation_type, "A violation was detected.")

        return ViolationEvent(
            violation_type=violation_type,
            severity=severity,
            message=message,
            timestamp=datetime.now(timezone.utc),
        )

    def build_multiple(
        self,
        session_id: str,
        candidate_id: str,
        violation_types: List[ViolationType],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Violation]:
        """
        Build multiple violations from a single frame analysis.
        Convenience method used by the orchestrator.
        """
        return [
            self.build(
                session_id=session_id,
                candidate_id=candidate_id,
                violation_type=vt,
                metadata=metadata,
            )
            for vt in violation_types
        ]

    def build_events_from_violations(
        self, violations: List[Violation]
    ) -> List[ViolationEvent]:
        """
        Convert a list of Violation objects to ViolationEvent objects
        for sending to the frontend.
        """
        return [self.build_event(v.violation_type) for v in violations]

    # ── Session state ─────────────────────────────────────────────────────────

    def get_violation_count(self, session_id: str, violation_type: ViolationType) -> int:
        return self._violation_counts.get(session_id, {}).get(violation_type.value, 0)

    def get_total_violations(self, session_id: str) -> int:
        counts = self._violation_counts.get(session_id, {})
        return sum(counts.values())

    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """
        Returns a summary of all violations for a session.
        Used at session end to build the proctoring report.
        """
        counts = self._violation_counts.get(session_id, {})
        total = sum(counts.values())
        is_flagged = self._flagged_sessions.get(session_id, False)

        # Break down by severity
        high_count = 0
        medium_count = 0
        low_count = 0

        for vtype_str, count in counts.items():
            try:
                vtype = ViolationType(vtype_str)
                severity = VIOLATION_SEVERITY_MAP.get(vtype, ViolationSeverity.LOW)
                if severity == ViolationSeverity.HIGH:
                    high_count += count
                elif severity == ViolationSeverity.MEDIUM:
                    medium_count += count
                else:
                    low_count += count
            except ValueError:
                continue

        return {
            "session_id": session_id,
            "total_violations": total,
            "violation_breakdown": counts,
            "high_severity_count": high_count,
            "medium_severity_count": medium_count,
            "low_severity_count": low_count,
            "is_flagged": is_flagged,
        }

    def is_session_flagged(self, session_id: str) -> bool:
        return self._flagged_sessions.get(session_id, False)

    def clear_session(self, session_id: str):
        """
        Clean up in-memory state when a session ends.
        """
        self._violation_counts.pop(session_id, None)
        self._flagged_sessions.pop(session_id, None)
        logger.info(f"Cleared violation state for session {session_id}")

    # ── Internals ─────────────────────────────────────────────────────────────

    def _increment_count(self, session_id: str, violation_type: ViolationType):
        if session_id not in self._violation_counts:
            self._violation_counts[session_id] = {}

        key = violation_type.value
        self._violation_counts[session_id][key] = (
            self._violation_counts[session_id].get(key, 0) + 1
        )

        # Check if session should be auto-flagged
        # Flag if any single HIGH severity violation type exceeds threshold
        severity = VIOLATION_SEVERITY_MAP.get(violation_type, ViolationSeverity.LOW)
        if severity == ViolationSeverity.HIGH:
            count = self._violation_counts[session_id][key]
            if count >= self._auto_flag_threshold:
                if not self._flagged_sessions.get(session_id, False):
                    self._flagged_sessions[session_id] = True
                    logger.warning(
                        f"Session {session_id} auto-flagged: "
                        f"{violation_type.value} occurred {count} times."
                    )