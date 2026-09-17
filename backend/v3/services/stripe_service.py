"""Stripe billing operations for API v3."""

import os

import boto3
import stripe

_secrets_client = None
_stripe_initialized = False


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


def create_checkout_session(
    user_id: str, email: str, price_id: str, success_url: str, cancel_url: str
) -> str:
    _init_stripe()
    session = stripe.checkout.Session.create(
        customer_email=email,
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=user_id,
        subscription_data={"metadata": {"user_id": user_id}},
    )
    return session.url  # type: ignore[return-value]


def create_portal_session(stripe_customer_id: str, return_url: str) -> str:
    _init_stripe()
    session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=return_url,
    )
    return session.url  # type: ignore[return-value]


def get_webhook_secret() -> str:
    path = os.environ["STRIPE_SECRET_MANAGER_PATH"]
    return _get_secret(f"{path}/webhook-signing-secret")


def construct_webhook_event(payload: bytes, sig_header: str) -> stripe.Event:
    _init_stripe()
    secret = get_webhook_secret()
    return stripe.Webhook.construct_event(payload, sig_header, secret)
