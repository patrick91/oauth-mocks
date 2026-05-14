"""
Google OAuth Mock Server

A stateless mock implementation of Google's OAuth 2.0 and OpenID Connect
endpoints for testing. Authorization codes and access tokens are
self-contained, and ID tokens are signed with a stable RS256 key exposed via
JWKS so normal OIDC validation paths work.

Email verification status is determined by the email pattern:
- Emails starting with "unverified" -> email_verified: false
- All other emails -> email_verified: true
"""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .auth import (
    DEFAULT_SCOPE,
    FAIL_CLIENT_ID,
    ISSUER,
    build_redirect_url,
    create_id_token,
    decode_token,
    encode_token,
    generate_name,
    generate_subject,
    is_email_verified,
    public_jwk,
)
from .models import GoogleUserInfo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT_DIR / "templates"

app = FastAPI(
    title="Google OAuth Mock",
    description="Stateless mock Google OAuth 2.0 / OIDC server for testing",
)


def render_template(name: str, context: dict[str, str]) -> str:
    template = (TEMPLATES_DIR / name).read_text()
    for key, value in context.items():
        template = template.replace(f"{{{{{key}}}}}", value)
    return template


def _extract_access_token(authorization: str | None) -> dict[str, str]:
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_request", "error_description": "Missing token"},
        )

    token = authorization
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1]

    token_data = decode_token(token)
    if not token_data or "email" not in token_data:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_token",
                "error_description": "Invalid access token",
            },
        )

    return token_data


@app.get("/", response_class=HTMLResponse)
def root() -> str:
    return (TEMPLATES_DIR / "index.html").read_text()


@app.get("/.well-known/openid-configuration")
def openid_configuration(request: Request) -> dict[str, object]:
    base_url = str(request.base_url).rstrip("/")
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{base_url}/o/oauth2/v2/auth",
        "token_endpoint": f"{base_url}/token",
        "userinfo_endpoint": f"{base_url}/oauth2/v2/userinfo",
        "jwks_uri": f"{base_url}/oauth2/v3/certs",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": ["openid", "email", "profile"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_post",
            "client_secret_basic",
        ],
        "claims_supported": [
            "sub",
            "email",
            "email_verified",
            "name",
            "given_name",
            "picture",
            "nonce",
        ],
    }


@app.get("/oauth2/v3/certs")
def jwks() -> dict[str, list[dict[str, object]]]:
    return {"keys": [public_jwk()]}


@app.get("/o/oauth2/v2/auth", response_class=HTMLResponse)
async def authorize_form(
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    response_type: str = Query("code"),
    scope: str = Query(DEFAULT_SCOPE),
    state: str | None = Query(None),
    code_challenge: str | None = Query(None),
    code_challenge_method: str | None = Query(None),
    nonce: str | None = Query(None),
    login_hint: str | None = Query(None),
) -> str:
    logger.info(
        "GET /o/oauth2/v2/auth - client_id=%s redirect_uri=%s scope=%s",
        client_id,
        redirect_uri,
        scope,
    )

    if response_type != "code":
        params = {"error": "unsupported_response_type"}
        if state:
            params["state"] = state
        return RedirectResponse(
            url=build_redirect_url(redirect_uri, params),
            status_code=302,
        )

    return render_template(
        "authorize.html",
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state or "",
            "code_challenge": code_challenge or "",
            "code_challenge_method": code_challenge_method or "",
            "nonce": nonce or "",
            "login_hint": login_hint or "",
        },
    )


@app.post("/o/oauth2/v2/auth")
async def authorize_submit(
    client_id: Annotated[str, Form()],
    redirect_uri: Annotated[str, Form()],
    email: Annotated[str, Form()],
    scope: Annotated[str, Form()] = DEFAULT_SCOPE,
    state: Annotated[str, Form()] = "",
    code_challenge: Annotated[str, Form()] = "",
    code_challenge_method: Annotated[str, Form()] = "",
    nonce: Annotated[str, Form()] = "",
):
    logger.info(
        "POST /o/oauth2/v2/auth - client_id=%s email=%s redirect_uri=%s scope=%s",
        client_id,
        email,
        redirect_uri,
        scope,
    )

    if client_id == FAIL_CLIENT_ID:
        params = {
            "error": "invalid_client",
            "error_description": "Client id is configured to fail in this mock",
        }
        if state:
            params["state"] = state
        return RedirectResponse(
            url=build_redirect_url(redirect_uri, params),
            status_code=302,
        )

    code = encode_token(
        {
            "email": email,
            "scope": scope or DEFAULT_SCOPE,
            "client_id": client_id,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
        }
    )

    params = {"code": code}
    if state:
        params["state"] = state

    return RedirectResponse(
        url=build_redirect_url(redirect_uri, params),
        status_code=302,
    )


@app.post("/token")
@app.post("/oauth2/token")
async def token(
    client_id: Annotated[str, Form()],
    client_secret: Annotated[str | None, Form()] = None,
    code: Annotated[str | None, Form()] = None,
    redirect_uri: Annotated[str | None, Form()] = None,
    grant_type: Annotated[str, Form()] = "authorization_code",
    code_verifier: Annotated[str | None, Form()] = None,
):
    _ = client_secret, redirect_uri, code_verifier

    if client_id == FAIL_CLIENT_ID:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_client",
                "error_description": "Client id is configured to fail in this mock",
            },
        )

    if grant_type != "authorization_code":
        return JSONResponse(
            status_code=400,
            content={
                "error": "unsupported_grant_type",
                "error_description": "The grant_type is invalid or unsupported.",
            },
        )

    if not code:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_grant",
                "error_description": "Missing authorization code.",
            },
        )

    code_data = decode_token(code)
    if not code_data or "email" not in code_data:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_grant",
                "error_description": "The code passed is incorrect or expired.",
            },
        )

    email = code_data["email"]
    scope = code_data.get("scope") or DEFAULT_SCOPE
    nonce = code_data.get("nonce") or None
    token_client_id = code_data.get("client_id") or client_id
    access_token = encode_token(
        {
            "email": email,
            "scope": scope,
            "client_id": token_client_id,
        }
    )

    return {
        "access_token": access_token,
        "expires_in": 3600,
        "scope": scope,
        "token_type": "Bearer",
        "id_token": create_id_token(
            email=email,
            client_id=token_client_id,
            nonce=nonce,
        ),
    }


@app.get("/oauth2/v2/userinfo", response_model=GoogleUserInfo)
@app.get("/userinfo", response_model=GoogleUserInfo)
async def userinfo(
    authorization: Annotated[str | None, Header()] = None,
) -> GoogleUserInfo:
    token_data = _extract_access_token(authorization)

    email = token_data["email"]
    name = generate_name(email)
    return GoogleUserInfo(
        sub=generate_subject(email),
        email=email,
        email_verified=is_email_verified(email),
        name=name,
        given_name=name.split(" ", 1)[0],
        picture=f"https://lh3.googleusercontent.com/a/mock-{generate_subject(email)}",
    )
