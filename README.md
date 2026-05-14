# OAuth Mocks

A uv workspace for OAuth provider mocks used by FastAPI Cloud tests.

## Packages

| Package | Description |
| --- | --- |
| `github-oauth-mock` | GitHub OAuth and selected GitHub API endpoints. |
| `google-oauth-mock` | Google OAuth 2.0 / OIDC endpoints with RS256 ID tokens and JWKS. |

## Setup

```bash
uv sync --all-packages
```

## Run Tests

```bash
uv run pytest
```

## Run Locally

```bash
uv run uvicorn github_oauth_mock.app:app --app-dir github --reload --port 9001
uv run uvicorn google_oauth_mock.app:app --app-dir google --reload --port 9002
```

## Provider Endpoints

GitHub:

| Endpoint | Description |
| --- | --- |
| `/login/oauth/authorize` | OAuth authorization form and submit endpoint. |
| `/login/oauth/access_token` | OAuth token exchange. |
| `/api/user` | Authenticated user profile. |
| `/api/user/emails` | Authenticated user emails. |

Google:

| Endpoint | Description |
| --- | --- |
| `/.well-known/openid-configuration` | OIDC discovery metadata. |
| `/o/oauth2/v2/auth` | OAuth authorization form and submit endpoint. |
| `/token` | OAuth token exchange. |
| `/oauth2/v3/certs` | JWKS for ID token verification. |
| `/oauth2/v2/userinfo` | Authenticated user profile. |

Email verification follows the same convention in both mocks:

| Email Pattern | Verified |
| --- | --- |
| `unverified@*` | `false` |
| Any other email | `true` |
