"""Pydantic response models for the behavioral analysis API."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class SpeechResult(BaseModel):
    transcript: str
    language: str
    emotion: str = Field(
        ..., description="joy | fear | anger | sadness | disgust | surprise | neutral"
    )
    emotion_confidence: float = Field(..., ge=0.0, le=1.0)
    sentiment: str = Field(..., description="positive | neutral | negative")
    speech_rate_wpm: int
    pitch_variance: float
    confidence_score: int = Field(..., ge=0, le=100)
    flags: list[str]


class PostureResult(BaseModel):
    posture: str = Field(
        ...,
        description="upright | slouching | leaning_away | looking_away | face_not_visible",
    )
    head_tilt_angle: float
    gaze_direction: str = Field(
        ..., description="center | left | right | up | down | unknown"
    )
    spine_score: int = Field(..., ge=0, le=100)
    face_visible: bool
    flags: list[str]


class AnalysisResponse(BaseModel):
    status: str
    speech: Optional[SpeechResult] = None
    posture: Optional[PostureResult] = None
    errors: dict[str, str] = Field(default_factory=dict)
