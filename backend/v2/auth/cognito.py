"""
Extracts verified Cognito claims from the API Gateway JWT authorizer context.

API Gateway HTTP API JWT authorizer validates the token before Lambda is invoked,
so we only need to unpack the pre-verified claims from the event context.
"""

from typing import Any

from fastapi import HTTPException, Request, status


def get_current_user(request: Request) -> dict[str, Any]:
    """Return authenticated user dict from API Gateway JWT authorizer claims."""
    aws_event = request.scope.get("aws.event", {})
    claims = (
        aws_event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        )
    return {
        "user_id": user_id,
        "email": claims.get("email", ""),
        "username": claims.get("cognito:username", user_id),
    }
