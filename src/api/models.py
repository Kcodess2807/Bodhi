"""Pydantic request/response schemas for the Bodhi API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── Roles ─────────────────────────────────────────────────────────

class RoleCreate(BaseModel):
    role_name: str
    description: str = ""
    focus_areas: str = ""
    typical_topics: str = ""


class RoleUpdate(BaseModel):
    description: str | None = None
    focus_areas: str | None = None
    typical_topics: str | None = None


class RoleResponse(BaseModel):
    id: int
    role_name: str
    description: str
    focus_areas: str
    typical_topics: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Companies ─────────────────────────────────────────────────────

class CompanyProfileCreate(BaseModel):
    company_name: str
    role: str = "general"
    description: str = ""
    hiring_patterns: str = ""
    tech_stack: str = ""


class CompanyProfileResponse(BaseModel):
    id: int
    company_name: str
    role: str
    description: str | None
    hiring_patterns: str | None
    tech_stack: str | None
    contributed_by: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Documents / RAG ───────────────────────────────────────────────

class IngestRequest(BaseModel):
    company: str
    role: str = "general"
    text: str
    source_label: str = ""


class IngestResponse(BaseModel):
    chunks_ingested: int


class UploadResponse(BaseModel):
    chunks_ingested: int
    topics_extracted: list[str] = []
    profile_extracted: dict | None = None


class SearchRequest(BaseModel):
    company: str
    role: str = "general"
    query: str
    top_k: int = 5


class SearchResult(BaseModel):
    chunk_text: str
    similarity: float


class ContextResponse(BaseModel):
    company: str
    role: str
    context: str


class TopicsResponse(BaseModel):
    company: str
    role: str
    topics: list[str]


# ── Interviews ────────────────────────────────────────────────────

class InterviewStartRequest(BaseModel):
    candidate_name: str = "Candidate"
    company: str = "General"
    role: str = "Software Engineer"
    jd_text: str = ""  # Optional job description text for curriculum customization
    mode: Literal["standard", "option_a", "option_b", "mode_a", "mode_b"] = "standard"
    user_id: str | None = None   # required for option_a and option_b


class InterviewStartResponse(BaseModel):
    session_id: str
    greeting_text: str
    greeting_audio_b64: str = ""


class MessageRequest(BaseModel):
    text: str


class MessageResponse(BaseModel):
    transcript: str = ""
    reply_text: str
    reply_audio_b64: str = ""
    phase: str
    should_end: bool = False


class SessionStateResponse(BaseModel):
    session_id: str
    phase: str
    difficulty_level: int
    phase_scores: dict
    company: str
    role: str


class SessionEndResponse(BaseModel):
    session_id: str
    summary: str
    overall_score: float | None = None


# ── Audio utilities ───────────────────────────────────────────────

class STTResponse(BaseModel):
    transcript: str


class TTSRequest(BaseModel):
    text: str
    target_language_code: str = "hi-IN"
    speaker: str = "shubh"


class TTSResponse(BaseModel):
    audio_b64: str
