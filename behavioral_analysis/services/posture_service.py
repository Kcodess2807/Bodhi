"""Posture and gaze analysis service.

Pipeline:
  1. Decode JPEG/PNG image bytes with OpenCV
  2. MediaPipe Pose — 33 body landmarks → spine angle, slouch detection
  3. MediaPipe FaceMesh (refine_landmarks=True) — 478 pts including iris
     → head tilt from ear landmarks, gaze from iris vs eye-corner ratios
  4. Rule-based classification into posture labels and behavioral flags
"""
from __future__ import annotations

import math

import cv2
import mediapipe as mp
import numpy as np

# ── MediaPipe solution handles (loaded lazily) ────────────────────────────────
# mediapipe >= 0.10.14 removed mp.solutions — handle both old and new installs.

try:
    _mp_pose = mp.solutions.pose
    _mp_face = mp.solutions.face_mesh
    _SOLUTIONS_AVAILABLE = True
except AttributeError:
    _mp_pose = None  # type: ignore[assignment]
    _mp_face = None  # type: ignore[assignment]
    _SOLUTIONS_AVAILABLE = False

_pose_inst = None
_face_inst = None


def load_models() -> None:
    """Instantiate MediaPipe solutions. Safe to call multiple times."""
    global _pose_inst, _face_inst
    if not _SOLUTIONS_AVAILABLE:
        return
    if _pose_inst is None:
        _pose_inst = _mp_pose.Pose(
            static_image_mode=True,
            model_complexity=1,
            min_detection_confidence=0.5,
        )
    if _face_inst is None:
        _face_inst = _mp_face.FaceMesh(
            static_image_mode=True,
            refine_landmarks=True,       # enables iris landmarks (indices 468-477)
            max_num_faces=1,
            min_detection_confidence=0.5,
        )


def models_ready() -> bool:
    return _SOLUTIONS_AVAILABLE and _pose_inst is not None and _face_inst is not None


# ── Gaze detection from FaceMesh iris landmarks ───────────────────────────────

# FaceMesh landmark indices used for gaze
_L_IRIS = 468       # left iris center (refined)
_R_IRIS = 473       # right iris center (refined)
_L_EYE_OUTER = 33   # left eye outer corner
_L_EYE_INNER = 133  # left eye inner corner
_R_EYE_INNER = 362  # right eye inner corner
_R_EYE_OUTER = 263  # right eye outer corner
_L_EYE_TOP = 159    # left eye upper lid midpoint
_L_EYE_BOT = 145    # left eye lower lid midpoint


def _detect_gaze(face_landmarks) -> tuple[str, list[str]]:
    """Compute gaze direction from iris position relative to eye corners.

    Uses both eyes and averages the horizontal ratio.
    Vertical gaze is taken from the left iris vs upper/lower lid landmarks.

    Returns:
        (direction, flags) where direction ∈ {center, left, right, up, down}
        and flags may contain "looking_away".
    """
    lms = face_landmarks.landmark

    # Iris landmarks only exist when refine_landmarks=True (478-pt mesh)
    if len(lms) < 478:
        return "center", []

    def pt(idx) -> np.ndarray:
        l = lms[idx]
        return np.array([l.x, l.y])

    # ── Horizontal gaze ratio ─────────────────────────────────────────────────
    # For each eye: ratio 0 = iris at outer corner, 1 = iris at inner corner.
    # A centred iris sits at ~0.5.

    l_outer = pt(_L_EYE_OUTER)
    l_inner = pt(_L_EYE_INNER)
    l_iris = pt(_L_IRIS)
    l_span = abs(l_inner[0] - l_outer[0])
    l_ratio = (l_iris[0] - l_outer[0]) / l_span if l_span > 1e-4 else 0.5

    r_inner = pt(_R_EYE_INNER)
    r_outer = pt(_R_EYE_OUTER)
    r_iris = pt(_R_IRIS)
    r_span = abs(r_outer[0] - r_inner[0])
    r_ratio = (r_iris[0] - r_inner[0]) / r_span if r_span > 1e-4 else 0.5

    avg_h = (l_ratio + r_ratio) / 2.0

    # ── Vertical gaze ratio ───────────────────────────────────────────────────
    l_top = pt(_L_EYE_TOP)
    l_bot = pt(_L_EYE_BOT)
    v_span = abs(l_bot[1] - l_top[1])
    v_ratio = (l_iris[1] - l_top[1]) / v_span if v_span > 1e-4 else 0.5

    # ── Classify ──────────────────────────────────────────────────────────────
    flags: list[str] = []

    if avg_h < 0.30:
        direction = "left"
        flags.append("looking_away")
    elif avg_h > 0.70:
        direction = "right"
        flags.append("looking_away")
    elif v_ratio < 0.25:
        direction = "up"
        flags.append("looking_away")
    elif v_ratio > 0.75:
        direction = "down"
    else:
        direction = "center"

    return direction, flags


# ── Posture analysis from Pose landmarks ──────────────────────────────────────

_PL = _mp_pose.PoseLandmark if _SOLUTIONS_AVAILABLE else None


def _analyze_landmarks(pose_results, face_results) -> dict:
    """Compute all posture metrics from MediaPipe results."""

    face_visible = (
        face_results.multi_face_landmarks is not None
        and len(face_results.multi_face_landmarks) > 0
    )

    # No body detected → cannot assess posture
    if not pose_results.pose_landmarks:
        return {
            "posture": "face_not_visible",
            "head_tilt_angle": 0.0,
            "gaze_direction": "unknown",
            "spine_score": 0,
            "face_visible": face_visible,
            "flags": ["face_not_visible"],
        }

    lm = pose_results.pose_landmarks.landmark

    def get(landmark) -> np.ndarray:
        l = lm[landmark]
        return np.array([l.x, l.y])

    # Key body points in normalised [0,1] image coordinates
    l_shoulder = get(_PL.LEFT_SHOULDER)
    r_shoulder = get(_PL.RIGHT_SHOULDER)
    l_hip = get(_PL.LEFT_HIP)
    r_hip = get(_PL.RIGHT_HIP)
    l_ear = get(_PL.LEFT_EAR)
    r_ear = get(_PL.RIGHT_EAR)

    mid_shoulder = (l_shoulder + r_shoulder) / 2
    mid_hip = (l_hip + r_hip) / 2

    # ── Spine angle (0° = perfectly vertical) ────────────────────────────────
    spine_vec = mid_shoulder - mid_hip
    # atan2(Δx, Δy): the further from 0°, the more the person leans
    spine_angle_deg = math.degrees(math.atan2(abs(spine_vec[0]), abs(spine_vec[1])))
    # Score: 100 at 0°, drops 3 pts per degree; clamp 0-100
    spine_score = int(max(0, min(100, 100 - spine_angle_deg * 3)))

    # ── Head tilt (ear-to-ear horizontal angle) ───────────────────────────────
    ear_diff = r_ear - l_ear
    head_tilt_angle = round(
        abs(math.degrees(math.atan2(ear_diff[1], abs(ear_diff[0]) + 1e-6))), 1
    )

    # ── Slouching heuristic ───────────────────────────────────────────────────
    # In normalised coords, y increases downward.
    # Healthy posture: mid_shoulder sits well above mid_hip (Δy > 0.15).
    shoulder_hip_gap = mid_hip[1] - mid_shoulder[1]  # positive when upright
    is_slouching = shoulder_hip_gap < 0.12

    # ── Leaning away heuristic ────────────────────────────────────────────────
    is_leaning = spine_angle_deg > 20

    # ── Flags + posture label ─────────────────────────────────────────────────
    flags: list[str] = []

    if is_slouching:
        flags.append("slouching")

    if is_leaning:
        flags.append("leaning_back")

    if head_tilt_angle > 15:
        flags.append("head_tilt")

    if not face_visible:
        flags.append("face_not_visible")

    # Gaze detection (requires the refined FaceMesh iris landmarks)
    gaze_direction = "center"
    if face_visible:
        gaze_direction, gaze_flags = _detect_gaze(
            face_results.multi_face_landmarks[0]
        )
        flags.extend(gaze_flags)

    # Choose the most salient posture label (priority order)
    if not face_visible:
        posture = "face_not_visible"
    elif "looking_away" in flags:
        posture = "looking_away"
    elif is_slouching:
        posture = "slouching"
    elif is_leaning:
        posture = "leaning_away"
    else:
        posture = "upright"

    return {
        "posture": posture,
        "head_tilt_angle": head_tilt_angle,
        "gaze_direction": gaze_direction,
        "spine_score": spine_score,
        "face_visible": face_visible,
        "flags": flags,
    }


# ── Public entry point ────────────────────────────────────────────────────────


def analyze_posture(image_bytes: bytes) -> dict:
    """Run posture and gaze analysis on a raw JPEG/PNG image frame.

    Args:
        image_bytes: Raw bytes of the uploaded image file.

    Returns:
        Dict matching the PostureResult schema.
    """
    if not _SOLUTIONS_AVAILABLE:
        return {}  # mediapipe solutions unavailable — skip silently

    load_models()

    # Step 1: Decode image
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError("Failed to decode image — ensure it is a valid JPEG or PNG.")

    # Step 2: Convert BGR → RGB (MediaPipe expects RGB)
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    # Step 3: Run MediaPipe Pose
    pose_results = _pose_inst.process(img_rgb)  # type: ignore[union-attr]

    # Step 4: Run MediaPipe FaceMesh (iris landmarks need refine_landmarks=True)
    face_results = _face_inst.process(img_rgb)  # type: ignore[union-attr]

    # Step 5: Compute metrics from landmarks
    return _analyze_landmarks(pose_results, face_results)
