"""
POST /api/v3/orgs                    — create org (Enterprise only)
GET  /api/v3/orgs/me                 — get current user's org
POST /api/v3/orgs/{org_id}/members   — add member
"""

import logging

from fastapi import APIRouter, Depends, status

from ..auth.cognito import get_current_user
from ..models.schemas import OrgCreateRequest, OrgInviteRequest, OrgResponse
from ..services import org_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["orgs"])


@router.post("/orgs", response_model=OrgResponse, status_code=status.HTTP_201_CREATED)
async def create_org(
    payload: OrgCreateRequest,
    user: dict = Depends(get_current_user),
) -> OrgResponse:
    org = org_service.create_org(user["user_id"], payload.name)
    return OrgResponse(**org)


@router.get("/orgs/me", response_model=OrgResponse)
async def get_my_org(
    user: dict = Depends(get_current_user),
) -> OrgResponse:
    org = org_service.get_org(user["user_id"])
    return OrgResponse(**org)


@router.post("/orgs/{org_id}/members", status_code=status.HTTP_204_NO_CONTENT)
async def add_member(
    org_id: str,
    payload: OrgInviteRequest,
    user: dict = Depends(get_current_user),
) -> None:
    org_service.add_member(user["user_id"], org_id, payload.user_id)
