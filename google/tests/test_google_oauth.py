from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from google_oauth_mock.app import app
from google_oauth_mock.auth import FAIL_CLIENT_ID, ISSUER


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def authorize(
    client: TestClient,
    *,
    client_id: str = "test-google-client-id",
    redirect_uri: str = "https://example.com/callback",
    email: str = "test@example.com",
    scope: str = "openid email profile",
    state: str = "state-123",
    nonce: str = "nonce-123",
) -> str:
    response = client.post(
        "/o/oauth2/v2/auth",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "email": email,
            "scope": scope,
            "state": state,
            "nonce": nonce,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    return response.headers["location"]


def exchange(
    client: TestClient,
    code: str,
    *,
    client_id: str = "test-google-client-id",
):
    return client.post(
        "/token",
        data={
            "client_id": client_id,
            "client_secret": "test-google-client-secret",
            "code": code,
            "redirect_uri": "https://example.com/callback",
            "grant_type": "authorization_code",
        },
    )


def extract_code(location: str) -> str:
    query = parse_qs(urlparse(location).query)
    return query["code"][0]


def test_authorize_redirect_includes_code_and_state(client: TestClient) -> None:
    location = authorize(client)
    query = parse_qs(urlparse(location).query)

    assert "code" in query
    assert query["state"] == ["state-123"]


def test_authorize_fail_client_redirects_error(client: TestClient) -> None:
    location = authorize(client, client_id=FAIL_CLIENT_ID)
    query = parse_qs(urlparse(location).query)

    assert query == {
        "error": ["invalid_client"],
        "error_description": ["Client id is configured to fail in this mock"],
        "state": ["state-123"],
    }


def test_token_response_includes_valid_rs256_id_token(client: TestClient) -> None:
    location = authorize(client, email="verified@example.com")
    response = exchange(client, extract_code(location))

    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"]
    assert payload["token_type"] == "Bearer"
    assert payload["scope"] == "openid email profile"
    assert payload["expires_in"] == 3600

    header = jwt.get_unverified_header(payload["id_token"])
    assert header["alg"] == "RS256"
    assert header["kid"] == "google-oauth-mock-key-1"

    jwks = client.get("/oauth2/v3/certs").json()
    public_key = RSAAlgorithm.from_jwk(jwks["keys"][0])
    claims = jwt.decode(
        payload["id_token"],
        public_key,
        algorithms=["RS256"],
        audience="test-google-client-id",
        issuer=ISSUER,
    )

    assert claims["sub"].startswith("google-")
    assert claims["email"] == "verified@example.com"
    assert claims["email_verified"] is True
    assert claims["name"] == "Verified"
    assert claims["nonce"] == "nonce-123"


def test_token_response_marks_unverified_email(client: TestClient) -> None:
    location = authorize(client, email="unverified@example.com")
    response = exchange(client, extract_code(location))
    jwks = client.get("/oauth2/v3/certs").json()
    public_key = RSAAlgorithm.from_jwk(jwks["keys"][0])

    claims = jwt.decode(
        response.json()["id_token"],
        public_key,
        algorithms=["RS256"],
        audience="test-google-client-id",
        issuer=ISSUER,
    )

    assert claims["email"] == "unverified@example.com"
    assert claims["email_verified"] is False


def test_userinfo_returns_profile_from_access_token(client: TestClient) -> None:
    location = authorize(client, email="user.name@example.com")
    token_response = exchange(client, extract_code(location))
    access_token = token_response.json()["access_token"]

    response = client.get(
        "/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "sub": response.json()["sub"],
        "email": "user.name@example.com",
        "email_verified": True,
        "name": "User Name",
        "given_name": "User",
        "picture": response.json()["picture"],
    }


def test_openid_configuration_points_to_mock_endpoints(client: TestClient) -> None:
    response = client.get("/.well-known/openid-configuration")

    assert response.status_code == 200
    payload = response.json()
    assert payload["issuer"] == ISSUER
    assert payload["authorization_endpoint"].endswith("/o/oauth2/v2/auth")
    assert payload["token_endpoint"].endswith("/token")
    assert payload["jwks_uri"].endswith("/oauth2/v3/certs")
    assert payload["id_token_signing_alg_values_supported"] == ["RS256"]
