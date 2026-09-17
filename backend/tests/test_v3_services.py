"""Unit tests for v3 service layer and webhook handler."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("SUBSCRIPTIONS_TABLE", "test-subscriptions")
os.environ.setdefault("API_KEYS_TABLE", "test-api-keys")
os.environ.setdefault("ORGS_TABLE", "test-orgs")
os.environ.setdefault("DYNAMODB_V2_TABLE", "test-scans-v2")
os.environ.setdefault("DYNAMODB_TABLE", "test-scans-v2")
os.environ.setdefault("STRIPE_SECRET_MANAGER_PATH", "img-analyzer/test/stripe")
os.environ.setdefault("STRIPE_PRO_PRICE_ID", "price_pro_test")
os.environ.setdefault("STRIPE_ENTERPRISE_PRICE_ID", "price_enterprise_test")

# ── api_key_service ────────────────────────────────────────────────────────────


@patch("v3.services.api_key_service.db")
def test_create_api_key_ok(mock_db):
    from v3.services.api_key_service import create_api_key

    mock_db.list_api_keys.return_value = []
    mock_db.put_api_key.return_value = None

    result = create_api_key("user-1", "CI key")

    assert result["raw_key"].startswith("dia_")
    assert len(result["raw_key"]) == 4 + 64  # "dia_" + 64 hex chars
    assert result["name"] == "CI key"
    assert "key_id" in result
    mock_db.put_api_key.assert_called_once()


@patch("v3.services.api_key_service.db")
def test_create_api_key_max_limit(mock_db):
    from fastapi import HTTPException

    from v3.services.api_key_service import create_api_key

    mock_db.list_api_keys.return_value = [
        {"key_id": f"k{i}", "revoked": False} for i in range(10)
    ]

    with pytest.raises(HTTPException) as exc:
        create_api_key("user-1", "overflow key")
    assert exc.value.status_code == 400


@patch("v3.services.api_key_service.db")
def test_revoke_api_key_ok(mock_db):
    from v3.services.api_key_service import revoke_api_key

    mock_db.get_api_key.return_value = {"key_id": "k1", "user_id": "user-1"}
    mock_db.revoke_api_key.return_value = None

    revoke_api_key("user-1", "k1")
    mock_db.revoke_api_key.assert_called_once_with("k1")


@patch("v3.services.api_key_service.db")
def test_revoke_api_key_not_found(mock_db):
    from fastapi import HTTPException

    from v3.services.api_key_service import revoke_api_key

    mock_db.get_api_key.return_value = None

    with pytest.raises(HTTPException) as exc:
        revoke_api_key("user-1", "missing")
    assert exc.value.status_code == 404


@patch("v3.services.api_key_service.db")
def test_revoke_api_key_forbidden(mock_db):
    from fastapi import HTTPException

    from v3.services.api_key_service import revoke_api_key

    mock_db.get_api_key.return_value = {"key_id": "k1", "user_id": "other-user"}

    with pytest.raises(HTTPException) as exc:
        revoke_api_key("user-1", "k1")
    assert exc.value.status_code == 403


# ── org_service ────────────────────────────────────────────────────────────────


@patch("v3.services.org_service.db")
@patch("v3.services.org_service.require_org_feature")
def test_create_org_ok(mock_require, mock_db):
    from v3.services.org_service import create_org

    mock_db.get_org_by_admin.return_value = None
    mock_db.put_org.return_value = None

    result = create_org("user-1", "Acme Corp")

    assert result["name"] == "Acme Corp"
    assert result["admin_user_id"] == "user-1"
    assert isinstance(result["member_ids"], list)
    mock_db.put_org.assert_called_once()


@patch("v3.services.org_service.db")
@patch("v3.services.org_service.require_org_feature")
def test_create_org_already_exists(mock_require, mock_db):
    from fastapi import HTTPException

    from v3.services.org_service import create_org

    mock_db.get_org_by_admin.return_value = {"org_id": "existing"}

    with pytest.raises(HTTPException) as exc:
        create_org("user-1", "Dupe Corp")
    assert exc.value.status_code == 400


@patch("v3.services.org_service.db")
@patch("v3.services.org_service.require_org_feature")
def test_get_org_not_found(mock_require, mock_db):
    from fastapi import HTTPException

    from v3.services.org_service import get_org

    mock_db.get_org_by_admin.return_value = None

    with pytest.raises(HTTPException) as exc:
        get_org("user-1")
    assert exc.value.status_code == 404


@patch("v3.services.org_service.db")
@patch("v3.services.org_service.require_org_feature")
def test_add_member_forbidden(mock_require, mock_db):
    from fastapi import HTTPException

    from v3.services.org_service import add_member

    mock_db.get_org.return_value = {"org_id": "org-1", "admin_user_id": "other-admin"}

    with pytest.raises(HTTPException) as exc:
        add_member("user-1", "org-1", "new-member")
    assert exc.value.status_code == 403


# ── webhook handler ────────────────────────────────────────────────────────────


@patch("webhooks.stripe_handler._get_webhook_secret", return_value="whsec_test")
@patch("webhooks.stripe_handler._init_stripe")
@patch("webhooks.stripe_handler.stripe")
def test_webhook_invalid_signature(mock_stripe, mock_init, mock_secret):
    import stripe as real_stripe

    mock_stripe.Webhook.construct_event.side_effect = (
        real_stripe.error.SignatureVerificationError("bad sig", "header")
    )
    mock_stripe.error = real_stripe.error

    from webhooks.stripe_handler import handler

    event = {
        "body": json.dumps({"type": "test"}),
        "isBase64Encoded": False,
        "headers": {"stripe-signature": "bad"},
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 400


@patch("webhooks.stripe_handler._get_webhook_secret", return_value="whsec_test")
@patch("webhooks.stripe_handler._init_stripe")
@patch("webhooks.stripe_handler.stripe")
def test_webhook_unhandled_event(mock_stripe, mock_init, mock_secret):
    mock_stripe.Webhook.construct_event.return_value = {
        "type": "some.unhandled.event",
        "data": {"object": {}},
    }

    from webhooks.stripe_handler import handler

    event = {
        "body": json.dumps({"type": "noop"}),
        "isBase64Encoded": False,
        "headers": {"stripe-signature": "valid"},
    }
    resp = handler(event, None)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["received"] is True


@patch("webhooks.stripe_handler._subscriptions_table")
@patch("webhooks.stripe_handler._get_webhook_secret", return_value="whsec_test")
@patch("webhooks.stripe_handler._init_stripe")
@patch("webhooks.stripe_handler.stripe")
def test_webhook_checkout_completed(mock_stripe, mock_init, mock_secret, mock_table):
    mock_stripe.Webhook.construct_event.return_value = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test",
                "client_reference_id": "user-1",
                "customer": "cus_abc",
                "subscription": None,
            }
        },
    }
    mock_table_instance = MagicMock()
    mock_table.return_value = mock_table_instance

    from webhooks.stripe_handler import handler

    resp = handler(
        {
            "body": "{}",
            "isBase64Encoded": False,
            "headers": {"stripe-signature": "v1=sig"},
        },
        None,
    )
    assert resp["statusCode"] == 200
    mock_table_instance.update_item.assert_called_once()


@patch("webhooks.stripe_handler._subscriptions_table")
@patch("webhooks.stripe_handler._get_webhook_secret", return_value="whsec_test")
@patch("webhooks.stripe_handler._init_stripe")
@patch("webhooks.stripe_handler.stripe")
def test_webhook_invoice_payment_succeeded_resets_count(
    mock_stripe, mock_init, mock_secret, mock_table
):
    mock_stripe.Webhook.construct_event.return_value = {
        "type": "invoice.payment_succeeded",
        "data": {
            "object": {
                "customer": "cus_abc",
                "billing_reason": "subscription_cycle",
            }
        },
    }
    mock_table_instance = MagicMock()
    mock_table.return_value = mock_table_instance
    mock_table_instance.query.return_value = {
        "Items": [{"user_id": "user-1", "stripe_customer_id": "cus_abc"}]
    }

    from webhooks.stripe_handler import handler

    resp = handler(
        {
            "body": "{}",
            "isBase64Encoded": False,
            "headers": {"stripe-signature": "v1=sig"},
        },
        None,
    )
    assert resp["statusCode"] == 200
    mock_table_instance.update_item.assert_called_once()
    call_expr = mock_table_instance.update_item.call_args[1]["UpdateExpression"]
    assert "scan_count_month" in call_expr


@patch("webhooks.stripe_handler._subscriptions_table")
@patch("webhooks.stripe_handler._get_webhook_secret", return_value="whsec_test")
@patch("webhooks.stripe_handler._init_stripe")
@patch("webhooks.stripe_handler.stripe")
def test_webhook_invoice_payment_failed(
    mock_stripe, mock_init, mock_secret, mock_table
):
    mock_stripe.Webhook.construct_event.return_value = {
        "type": "invoice.payment_failed",
        "data": {"object": {"customer": "cus_abc"}},
    }
    mock_table_instance = MagicMock()
    mock_table.return_value = mock_table_instance
    mock_table_instance.query.return_value = {
        "Items": [{"user_id": "user-1", "stripe_customer_id": "cus_abc"}]
    }

    from webhooks.stripe_handler import handler

    resp = handler(
        {
            "body": "{}",
            "isBase64Encoded": False,
            "headers": {"stripe-signature": "v1=sig"},
        },
        None,
    )
    assert resp["statusCode"] == 200
    call_expr = mock_table_instance.update_item.call_args[1]["UpdateExpression"]
    assert "payment_past_due" in call_expr


# ── stripe_service ────────────────────────────────────────────────────────────


@patch("v3.services.stripe_service.stripe")
@patch("v3.services.stripe_service.boto3")
def test_create_checkout_session(mock_boto3, mock_stripe):
    import v3.services.stripe_service as svc

    svc._stripe_initialized = False
    mock_secrets = MagicMock()
    mock_boto3.client.return_value = mock_secrets
    mock_secrets.get_secret_value.return_value = {"SecretString": "sk_test_fake"}

    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/pay/cs_test"
    mock_stripe.checkout.Session.create.return_value = mock_session

    url = svc.create_checkout_session(
        user_id="user-1",
        email="test@example.com",
        price_id="price_pro_test",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
    )
    assert url == "https://checkout.stripe.com/pay/cs_test"


@patch("v3.services.stripe_service.stripe")
@patch("v3.services.stripe_service.boto3")
def test_create_portal_session(mock_boto3, mock_stripe):
    import v3.services.stripe_service as svc

    svc._stripe_initialized = True  # already initialized

    mock_portal = MagicMock()
    mock_portal.url = "https://billing.stripe.com/session/test"
    mock_stripe.billing_portal.Session.create.return_value = mock_portal

    url = svc.create_portal_session("cus_abc", "https://example.com/billing")
    assert url == "https://billing.stripe.com/session/test"


@patch("v3.services.stripe_service.boto3")
def test_get_webhook_secret(mock_boto3):
    import v3.services.stripe_service as svc

    mock_secrets = MagicMock()
    mock_boto3.client.return_value = mock_secrets
    mock_secrets.get_secret_value.return_value = {"SecretString": "whsec_test"}
    svc._secrets_client = None

    secret = svc.get_webhook_secret()
    assert secret == "whsec_test"


# ── entitlements ───────────────────────────────────────────────────────────────


@patch("v3.middleware.entitlements.db")
def test_require_org_feature_free_tier(mock_db):
    from fastapi import HTTPException

    from v3.middleware.entitlements import require_org_feature

    mock_db.get_subscription.return_value = {"tier": "free"}

    with pytest.raises(HTTPException) as exc:
        require_org_feature("user-1")
    assert exc.value.status_code == 403
    assert "Enterprise" in exc.value.detail


@patch("v3.middleware.entitlements.db")
def test_require_image_scan_free_tier(mock_db):
    from fastapi import HTTPException

    from v3.middleware.entitlements import require_image_scan

    mock_db.get_subscription.return_value = {"tier": "free"}

    with pytest.raises(HTTPException) as exc:
        require_image_scan("user-1")
    assert exc.value.status_code == 403


@patch("v3.middleware.entitlements.db")
def test_check_scan_quota_enterprise_unlimited(mock_db):
    from v3.middleware.entitlements import check_scan_quota

    mock_db.get_subscription.return_value = {
        "tier": "enterprise",
        "scan_count_month": 9999,
    }

    sub = check_scan_quota("user-1")
    assert sub["tier"] == "enterprise"
