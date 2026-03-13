"""Role profiles CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import get_storage
from src.api.models import RoleCreate, RoleResponse, RoleUpdate
from src.storage import BodhiStorage

router = APIRouter(prefix="/api/roles", tags=["roles"])


@router.post("", response_model=RoleResponse, status_code=201)
async def create_role(
    body: RoleCreate,
    storage: BodhiStorage = Depends(get_storage),
):
    try:
        row = storage.create_role(
            role_name=body.role_name,
            description=body.description,
            focus_areas=body.focus_areas,
            typical_topics=body.typical_topics,
        )
        return row
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(409, f"Role '{body.role_name}' already exists")
        raise


@router.get("", response_model=list[RoleResponse])
async def list_roles(storage: BodhiStorage = Depends(get_storage)):
    return storage.list_roles()


@router.get("/{role_name}", response_model=RoleResponse)
async def get_role(
    role_name: str,
    storage: BodhiStorage = Depends(get_storage),
):
    row = storage.get_role(role_name)
    if not row:
        raise HTTPException(404, f"Role '{role_name}' not found")
    return row


@router.put("/{role_name}", response_model=RoleResponse)
async def update_role(
    role_name: str,
    body: RoleUpdate,
    storage: BodhiStorage = Depends(get_storage),
):
    row = storage.update_role(role_name, **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, f"Role '{role_name}' not found")
    return row


@router.delete("/{role_name}", status_code=204)
async def delete_role(
    role_name: str,
    storage: BodhiStorage = Depends(get_storage),
):
    deleted = storage.delete_role(role_name)
    if not deleted:
        raise HTTPException(404, f"Role '{role_name}' not found")
