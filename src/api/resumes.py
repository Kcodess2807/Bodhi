"""Resume ingestion endpoints — parse and store structured candidate profiles."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.api.deps import get_llm, get_storage
from src.storage import BodhiStorage

router = APIRouter(prefix="/api/resumes", tags=["resumes"])

_ALLOWED_EXTENSIONS = (".pdf", ".docx")
_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ResumeUploadResponse(BaseModel):
    user_id: str
    profile: dict


class ProfileResponse(BaseModel):
    user_id: str
    professional_summary: dict


@router.post("/upload", response_model=ResumeUploadResponse, status_code=201)
async def upload_resume(
    file: UploadFile = File(...),
    storage: BodhiStorage = Depends(get_storage),
    llm=Depends(get_llm),
):
    """Upload a PDF or DOCX resume. Extracts text, parses it with the LLM into a
    structured profile, and stores the result. Returns the new user_id."""
    from src.document_parser import extract_text_from_file
    from src.resume_parser import parse_resume

    filename = file.filename or ""
    content_type = file.content_type or ""

    if not (
        content_type in _ALLOWED_CONTENT_TYPES
        or any(filename.lower().endswith(ext) for ext in _ALLOWED_EXTENSIONS)
    ):
        raise HTTPException(400, "Only PDF and DOCX files are supported")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(400, "Uploaded file is empty")

    try:
        raw_text = extract_text_from_file(file_bytes, filename)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if not raw_text or len(raw_text.strip()) < 50:
        raise HTTPException(422, "Could not extract meaningful text from the document")

    try:
        profile = parse_resume(raw_text, llm)
    except ValueError as exc:
        raise HTTPException(422, f"Resume parsing failed: {exc}") from exc

    user_id = storage.create_user_profile(raw_text, profile)
    return ResumeUploadResponse(user_id=user_id, profile=profile)


@router.get("/{user_id}", response_model=ProfileResponse)
async def get_resume_profile(
    user_id: str,
    storage: BodhiStorage = Depends(get_storage),
):
    """Retrieve a stored candidate profile by user_id."""
    row = storage.get_user_profile(user_id)
    if not row:
        raise HTTPException(404, f"Profile '{user_id}' not found")
    return ProfileResponse(
        user_id=row["user_id"],
        professional_summary=row["professional_summary"],
    )
