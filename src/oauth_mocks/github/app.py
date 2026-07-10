"""
GitHub OAuth Mock Server

A stateless mock implementation of GitHub's OAuth endpoints for testing.
Email verification status is determined by the email pattern:
- Emails starting with "unverified" -> verified: false
- All other emails -> verified: true

This mock is completely stateless - tokens are self-contained and encode
the user's email and scope, eliminating the need for shared storage across replicas.

Endpoints:
- GET  /login/oauth/authorize - Login form
- POST /login/oauth/authorize - Process login and redirect
- POST /login/oauth/access_token - Token exchange
- GET  /api/user - User profile
- GET  /api/user/emails - User emails with verification status
- GET  /api/repositories/{repository_id} - Repository by id
"""

import logging
from importlib.resources import files
from typing import Annotated

from fastapi import FastAPI, Form, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from .auth import (
    DEFAULT_SCOPE,
    FAIL_CLIENT_ID,
    FAIL_REFRESH_TOKEN,
    build_redirect_url,
    decode_token,
    encode_token,
    extract_email_from_auth,
    extract_token_data_from_auth,
    generate_login,
    generate_user_id,
    is_email_verified,
    parse_scopes,
    require_scope,
    token_response,
)
from .models import (
    GitHubCommit,
    GitHubCommitData,
    GitHubEmail,
    GitHubInstallation,
    GitHubInstallationAccount,
    GitHubInstallationRepositoriesResponse,
    GitHubInstallationsResponse,
    GitHubRepository,
    GitHubRepositoryOwner,
    GitHubUser,
)

logger = logging.getLogger(__name__)

TEMPLATES_DIR = files("oauth_mocks.github") / "templates"

app = FastAPI(
    title="GitHub OAuth Mock",
    description="Stateless mock GitHub OAuth server for testing",
)

USER_INSTALLATION_ID = 1001
ORG_INSTALLATION_ID = 2002
ORG_LOGIN = "mock-org"

# User-type installation repos — owner/full_name are filled dynamically per request.
_USER_REPO_TEMPLATES = [
    {"id": 101, "name": "demo-repo", "private": True},
    {"id": 102, "name": "playwright-repo", "private": False},
]

# Repo names belonging to the user installation (for lookup by name).
_USER_REPO_NAMES = {r["name"] for r in _USER_REPO_TEMPLATES}

ORG_REPOSITORIES = [
    GitHubRepository(
        id=201,
        name="org-repo",
        full_name=f"{ORG_LOGIN}/org-repo",
        private=True,
        owner=GitHubRepositoryOwner(login=ORG_LOGIN),
    ),
    GitHubRepository(
        id=202,
        name="org-public-repo",
        full_name=f"{ORG_LOGIN}/org-public-repo",
        private=False,
        owner=GitHubRepositoryOwner(login=ORG_LOGIN),
    ),
]

ORG_REPO_NAMES = {r.name for r in ORG_REPOSITORIES}


def _build_installations(login: str) -> list[GitHubInstallation]:
    return [
        GitHubInstallation(
            id=USER_INSTALLATION_ID,
            account=GitHubInstallationAccount(login=login, type="User"),
        ),
        GitHubInstallation(
            id=ORG_INSTALLATION_ID,
            account=GitHubInstallationAccount(login=ORG_LOGIN, type="Organization"),
        ),
    ]


def _build_user_repositories(login: str) -> list[GitHubRepository]:
    return [
        GitHubRepository(
            id=t["id"],
            name=t["name"],
            full_name=f"{login}/{t['name']}",
            private=t["private"],
            owner=GitHubRepositoryOwner(login=login),
        )
        for t in _USER_REPO_TEMPLATES
    ]


def _find_repository_by_id(login: str, repository_id: int) -> GitHubRepository | None:
    for repository in _build_user_repositories(login):
        if repository.id == repository_id:
            return repository

    for repository in ORG_REPOSITORIES:
        if repository.id == repository_id:
            return repository

    return None


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log validation errors with full details for debugging."""
    logger.error(
        f"Validation error on {request.method} {request.url.path}\n"
        f"  Query params: {dict(request.query_params)}\n"
        f"  Errors: {exc.errors()}"
    )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


def render_template(name: str, context: dict[str, str]) -> str:
    template = (TEMPLATES_DIR / name).read_text(encoding="utf-8")
    for key, value in context.items():
        template = template.replace(f"{{{{{key}}}}}", value)
    return template


@app.get("/", response_class=HTMLResponse)
def root():
    """Serve the intro page."""
    template_path = TEMPLATES_DIR / "index.html"
    return template_path.read_text(encoding="utf-8")


@app.get("/api")
def api_info():
    """Health check and info endpoint."""
    return {
        "service": "GitHub OAuth Mock",
        "version": "2.0.0",
        "description": "Stateless mock - tokens are self-contained",
        "rules": {
            "unverified@*": "verified: false",
            "*": "verified: true",
        },
        "oauth": {
            "default_scope": DEFAULT_SCOPE,
            "email_scope": "user:email",
        },
        "special_clients": {
            "fail": FAIL_CLIENT_ID,
        },
        "special_tokens": {
            "fail_refresh": FAIL_REFRESH_TOKEN,
        },
        "endpoints": {
            "authorize": "/login/oauth/authorize",
            "token": "/login/oauth/access_token",
            "user": "/api/user",
            "emails": "/api/user/emails",
            "installations": "/api/user/installations",
            "installation_repositories": "/api/user/installations/{installation_id}/repositories",
            "repository_by_id": "/api/repositories/{repository_id}",
            "repository_installation": "/api/repos/{owner}/{repo}/installation",
        },
    }


@app.get("/login/oauth/authorize", response_class=HTMLResponse)
async def authorize_form(
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    scope: str = Query(""),
    state: str | None = Query(None),
    code_challenge: str | None = Query(None),
    code_challenge_method: str | None = Query(None),
):
    """Show login form for GitHub OAuth mock."""
    logger.info(
        f"GET /login/oauth/authorize - client_id={client_id}, "
        f"redirect_uri={redirect_uri}, scope={scope}"
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
        },
    )


@app.post("/login/oauth/authorize")
async def authorize_submit(
    client_id: Annotated[str, Form()],
    redirect_uri: Annotated[str, Form()],
    email: Annotated[str, Form()],
    scope: Annotated[str, Form()] = "",
    state: Annotated[str, Form()] = "",
    code_challenge: Annotated[str, Form()] = "",
    code_challenge_method: Annotated[str, Form()] = "",
):
    """Process login form and redirect with auth code."""
    logger.info(
        f"POST /login/oauth/authorize - client_id={client_id}, "
        f"email={email}, redirect_uri={redirect_uri}, scope={scope}"
    )
    if client_id == FAIL_CLIENT_ID:
        params = {
            "error": "invalid_client",
            "error_description": "Client id is configured to fail in this mock",
        }
        if state:
            params["state"] = state
        redirect_url = build_redirect_url(redirect_uri, params)
        return RedirectResponse(url=redirect_url, status_code=302)

    # Generate self-contained auth code (encodes the email)
    requested_scope = scope or DEFAULT_SCOPE
    code = encode_token(email, requested_scope)

    # Build redirect URL
    params = {"code": code}
    if state:
        params["state"] = state

    redirect_url = build_redirect_url(redirect_uri, params)
    return RedirectResponse(url=redirect_url, status_code=302)


@app.post("/login/oauth/access_token")
async def token(
    request: Request,
    client_id: Annotated[str, Form()],
    client_secret: Annotated[str | None, Form()] = None,
    code: Annotated[str | None, Form()] = None,
    redirect_uri: Annotated[str | None, Form()] = None,
    code_verifier: Annotated[str | None, Form()] = None,
    grant_type: Annotated[str, Form()] = "authorization_code",
    refresh_token: Annotated[str | None, Form()] = None,
):
    """
    Token exchange endpoint.

    GitHub returns tokens as form-urlencoded by default,
    but accepts Accept: application/json header for JSON response.

    Supports both authorization_code and refresh_token grant types.
    """
    accept = request.headers.get("accept", "")
    if client_id == FAIL_CLIENT_ID:
        return token_response(
            {
                "error": "invalid_client",
                "error_description": "Client id is configured to fail in this mock",
            },
            accept,
            status_code=400,
        )

    if grant_type == "refresh_token":
        return _handle_refresh_token(refresh_token, accept)

    if grant_type != "authorization_code":
        return token_response(
            {
                "error": "unsupported_grant_type",
                "error_description": "The grant_type is invalid or unsupported.",
            },
            accept,
            status_code=400,
        )

    if not code:
        return token_response(
            {
                "error": "bad_verification_code",
                "error_description": "The code passed is incorrect or expired.",
            },
            accept,
            status_code=400,
        )

    # Decode email from the self-contained auth code
    token_data = decode_token(code)
    if not token_data or "email" not in token_data:
        return token_response(
            {
                "error": "bad_verification_code",
                "error_description": "The code passed is incorrect or expired.",
            },
            accept,
            status_code=400,
        )
    email = token_data["email"]
    scope = token_data.get("scope") or DEFAULT_SCOPE
    if not isinstance(scope, str):
        scope = DEFAULT_SCOPE

    # Generate self-contained access token (same format, encodes email)
    access_token = encode_token(email, scope)

    # Generate a refresh token (same self-contained format)
    new_refresh_token = encode_token(email, scope)

    response_data = {
        "access_token": access_token,
        "token_type": "bearer",
        "scope": scope,
        "refresh_token": new_refresh_token,
        "refresh_token_expires_in": 15897600,
    }

    return token_response(response_data, accept)


def _handle_refresh_token(refresh_token: str | None, accept: str) -> Response:
    """Handle the refresh_token grant type.

    GitHub returns 200 with a URL-encoded error body for bad refresh tokens,
    which is the exact behavior that caused the production bug.
    """
    if not refresh_token or refresh_token == FAIL_REFRESH_TOKEN:
        return token_response(
            {
                "error": "bad_refresh_token",
                "error_description": "bad-verification-code",
            },
            accept,
        )

    token_data = decode_token(refresh_token)
    if not token_data or "email" not in token_data:
        return token_response(
            {
                "error": "bad_refresh_token",
                "error_description": "bad-verification-code",
            },
            accept,
        )

    email = token_data["email"]
    scope = token_data.get("scope") or DEFAULT_SCOPE
    if not isinstance(scope, str):
        scope = DEFAULT_SCOPE

    new_access_token = encode_token(email, scope)
    new_refresh_token = encode_token(email, scope)

    return token_response(
        {
            "access_token": new_access_token,
            "token_type": "bearer",
            "scope": scope,
            "refresh_token": new_refresh_token,
            "refresh_token_expires_in": 15897600,
        },
        accept,
    )


# Support both /api/user and /api/v3/user (GitHub Enterprise style)
@app.get("/api/user", response_model=GitHubUser)
@app.get("/api/v3/user", response_model=GitHubUser)
async def get_user(authorization: Annotated[str | None, Header()] = None):
    """Get authenticated user's profile."""
    token_data = extract_token_data_from_auth(authorization)
    email = token_data["email"]
    scopes = parse_scopes(token_data.get("scope"))
    profile_email = email if "user:email" in scopes else None

    return GitHubUser(
        id=generate_user_id(email),
        login=generate_login(email),
        name=generate_login(email).title(),
        email=profile_email,
        avatar_url=f"https://avatars.githubusercontent.com/u/{generate_user_id(email)}",
        html_url=f"https://github.com/{generate_login(email)}",
    )


@app.get("/api/user/emails", response_model=list[GitHubEmail])
@app.get("/api/v3/user/emails", response_model=list[GitHubEmail])
async def get_user_emails(authorization: Annotated[str | None, Header()] = None):
    """Get authenticated user's emails with verification status."""
    token_data = extract_token_data_from_auth(authorization)
    require_scope(token_data, "user:email")
    email = token_data["email"]

    return [
        GitHubEmail(
            email=email,
            primary=True,
            verified=is_email_verified(email),
        )
    ]


@app.get("/api/user/installations", response_model=GitHubInstallationsResponse)
@app.get("/api/v3/user/installations", response_model=GitHubInstallationsResponse)
async def get_user_installations(
    authorization: Annotated[str | None, Header()] = None,
):
    """Get GitHub App installations accessible to the authenticated user."""
    email = extract_email_from_auth(authorization)
    login = generate_login(email)
    return GitHubInstallationsResponse(installations=_build_installations(login))


@app.get(
    "/api/user/installations/{installation_id}/repositories",
    response_model=GitHubInstallationRepositoriesResponse,
)
@app.get(
    "/api/v3/user/installations/{installation_id}/repositories",
    response_model=GitHubInstallationRepositoriesResponse,
)
async def get_installation_repositories(
    installation_id: int,
    authorization: Annotated[str | None, Header()] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
):
    """Get repositories for a GitHub App installation."""
    email = extract_email_from_auth(authorization)
    login = generate_login(email)

    if installation_id == USER_INSTALLATION_ID:
        repositories = _build_user_repositories(login)
    elif installation_id == ORG_INSTALLATION_ID:
        repositories = ORG_REPOSITORIES
    else:
        raise HTTPException(status_code=404, detail="Installation not found")

    start = (page - 1) * per_page
    end = start + per_page

    return GitHubInstallationRepositoriesResponse(
        total_count=len(repositories),
        repositories=repositories[start:end],
    )


@app.get("/api/repositories/{repository_id}", response_model=GitHubRepository)
@app.get("/api/v3/repositories/{repository_id}", response_model=GitHubRepository)
async def get_repository_by_id(
    repository_id: int,
    authorization: Annotated[str | None, Header()] = None,
):
    """Get a repository by its global GitHub repository id."""
    email = extract_email_from_auth(authorization)
    login = generate_login(email)
    repository = _find_repository_by_id(login, repository_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="Not Found")
    return repository


@app.get("/api/repos/{owner}/{repo}/installation", response_model=GitHubInstallation)
@app.get(
    "/api/v3/repos/{owner}/{repo}/installation",
    response_model=GitHubInstallation,
)
async def get_repository_installation(
    owner: str,
    repo: str,
    authorization: Annotated[str | None, Header()] = None,
):
    """Get the GitHub App installation that covers a repository."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Requires authentication")

    if repo in _USER_REPO_NAMES:
        return GitHubInstallation(
            id=USER_INSTALLATION_ID,
            account=GitHubInstallationAccount(login=owner, type="User"),
        )

    if repo in ORG_REPO_NAMES and owner == ORG_LOGIN:
        return GitHubInstallation(
            id=ORG_INSTALLATION_ID,
            account=GitHubInstallationAccount(login=ORG_LOGIN, type="Organization"),
        )

    raise HTTPException(status_code=404, detail="Not Found")


@app.get("/api/repos/{owner}/{repo}", response_model=GitHubRepository)
@app.get("/api/v3/repos/{owner}/{repo}", response_model=GitHubRepository)
async def get_repository(
    owner: str,
    repo: str,
    authorization: Annotated[str | None, Header()] = None,
):
    """Get a repository by owner and name."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Requires authentication")

    if repo in _USER_REPO_NAMES:
        template = next(t for t in _USER_REPO_TEMPLATES if t["name"] == repo)
        return GitHubRepository(
            id=template["id"],
            name=repo,
            full_name=f"{owner}/{repo}",
            private=template["private"],
            owner=GitHubRepositoryOwner(login=owner),
        )

    if repo in ORG_REPO_NAMES and owner == ORG_LOGIN:
        return next(r for r in ORG_REPOSITORIES if r.name == repo)

    raise HTTPException(status_code=404, detail="Not Found")


@app.get("/api/repos/{owner}/{repo}/commits/{ref}", response_model=GitHubCommit)
@app.get("/api/v3/repos/{owner}/{repo}/commits/{ref}", response_model=GitHubCommit)
async def get_commit(
    owner: str,
    repo: str,
    ref: str,
    authorization: Annotated[str | None, Header()] = None,
):
    """Get a commit by ref (branch name or SHA)."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Requires authentication")

    all_known_repos = _USER_REPO_NAMES | ORG_REPO_NAMES
    if repo not in all_known_repos:
        raise HTTPException(status_code=404, detail="Not Found")

    return GitHubCommit(
        sha="abc123mock",
        commit=GitHubCommitData(message=f"Mock commit on {ref}"),
    )


# Additional endpoints that GitHub has (minimal implementations)


@app.get("/api/user/orgs")
@app.get("/api/v3/user/orgs")
async def get_user_orgs(authorization: Annotated[str | None, Header()] = None):
    """Get user's organizations (empty for mock)."""
    _ = extract_email_from_auth(authorization)  # Validate token
    return []


@app.get("/api/user/repos")
@app.get("/api/v3/user/repos")
async def get_user_repos(authorization: Annotated[str | None, Header()] = None):
    """Get user's repositories (empty for mock)."""
    _ = extract_email_from_auth(authorization)  # Validate token
    return []
