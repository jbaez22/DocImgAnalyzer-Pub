"""
User identity resolution for API v3.

JWT routes: API Gateway JWT authorizer validates the Cognito token before Lambda
is invoked — claims are unpacked from the event context.

Analyze routes (no API GW authorizer): the Lambda manually decodes the Bearer
token from the Authorization header using PyJWT + Cognito JWKS, OR validates an
X-Api-Key header against the DynamoDB api-keys table (SHA-256 hash comparison).
This lets browser users and CI/CD tools share the same endpoint.
"""

import os
from typing import Any

import jwt
from fastapi import HTTPException, Request, status

from ..db import dynamodb as db

_REGION = os.environ.get("AWS_REGION", "us-east-1")
_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
_CLIENT_ID = os.environ.get("COGNITO_APP_CLIENT_ID", "")
_ISSUER = f"https://cognito-idp.{_REGION}.amazonaws.com/{_POOL_ID}"
_JWKS_URL = f"{_ISSUER}/.well-known/jwks.json"

_jwks_client: jwt.PyJWKClient | None = None


def _get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(_JWKS_URL)
    return _jwks_client


def _decode_bearer(token: str) -> dict[str, Any]:
    """Decode and verify a Cognito ID token. Returns claims or raises HTTPException."""
    try:
        client = _get_jwks_client()
        signing_key = client.get_signing_key_from_jwt(token)
        data: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            # Cognito ID token aud = app client ID; issuer = pool URL
            audience=_CLIENT_ID or None,
            issuer=_ISSUER or None,
            options={"verify_exp": True, "verify_aud": bool(_CLIENT_ID)},
        )
        return data
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )


def _claims_from_event(request: Request) -> dict[str, str]:
    """Extract JWT claims injected by the API Gateway JWT authorizer (JWT-protected routes)."""
    aws_event = request.scope.get("aws.event", {})
    return (
        aws_event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )


def get_current_user(request: Request) -> dict[str, Any]:
    """Require a valid Cognito JWT (pre-verified by API Gateway JWT authorizer)."""
    claims = _claims_from_event(request)
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        )
    return {
        "user_id": user_id,
        "email": claims.get("email", ""),
        "username": claims.get("cognito:username", user_id),
        "auth_method": "jwt",
    }


def get_current_user_or_api_key(request: Request) -> dict[str, Any]:
    """
    Accept either a Cognito JWT or an X-Api-Key header.

    Used on /api/v3/analyze/* routes (no API Gateway JWT authorizer) so that:
    - Browser users pass Authorization: Bearer <cognito-token>
    - CI/CD callers pass X-Api-Key: dia_<key>
    """
    # 1 — try event context (route has JWT authorizer — shouldn't happen but harmless)
    claims = _claims_from_event(request)
    if claims.get("sub"):
        return {
            "user_id": claims["sub"],
            "email": claims.get("email", ""),
            "username": claims.get("cognito:username", claims["sub"]),
            "auth_method": "jwt",
        }

    # 2 — try Bearer token (manual decode — route has NONE authorizer)
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        decoded = _decode_bearer(token)
        return {
            "user_id": decoded["sub"],
            "email": decoded.get("email", ""),
            "username": decoded.get("cognito:username", decoded["sub"]),
            "auth_method": "jwt",
        }

    # 3 — try X-Api-Key
    raw_key = request.headers.get("X-Api-Key", "").strip()
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Provide a Bearer token or X-Api-Key header",
        )

    key_record = db.validate_api_key(raw_key)
    if not key_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
        )

    db.touch_api_key(key_record["key_id"])

    return {
        "user_id": key_record["user_id"],
        "email": "",
        "username": key_record["user_id"],
        "auth_method": "api_key",
        "key_id": key_record["key_id"],
    }
