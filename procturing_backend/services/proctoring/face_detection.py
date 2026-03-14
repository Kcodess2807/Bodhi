import mediapipe as mp
import numpy as np
import cv2
from loguru import logger
from dataclasses import dataclass
from typing import Optional, Tuple
import urllib.request
import os

_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "blaze_face_short_range.tflite")


@dataclass
class FaceDetectionResult:
    has_face: bool
    face_count: int
    is_centered: bool
    confidence: float
    face_bbox: Optional[Tuple[float, float, float, float]] = None  # (x, y, w, h) normalized 0-1
    center_offset: Optional[Tuple[float, float]] = None            # (x_offset, y_offset) from frame center


class FaceDetector:

    CENTER_TOLERANCE_X = 0.25
    CENTER_TOLERANCE_Y = 0.25

    def __init__(self):
        logger.info("Initializing FaceDetector (MediaPipe Tasks)...")
        self._ensure_model()

        BaseOptions = mp.tasks.BaseOptions
        FaceDetector = mp.tasks.vision.FaceDetector
        FaceDetectorOptions = mp.tasks.vision.FaceDetectorOptions
        VisionRunningMode = mp.tasks.vision.RunningMode

        options = FaceDetectorOptions(
            base_options=BaseOptions(model_asset_path=_MODEL_PATH),
            running_mode=VisionRunningMode.IMAGE,
            min_detection_confidence=0.6,
        )
        self._detector = FaceDetector.create_from_options(options)
        logger.info("FaceDetector ready.")

    def _ensure_model(self):
        if not os.path.exists(_MODEL_PATH):
            logger.info("Downloading face detection model (~800 KB)...")
            urllib.request.urlretrieve(_MODEL_URL, _MODEL_PATH)
            logger.info("Face detection model downloaded.")

    def analyze(self, frame: np.ndarray) -> FaceDetectionResult:
        try:
            frame_h, frame_w = frame.shape[:2]
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

            result = self._detector.detect(mp_image)
            detections = result.detections

            if not detections:
                return FaceDetectionResult(
                    has_face=False, face_count=0, is_centered=False, confidence=0.0
                )

            face_count = len(detections)
            primary = max(detections, key=lambda d: d.categories[0].score)
            confidence = primary.categories[0].score

            bbox = primary.bounding_box
            x_norm = bbox.origin_x / frame_w
            y_norm = bbox.origin_y / frame_h
            w_norm = bbox.width / frame_w
            h_norm = bbox.height / frame_h

            face_center_x = x_norm + w_norm / 2
            face_center_y = y_norm + h_norm / 2
            offset_x = face_center_x - 0.5
            offset_y = face_center_y - 0.5

            is_centered = (
                abs(offset_x) <= self.CENTER_TOLERANCE_X and
                abs(offset_y) <= self.CENTER_TOLERANCE_Y
            )

            return FaceDetectionResult(
                has_face=True,
                face_count=face_count,
                is_centered=is_centered,
                confidence=round(float(confidence), 3),
                face_bbox=(x_norm, y_norm, w_norm, h_norm),
                center_offset=(round(offset_x, 3), round(offset_y, 3)),
            )

        except Exception as e:
            logger.error(f"FaceDetector error: {e}")
            return FaceDetectionResult(
                has_face=False, face_count=0, is_centered=False, confidence=0.0
            )

    def close(self):
        self._detector.close()
