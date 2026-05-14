import base64
import hashlib
import json
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response

FAIL_CLIENT_ID = "fail-client-id"
FAIL_REFRESH_TOKEN = "fail-refresh-token"
DEFAULT_SCOPE = ""


def encode_token(email: str, scope: str) -> str:
    """
    Encode email and scope into a self-contained token.

    The token is simply base64-encoded JSON containing the email and scope.
    This makes the mock completely stateless - no storage needed.
    """
    data = {"email": email, "scope": scope}
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def decode_token(token: str) -> dict[str, str] | None:
    """
    Decode token to extract email and scope.

    Returns None if the token is invalid or cannot be decoded.
    """
    try:
        # Handle potential padding issues
        padded = token + "=" * (-len(token) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode())
        if not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None


def is_email_verified(email: str) -> bool:
    """Determine if email should be marked as verified based on pattern."""
    return not email.lower().startswith("unverified")


def generate_user_id(email: str) -> int:
    """Generate a consistent user ID from email."""
    return int(hashlib.md5(email.encode()).hexdigest()[:8], 16)


def generate_login(email: str) -> str:
    """Generate a login/username from email."""
    return email.split("@")[0].replace(".", "").replace("+", "")


def parse_scopes(scope: str | None) -> set[str]:
    """Parse OAuth scope string into a set of scopes."""
    if not scope:
        return set()
    return {item for item in scope.split() if item}


def wants_json(accept_header: str) -> bool:
    """Return True when the caller prefers JSON responses."""
    return "application/json" in accept_header.lower()


def build_redirect_url(redirect_uri: str, params: dict[str, str]) -> str:
    """Append params to redirect_uri while preserving existing query string."""
    parsed = urlparse(redirect_uri)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(params)
    return urlunparse(parsed._replace(query=urlencode(query)))


def token_response(payload: dict[str, str], accept_header: str, status_code: int = 200) -> Response:
    """Return a token response matching GitHub's format negotiation."""
    if wants_json(accept_header):
        return JSONResponse(payload, status_code=status_code)
    return Response(
        content=urlencode(payload),
        media_type="application/x-www-form-urlencoded",
        status_code=status_code,
    )


def extract_token_data_from_auth(authorization: str | None) -> dict[str, str]:
    """
    Extract token payload from Authorization header.

    Raises HTTPException with 401 if token is invalid.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Requires authentication")

    token = authorization
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() in {"bearer", "token"}:
        token = parts[1]

    data = decode_token(token)
    if not data or "email" not in data:
        raise HTTPException(status_code=401, detail="Bad credentials")

    scope = data.get("scope", DEFAULT_SCOPE)
    if not isinstance(scope, str):
        scope = DEFAULT_SCOPE
    if scope is None:
        scope = DEFAULT_SCOPE
    data["scope"] = scope

    return data


def extract_email_from_auth(authorization: str | None) -> str:
    """Extract email from Authorization header."""
    return extract_token_data_from_auth(authorization)["email"]


def require_scope(token_data: dict[str, str], required_scope: str) -> None:
    """Ensure a token includes the required scope."""
    scopes = parse_scopes(token_data.get("scope"))
    if required_scope not in scopes:
        raise HTTPException(
            status_code=403,
            detail=f"Requires {required_scope} scope",
        )
