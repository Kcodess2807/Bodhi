import numpy as np
import cv2
from ultralytics import YOLO
from loguru import logger
from dataclasses import dataclass, field
from typing import List, Tuple
from ...config import settings


@dataclass
class DetectedObject:
    label: str
    confidence: float
    bbox: Tuple[float, float, float, float]   # (x1, y1, x2, y2) normalized 0-1
    is_prohibited: bool


@dataclass
class ObjectDetectionResult:
    detected_objects: List[DetectedObject] = field(default_factory=list)
    prohibited_objects: List[DetectedObject] = field(default_factory=list)
    has_prohibited_object: bool = False
    person_count: int = 0
    multiple_people: bool = False


class ObjectDetector:
    """
    Detects objects in a frame using YOLOv8.

    Checks for:
      - Mobile phones
      - Books / notebooks
      - Multiple people in frame
      - Any other prohibited items

    YOLO detects 80 COCO classes. We filter down to the ones
    relevant for proctoring and classify them as prohibited or allowed.
    """

    # COCO class names that are prohibited in an exam context
    PROHIBITED_CLASSES = {
        "cell phone":   "phone_detected",
        "book":         "book_detected",
        "laptop":       "unauthorized_object",
        "tablet":       "unauthorized_object",
        "remote":       "unauthorized_object",
        "keyboard":     "unauthorized_object",   # Secondary keyboard = suspicious
        "mouse":        "unauthorized_object",   # Secondary mouse = suspicious
        "headphones":   "unauthorized_object",
        "earbuds":      "unauthorized_object",
    }

    # Classes we track but don't flag as prohibited
    MONITORED_CLASSES = {
        "person",     # We track person count separately
        "chair",
        "cup",
        "bottle",
    }

    def __init__(self):
        logger.info(f"Initializing ObjectDetector (YOLO: {settings.YOLO_MODEL_VARIANT})...")
        # Downloads model weights on first run, cached after that
        self._model = YOLO(f"{settings.YOLO_MODEL_VARIANT}.pt")
        self._confidence_threshold = settings.OBJECT_DETECTION_CONFIDENCE
        logger.info("ObjectDetector ready.")

    def analyze(self, frame: np.ndarray) -> ObjectDetectionResult:
        """
        Run object detection on a single BGR frame.
        """
        try:
            frame_h, frame_w = frame.shape[:2]

            results = self._model(
                frame,
                conf=self._confidence_threshold,
                verbose=False,    # Suppress YOLO's own logging
            )

            detected_objects: List[DetectedObject] = []
            prohibited_objects: List[DetectedObject] = []
            person_count = 0

            # results[0].boxes contains all detections for the frame
            for box in results[0].boxes:
                label = self._model.names[int(box.cls[0])]
                confidence = float(box.conf[0])

                # Normalized bbox
                x1, y1, x2, y2 = box.xyxyn[0].tolist()
                bbox = (
                    round(x1, 3),
                    round(y1, 3),
                    round(x2, 3),
                    round(y2, 3),
                )

                is_prohibited = label in self.PROHIBITED_CLASSES

                obj = DetectedObject(
                    label=label,
                    confidence=round(confidence, 3),
                    bbox=bbox,
                    is_prohibited=is_prohibited,
                )

                detected_objects.append(obj)

                if label == "person":
                    person_count += 1

                if is_prohibited:
                    prohibited_objects.append(obj)

            # Person count: YOLO detects the candidate themselves as a person too.
            # So multiple_people triggers at count > 1, not > 0.
            multiple_people = person_count > 1

            return ObjectDetectionResult(
                detected_objects=detected_objects,
                prohibited_objects=prohibited_objects,
                has_prohibited_object=len(prohibited_objects) > 0,
                person_count=person_count,
                multiple_people=multiple_people,
            )

        except Exception as e:
            logger.error(f"ObjectDetector error: {e}")
            return ObjectDetectionResult()

    def get_violation_types(self, result: ObjectDetectionResult) -> List[str]:
        """
        Map detected prohibited objects to violation type strings.
        Returns a list of violation type strings for the orchestrator to process.
        """
        violations = []

        if result.multiple_people:
            violations.append("multiple_faces")  # Reuse existing violation type

        for obj in result.prohibited_objects:
            violation_type = self.PROHIBITED_CLASSES.get(obj.label)
            if violation_type and violation_type not in violations:
                violations.append(violation_type)

        return violations