from urllib.parse import parse_qs, parse_qsl, urlparse

import pytest
from inline_snapshot import snapshot
from fastapi.testclient import TestClient

from oauth_mocks.github.app import app
from oauth_mocks.github.auth import FAIL_CLIENT_ID, FAIL_REFRESH_TOKEN


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def authorize(
    client: TestClient,
    *,
    client_id: str = "test-client",
    redirect_uri: str = "https://example.com/callback",
    email: str = "test@example.com",
    scope: str = "user:email",
    state: str = "state-123",
) -> str:
    response = client.post(
        "/login/oauth/authorize",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "email": email,
            "scope": scope,
            "state": state,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    return response.headers["location"]


def exchange(
    client: TestClient,
    code: str,
    *,
    client_id: str = "test-client",
    accept: str | None = None,
):
    headers = {}
    if accept:
        headers["accept"] = accept
    return client.post(
        "/login/oauth/access_token",
        data={"client_id": client_id, "code": code},
        headers=headers,
    )


def extract_code(location: str) -> str:
    query = parse_qs(urlparse(location).query)
    return query["code"][0]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_authorize_redirect_includes_code_and_state(client: TestClient) -> None:
    location = authorize(client)
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert query == snapshot(
        {
            "code": [
                "eyJlbWFpbCI6ICJ0ZXN0QGV4YW1wbGUuY29tIiwgInNjb3BlIjogInVzZXI6ZW1haWwifQ=="
            ],
            "state": ["state-123"],
        }
    )


def test_authorize_preserves_existing_query(client: TestClient) -> None:
    location = authorize(client, redirect_uri="https://example.com/callback?foo=bar")
    query = parse_qs(urlparse(location).query)
    assert query == snapshot(
        {
            "foo": ["bar"],
            "code": [
                "eyJlbWFpbCI6ICJ0ZXN0QGV4YW1wbGUuY29tIiwgInNjb3BlIjogInVzZXI6ZW1haWwifQ=="
            ],
            "state": ["state-123"],
        }
    )


def test_authorize_fail_client_redirects_error(client: TestClient) -> None:
    location = authorize(client, client_id=FAIL_CLIENT_ID)
    query = parse_qs(urlparse(location).query)
    assert query == snapshot(
        {
            "error": ["invalid_client"],
            "error_description": ["Client id is configured to fail in this mock"],
            "state": ["state-123"],
        }
    )


def test_token_json_response(client: TestClient) -> None:
    location = authorize(client, scope="user:email")
    code = extract_code(location)
    response = exchange(client, code, accept="application/json")
    assert response.status_code == 200
    payload = response.json()
    assert payload == snapshot(
        {
            "access_token": "eyJlbWFpbCI6ICJ0ZXN0QGV4YW1wbGUuY29tIiwgInNjb3BlIjogInVzZXI6ZW1haWwifQ==",
            "token_type": "bearer",
            "scope": "user:email",
            "refresh_token": "eyJlbWFpbCI6ICJ0ZXN0QGV4YW1wbGUuY29tIiwgInNjb3BlIjogInVzZXI6ZW1haWwifQ==",
            "refresh_token_expires_in": 15897600,
        }
    )


def test_token_form_response(client: TestClient) -> None:
    location = authorize(client, scope="user:email")
    code = extract_code(location)
    response = exchange(client, code)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/x-www-form-urlencoded"
    )
    payload = dict(parse_qsl(response.text))
    assert payload == snapshot(
        {
            "access_token": "eyJlbWFpbCI6ICJ0ZXN0QGV4YW1wbGUuY29tIiwgInNjb3BlIjogInVzZXI6ZW1haWwifQ==",
            "token_type": "bearer",
            "scope": "user:email",
            "refresh_token": "eyJlbWFpbCI6ICJ0ZXN0QGV4YW1wbGUuY29tIiwgInNjb3BlIjogInVzZXI6ZW1haWwifQ==",
            "refresh_token_expires_in": "15897600",
        }
    )


def test_token_error_fail_client_form(client: TestClient) -> None:
    response = exchange(client, "invalid-code", client_id=FAIL_CLIENT_ID)
    assert response.status_code == 400
    payload = dict(parse_qsl(response.text))
    assert payload == snapshot(
        {
            "error": "invalid_client",
            "error_description": "Client id is configured to fail in this mock",
        }
    )


def test_user_email_requires_scope(client: TestClient) -> None:
    location = authorize(client, scope="read:user")
    code = extract_code(location)
    token_response = exchange(client, code, accept="application/json")
    token = token_response.json()["access_token"]

    user_response = client.get("/api/user", headers=auth_header(token))
    assert user_response.status_code == 200
    assert user_response.json() == snapshot(
        {
            "id": 1431318336,
            "login": "test",
            "name": "Test",
            "email": None,
            "avatar_url": "https://avatars.githubusercontent.com/u/1431318336",
            "html_url": "https://github.com/test",
            "type": "User",
            "site_admin": False,
            "company": None,
            "blog": None,
            "location": None,
            "bio": None,
            "twitter_username": None,
            "public_repos": 0,
            "public_gists": 0,
            "followers": 0,
            "following": 0,
            "created_at": "2020-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
    )

    emails_response = client.get("/api/user/emails", headers=auth_header(token))
    assert emails_response.status_code == 403
    assert emails_response.json() == snapshot({"detail": "Requires user:email scope"})


def test_user_emails_with_scope(client: TestClient) -> None:
    location = authorize(client, scope="user:email")
    code = extract_code(location)
    token_response = exchange(client, code, accept="application/json")
    token = token_response.json()["access_token"]

    emails_response = client.get("/api/user/emails", headers=auth_header(token))
    assert emails_response.status_code == 200
    payload = emails_response.json()
    assert payload == snapshot(
        [
            {
                "email": "test@example.com",
                "primary": True,
                "verified": True,
                "visibility": "private",
            }
        ]
    )


def test_user_installations(client: TestClient) -> None:
    location = authorize(client, scope="user:email")
    code = extract_code(location)
    token_response = exchange(client, code, accept="application/json")
    token = token_response.json()["access_token"]

    response = client.get("/api/user/installations", headers=auth_header(token))

    assert response.status_code == 200
    assert response.json() == snapshot(
        {
            "installations": [
                {
                    "id": 1001,
                    "account": {"login": "test", "type": "User"},
                },
                {
                    "id": 2002,
                    "account": {"login": "mock-org", "type": "Organization"},
                },
            ]
        }
    )


def test_installation_repositories_paginate(client: TestClient) -> None:
    location = authorize(client, scope="user:email")
    code = extract_code(location)
    token_response = exchange(client, code, accept="application/json")
    token = token_response.json()["access_token"]

    response = client.get(
        "/api/user/installations/1001/repositories",
        params={"page": 2, "per_page": 1},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json() == snapshot(
        {
            "total_count": 2,
            "repositories": [
                {
                    "id": 102,
                    "name": "playwright-repo",
                    "full_name": "test/playwright-repo",
                    "private": False,
                    "owner": {"login": "test"},
                    "default_branch": "main",
                    "updated_at": "2024-01-01T00:00:00Z",
                }
            ],
        }
    )


def test_repository_by_id_user_repo(client: TestClient) -> None:
    location = authorize(client, scope="user:email")
    code = extract_code(location)
    token_response = exchange(client, code, accept="application/json")
    token = token_response.json()["access_token"]

    response = client.get("/api/repositories/101", headers=auth_header(token))

    assert response.status_code == 200
    assert response.json() == snapshot(
        {
            "id": 101,
            "name": "demo-repo",
            "full_name": "test/demo-repo",
            "private": True,
            "owner": {"login": "test"},
            "default_branch": "main",
            "updated_at": "2024-01-01T00:00:00Z",
        }
    )


def test_repository_by_id_org_repo(client: TestClient) -> None:
    location = authorize(client, scope="user:email")
    code = extract_code(location)
    token_response = exchange(client, code, accept="application/json")
    token = token_response.json()["access_token"]

    response = client.get("/api/repositories/201", headers=auth_header(token))

    assert response.status_code == 200
    assert response.json() == snapshot(
        {
            "id": 201,
            "name": "org-repo",
            "full_name": "mock-org/org-repo",
            "private": True,
            "owner": {"login": "mock-org"},
            "default_branch": "main",
            "updated_at": "2024-01-01T00:00:00Z",
        }
    )


def test_repository_by_id_unknown_repo(client: TestClient) -> None:
    location = authorize(client, scope="user:email")
    code = extract_code(location)
    token_response = exchange(client, code, accept="application/json")
    token = token_response.json()["access_token"]

    response = client.get("/api/repositories/999", headers=auth_header(token))

    assert response.status_code == 404
    assert response.json() == snapshot({"detail": "Not Found"})


def test_repository_installation_lookup(client: TestClient) -> None:
    response = client.get(
        "/api/repos/some-user/demo-repo/installation",
        headers={"Authorization": "Bearer app-jwt"},
    )

    assert response.status_code == 200
    assert response.json() == snapshot(
        {
            "id": 1001,
            "account": {"login": "some-user", "type": "User"},
        }
    )


def test_repository_installation_lookup_unknown_repo(client: TestClient) -> None:
    response = client.get(
        "/api/repos/some-user/missing-repo/installation",
        headers={"Authorization": "Bearer app-jwt"},
    )

    assert response.status_code == 404
    assert response.json() == snapshot({"detail": "Not Found"})


def test_refresh_token_success_json(client: TestClient) -> None:
    """Valid refresh token returns new tokens as JSON."""
    location = authorize(client, scope="user:email")
    code = extract_code(location)
    token_resp = exchange(client, code, accept="application/json")
    refresh_token = token_resp.json()["refresh_token"]

    response = client.post(
        "/login/oauth/access_token",
        data={
            "client_id": "test-client",
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        headers={"accept": "application/json"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "access_token" in payload
    assert "refresh_token" in payload
    assert payload["token_type"] == "bearer"
    assert payload["scope"] == "user:email"


def test_refresh_token_success_form(client: TestClient) -> None:
    """Valid refresh token returns new tokens as form-urlencoded."""
    location = authorize(client, scope="user:email")
    code = extract_code(location)
    token_resp = exchange(client, code, accept="application/json")
    refresh_token = token_resp.json()["refresh_token"]

    response = client.post(
        "/login/oauth/access_token",
        data={
            "client_id": "test-client",
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/x-www-form-urlencoded"
    )
    payload = dict(parse_qsl(response.text))
    assert "access_token" in payload
    assert "refresh_token" in payload


def test_refresh_token_bad_token_form(client: TestClient) -> None:
    """Bad refresh token returns 200 with URL-encoded error (GitHub's real behavior)."""
    response = client.post(
        "/login/oauth/access_token",
        data={
            "client_id": "test-client",
            "grant_type": "refresh_token",
            "refresh_token": FAIL_REFRESH_TOKEN,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/x-www-form-urlencoded"
    )
    payload = dict(parse_qsl(response.text))
    assert payload == snapshot(
        {
            "error": "bad_refresh_token",
            "error_description": "bad-verification-code",
        }
    )


def test_refresh_token_bad_token_json(client: TestClient) -> None:
    """Bad refresh token returns 200 with JSON error when Accept: application/json."""
    response = client.post(
        "/login/oauth/access_token",
        data={
            "client_id": "test-client",
            "grant_type": "refresh_token",
            "refresh_token": FAIL_REFRESH_TOKEN,
        },
        headers={"accept": "application/json"},
    )

    assert response.status_code == 200
    assert response.json() == snapshot(
        {
            "error": "bad_refresh_token",
            "error_description": "bad-verification-code",
        }
    )


def test_refresh_token_missing_token(client: TestClient) -> None:
    """Missing refresh token returns error."""
    response = client.post(
        "/login/oauth/access_token",
        data={
            "client_id": "test-client",
            "grant_type": "refresh_token",
        },
    )

    assert response.status_code == 200
    payload = dict(parse_qsl(response.text))
    assert payload["error"] == "bad_refresh_token"
