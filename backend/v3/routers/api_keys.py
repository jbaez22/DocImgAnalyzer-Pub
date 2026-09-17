"""
POST   /api/v3/keys           — create API key (returns raw key once)
GET    /api/v3/keys           — list user's API keys
DELETE /api/v3/keys/{key_id}  — revoke a key
"""

import logging

from fastapi import APIRouter, Depends, status

from ..auth.cognito import get_current_user
from ..models.schemas import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeySummary,
)
from ..services import api_key_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["api-keys"])


@router.post(
    "/keys", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED
)
async def create_key(
    payload: ApiKeyCreateRequest,
    user: dict = Depends(get_current_user),
) -> ApiKeyCreateResponse:
    result = api_key_service.create_api_key(user["user_id"], payload.name)
    return ApiKeyCreateResponse(**result)


@router.get("/keys", response_model=ApiKeyListResponse)
async def list_keys(
    user: dict = Depends(get_current_user),
) -> ApiKeyListResponse:
    records = api_key_service.list_api_keys(user["user_id"])
    summaries = [
        ApiKeySummary(
            key_id=r["key_id"],
            name=r["name"],
            created_at=r["created_at"],
            last_used_at=r.get("last_used_at"),
            revoked=r.get("revoked", False),
        )
        for r in records
    ]
    return ApiKeyListResponse(keys=summaries)


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(
    key_id: str,
    user: dict = Depends(get_current_user),
) -> None:
    api_key_service.revoke_api_key(user["user_id"], key_id)
