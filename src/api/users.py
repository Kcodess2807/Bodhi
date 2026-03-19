"""User profile synchronization endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from src.api.auth import require_auth
from src.api.deps import get_storage
from src.storage import BodhiStorage

router = APIRouter(prefix="/api/users", tags=["users"])


class UserSyncResponse(BaseModel):
    user_id: str
    clerk_user_id: str


class UserStatusResponse(BaseModel):
    user_id: str
    clerk_user_id: str
    has_resume: bool


@router.post("/me", response_model=UserSyncResponse)
async def upsert_current_user(
    clerk_user_id: str = Depends(require_auth),
    storage: BodhiStorage = Depends(get_storage),
):
    user_id = storage.ensure_user_profile_for_clerk(clerk_user_id)
    return UserSyncResponse(user_id=user_id, clerk_user_id=clerk_user_id)


@router.get("/me", response_model=UserSyncResponse)
async def get_current_user(
    clerk_user_id: str = Depends(require_auth),
    storage: BodhiStorage = Depends(get_storage),
):
    user_id = storage.get_user_profile_id_by_clerk_user_id(clerk_user_id)
    if not user_id:
        user_id = storage.ensure_user_profile_for_clerk(clerk_user_id)
    return UserSyncResponse(user_id=user_id, clerk_user_id=clerk_user_id)


@router.get("/me/status", response_model=UserStatusResponse)
async def get_current_user_status(
    clerk_user_id: str = Depends(require_auth),
    storage: BodhiStorage = Depends(get_storage),
):
    status = storage.get_user_profile_status_by_clerk_user_id(clerk_user_id)
    if not status:
        user_id = storage.ensure_user_profile_for_clerk(clerk_user_id)
        return UserStatusResponse(
            user_id=user_id,
            clerk_user_id=clerk_user_id,
            has_resume=False,
        )
    user_id, has_resume = status
    return UserStatusResponse(
        user_id=user_id,
        clerk_user_id=clerk_user_id,
        has_resume=has_resume,
    )


from datetime import datetime

class InterviewHistoryItem(BaseModel):
    session_id: str
    target_company: str
    target_role: str
    overall_score: float | None = None
    started_at: datetime
    ended_at: datetime | None = None

class UserProfileResponse(BaseModel):
    clerk_user_id: str
    has_resume: bool
    resume_data: dict | None = None
    resume_file_name: str | None = None
    interview_history: list[InterviewHistoryItem]

@router.get("/me/resume/download")
async def download_resume(
    clerk_user_id: str = Depends(require_auth),
    storage: BodhiStorage = Depends(get_storage),
):
    content, filename = storage.get_user_resume_file(clerk_user_id)
    if not content:
        raise HTTPException(status_code=404, detail="No resume available to download.")
    return Response(content, media_type="application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="{filename or "resume.pdf"}"'
    })

@router.get("/me/profile", response_model=UserProfileResponse)
async def get_full_user_profile(
    clerk_user_id: str = Depends(require_auth),
    storage: BodhiStorage = Depends(get_storage),
):
    # Get user profile status to find user_id and has_resume
    status = storage.get_user_profile_status_by_clerk_user_id(clerk_user_id)
    if not status:
        user_id = storage.ensure_user_profile_for_clerk(clerk_user_id)
        has_resume = False
    else:
        user_id, has_resume = status

    # Get resume profile data
    resume_data = None
    resume_file_name = None
    if has_resume:
        full_profile = storage.get_user_profile(user_id)
        if full_profile and getattr(full_profile, "get", None):
            resume_data = full_profile.get("professional_summary")
            resume_file_name = full_profile.get("resume_file_name")

    # Get interview history
    history = storage.get_user_interview_history(clerk_user_id)
    
    return UserProfileResponse(
        clerk_user_id=clerk_user_id,
        has_resume=has_resume,
        resume_data=resume_data,
        resume_file_name=resume_file_name,
        interview_history=history,
    )
