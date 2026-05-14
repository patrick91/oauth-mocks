# Google OAuth Mock

A stateless mock implementation of Google's OAuth 2.0 and OpenID Connect
endpoints for testing.

It intentionally signs `id_token` values with RS256 and exposes the matching
public key at `/oauth2/v3/certs`, so applications can exercise their normal
Google OIDC validation path.

## Email Verification Rules

| Email Pattern | `email_verified` |
| --- | --- |
| `unverified@*` | `false` |
| Any other email | `true` |

## Quick Start

```bash
uv run uvicorn google_oauth_mock.app:app --app-dir google --reload --port 9002
```

## Endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/.well-known/openid-configuration` | GET | OIDC discovery metadata |
| `/o/oauth2/v2/auth` | GET | Shows sign-in form |
| `/o/oauth2/v2/auth` | POST | Processes sign-in and redirects with code |
| `/token` | POST | Token exchange |
| `/oauth2/token` | POST | Alias for token exchange |
| `/oauth2/v3/certs` | GET | JWKS |
| `/oauth2/v2/userinfo` | GET | User profile |
| `/userinfo` | GET | Alias for user profile |

## FastAPI Cloud Settings

For a deployed mock, set:

```bash
BACKEND_GOOGLE_CLIENT_ID=test-google-client-id
BACKEND_GOOGLE_CLIENT_SECRET=test-google-client-secret
BACKEND_GOOGLE_AUTHORIZATION_ENDPOINT=https://google-oauth-mock.example.com/o/oauth2/v2/auth
BACKEND_GOOGLE_TOKEN_ENDPOINT=https://google-oauth-mock.example.com/token
BACKEND_GOOGLE_JWKS_URI=https://google-oauth-mock.example.com/oauth2/v3/certs
```

No custom `BACKEND_GOOGLE_USER_INFO_ENDPOINT` override should be needed because
the mock emits normal RS256 ID tokens.
