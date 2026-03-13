"""Company profiles CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import get_storage
from src.api.models import CompanyProfileCreate, CompanyProfileResponse
from src.storage import BodhiStorage

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.post("", response_model=CompanyProfileResponse, status_code=201)
async def create_or_update_company(
    body: CompanyProfileCreate,
    storage: BodhiStorage = Depends(get_storage),
):
    storage.upsert_company_profile(
        company_name=body.company_name,
        role=body.role,
        description=body.description,
        hiring_patterns=body.hiring_patterns,
        tech_stack=body.tech_stack,
    )
    profiles = storage.get_company_profiles(body.company_name)
    match = next(
        (p for p in profiles if p["role"].lower() == body.role.lower()), None
    )
    if not match:
        raise HTTPException(500, "Profile created but could not be retrieved")
    return match


@router.get("", response_model=list[CompanyProfileResponse])
async def list_companies(storage: BodhiStorage = Depends(get_storage)):
    return storage.list_company_profiles()


@router.get("/{company_name}", response_model=list[CompanyProfileResponse])
async def get_company(
    company_name: str,
    storage: BodhiStorage = Depends(get_storage),
):
    profiles = storage.get_company_profiles(company_name)
    if not profiles:
        raise HTTPException(404, f"No profiles found for '{company_name}'")
    return profiles


@router.delete("/{company_name}/{role}", status_code=204)
async def delete_company_profile(
    company_name: str,
    role: str,
    storage: BodhiStorage = Depends(get_storage),
):
    deleted = storage.delete_company_profile(company_name, role)
    if not deleted:
        raise HTTPException(404, f"Profile '{company_name}/{role}' not found")
