"""
POST /api/v3/billing/checkout      — create Stripe Checkout session
POST /api/v3/billing/portal        — create Stripe Customer Portal session
GET  /api/v3/billing/status        — current tier + scan usage
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth.cognito import get_current_user
from ..db import dynamodb as db
from ..models.schemas import (
    BillingStatusResponse,
    CheckoutRequest,
    CheckoutResponse,
    PortalResponse,
    SubscriptionTier,
)
from ..services import stripe_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["billing"])

_FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://imgapp.craftingnewtech.com")


@router.post("/billing/checkout", response_model=CheckoutResponse)
async def create_checkout(
    payload: CheckoutRequest,
    user: dict = Depends(get_current_user),
) -> CheckoutResponse:
    checkout_url = stripe_service.create_checkout_session(
        user_id=user["user_id"],
        email=user["email"],
        price_id=payload.price_id,
        success_url=f"{_FRONTEND_URL}/billing?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{_FRONTEND_URL}/billing",
    )
    return CheckoutResponse(checkout_url=checkout_url)


@router.post("/billing/portal", response_model=PortalResponse)
async def create_portal(
    user: dict = Depends(get_current_user),
) -> PortalResponse:
    sub = db.get_subscription(user["user_id"])
    customer_id = sub.get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription found. Subscribe first via /api/v3/billing/checkout.",
        )
    portal_url = stripe_service.create_portal_session(
        stripe_customer_id=customer_id,
        return_url=f"{_FRONTEND_URL}/billing",
    )
    return PortalResponse(portal_url=portal_url)


@router.get("/billing/status", response_model=BillingStatusResponse)
async def get_billing_status(
    user: dict = Depends(get_current_user),
) -> BillingStatusResponse:
    sub = db.get_subscription(user["user_id"])
    _LIMITS = {"free": 10, "pro": 200, "enterprise": -1}
    tier = sub.get("tier", "free")
    return BillingStatusResponse(
        tier=SubscriptionTier(tier),
        scan_count_month=sub.get("scan_count_month", 0),
        scan_limit=_LIMITS.get(tier, 10),
        period_end=sub.get("period_end"),
        payment_past_due=sub.get("payment_past_due", False),
    )
