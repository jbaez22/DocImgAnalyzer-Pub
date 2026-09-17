"""
Stripe webhook Lambda handler.

Receives POST /webhooks/stripe routed by API Gateway (no JWT authorizer).
Verifies HMAC-SHA256 signature then dispatches on event type.

Handled events:
  checkout.session.completed      — provision subscription after first payment
  customer.subscription.updated  — tier change or renewal
  customer.subscription.deleted  — downgrade to free on cancellation
  invoice.payment_succeeded       — reset monthly scan counter on renewal
  invoice.payment_failed          — mark payment_past_due
"""

import json
import logging
import os
from datetime import datetime, timezone

import boto3
import stripe
import stripe.error

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

_secrets_client = None
_stripe_initialized = False

_PRICE_TO_TIER = {
    os.environ.get("STRIPE_PRO_PRICE_ID", ""): "pro",
    os.environ.get("STRIPE_ENTERPRISE_PRICE_ID", ""): "enterprise",
}

_SCAN_LIMITS = {"free": 10, "pro": 200, "enterprise": -1}


def _get_secret(secret_id: str) -> str:
    global _secrets_client
    if _secrets_client is None:
        _secrets_client = boto3.client("secretsmanager")
    return _secrets_client.get_secret_value(SecretId=secret_id)["SecretString"]


def _init_stripe() -> None:
    global _stripe_initialized
    if _stripe_initialized:
        return
    path = os.environ["STRIPE_SECRET_MANAGER_PATH"]
    stripe.api_key = _get_secret(f"{path}/secret-key")
    _stripe_initialized = True


def _get_webhook_secret() -> str:
    path = os.environ["STRIPE_SECRET_MANAGER_PATH"]
    return _get_secret(f"{path}/webhook-signing-secret")


def _ddb_table(table_name: str):
    return boto3.resource("dynamodb").Table(table_name)


def _subscriptions_table():
    return _ddb_table(os.environ["SUBSCRIPTIONS_TABLE"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_tier(price_id: str) -> str:
    return _PRICE_TO_TIER.get(price_id, "free")


def _handle_checkout_completed(session: dict) -> None:
    user_id = session.get("client_reference_id") or session.get("metadata", {}).get(
        "user_id"
    )
    if not user_id:
        logger.warning(
            "checkout.session.completed missing user_id",
            extra={"session": session["id"]},
        )
        return

    sub_id = session.get("subscription")
    customer_id = session.get("customer")
    price_id = ""

    if sub_id:
        _init_stripe()
        sub_obj = stripe.Subscription.retrieve(sub_id)
        price_id = sub_obj["items"]["data"][0]["price"]["id"]

    tier = _resolve_tier(price_id)
    limit = _SCAN_LIMITS.get(tier, 10)

    _subscriptions_table().update_item(
        Key={"user_id": user_id},
        UpdateExpression=(
            "SET #tier = :tier, stripe_customer_id = :cid, stripe_subscription_id = :sid, "
            "scan_limit = :lim, payment_past_due = :f, updated_at = :now"
        ),
        ExpressionAttributeNames={"#tier": "tier"},
        ExpressionAttributeValues={
            ":tier": tier,
            ":cid": customer_id,
            ":sid": sub_id,
            ":lim": limit,
            ":f": False,
            ":now": _now(),
        },
    )
    logger.info("Subscription created", extra={"user_id": user_id, "tier": tier})


def _handle_subscription_updated(sub: dict) -> None:
    customer_id = sub.get("customer")
    if not customer_id:
        return

    table = _subscriptions_table()
    resp = table.query(
        IndexName="stripe-customer-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("stripe_customer_id").eq(
            customer_id
        ),
        Limit=1,
    )
    items = resp.get("Items", [])
    if not items:
        logger.warning(
            "No subscription record for customer", extra={"customer": customer_id}
        )
        return

    user_id = items[0]["user_id"]
    price_id = sub["items"]["data"][0]["price"]["id"]
    tier = _resolve_tier(price_id)
    limit = _SCAN_LIMITS.get(tier, 10)
    period_end = datetime.fromtimestamp(
        sub["current_period_end"], tz=timezone.utc
    ).isoformat()

    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET #tier = :tier, scan_limit = :lim, period_end = :pe, updated_at = :now",
        ExpressionAttributeNames={"#tier": "tier"},
        ExpressionAttributeValues={
            ":tier": tier,
            ":lim": limit,
            ":pe": period_end,
            ":now": _now(),
        },
    )
    logger.info("Subscription updated", extra={"user_id": user_id, "tier": tier})


def _handle_subscription_deleted(sub: dict) -> None:
    customer_id = sub.get("customer")
    if not customer_id:
        return

    table = _subscriptions_table()
    resp = table.query(
        IndexName="stripe-customer-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("stripe_customer_id").eq(
            customer_id
        ),
        Limit=1,
    )
    items = resp.get("Items", [])
    if not items:
        return

    user_id = items[0]["user_id"]
    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET #tier = :free, scan_limit = :lim, period_end = :none, updated_at = :now",
        ExpressionAttributeNames={"#tier": "tier"},
        ExpressionAttributeValues={
            ":free": "free",
            ":lim": 10,
            ":none": None,
            ":now": _now(),
        },
    )
    logger.info("Subscription cancelled — reverted to free", extra={"user_id": user_id})


def _handle_invoice_succeeded(invoice: dict) -> None:
    """Reset monthly scan counter on each successful renewal."""
    customer_id = invoice.get("customer")
    if not customer_id or invoice.get("billing_reason") != "subscription_cycle":
        return

    table = _subscriptions_table()
    resp = table.query(
        IndexName="stripe-customer-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("stripe_customer_id").eq(
            customer_id
        ),
        Limit=1,
    )
    items = resp.get("Items", [])
    if not items:
        return

    user_id = items[0]["user_id"]
    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET scan_count_month = :zero, payment_past_due = :f, updated_at = :now",
        ExpressionAttributeValues={":zero": 0, ":f": False, ":now": _now()},
    )
    logger.info("Scan count reset for new billing period", extra={"user_id": user_id})


def _handle_invoice_failed(invoice: dict) -> None:
    customer_id = invoice.get("customer")
    if not customer_id:
        return

    table = _subscriptions_table()
    resp = table.query(
        IndexName="stripe-customer-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("stripe_customer_id").eq(
            customer_id
        ),
        Limit=1,
    )
    items = resp.get("Items", [])
    if not items:
        return

    user_id = items[0]["user_id"]
    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET payment_past_due = :t, updated_at = :now",
        ExpressionAttributeValues={":t": True, ":now": _now()},
    )
    logger.warning("Payment failed — marked past_due", extra={"user_id": user_id})


_HANDLERS = {
    "checkout.session.completed": lambda e: _handle_checkout_completed(
        e["data"]["object"]
    ),
    "customer.subscription.updated": lambda e: _handle_subscription_updated(
        e["data"]["object"]
    ),
    "customer.subscription.deleted": lambda e: _handle_subscription_deleted(
        e["data"]["object"]
    ),
    "invoice.payment_succeeded": lambda e: _handle_invoice_succeeded(
        e["data"]["object"]
    ),
    "invoice.payment_failed": lambda e: _handle_invoice_failed(e["data"]["object"]),
}


def handler(event: dict, context: object) -> dict:
    _init_stripe()

    body = event.get("body", "")
    if event.get("isBase64Encoded"):
        import base64

        body = base64.b64decode(body)
    elif isinstance(body, str):
        body = body.encode()

    sig_header = event.get("headers", {}).get("stripe-signature", "")

    try:
        stripe_event = stripe.Webhook.construct_event(
            body, sig_header, _get_webhook_secret()
        )
    except stripe.error.SignatureVerificationError:  # type: ignore[attr-defined]
        logger.warning("Invalid Stripe signature")
        return {"statusCode": 400, "body": "Invalid signature"}

    event_type = stripe_event["type"]
    dispatch = _HANDLERS.get(event_type)
    if dispatch:
        try:
            dispatch(stripe_event)
        except Exception as exc:
            logger.error(
                "Webhook handler error",
                extra={"event_type": event_type, "error": str(exc)},
            )
            return {"statusCode": 500, "body": "Handler error"}
    else:
        logger.debug("Unhandled event type", extra={"event_type": event_type})

    return {"statusCode": 200, "body": json.dumps({"received": True})}
