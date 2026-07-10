# OAuth Mocks

Local GitHub and Google OAuth provider mocks for development, end-to-end tests,
CI, and no-network environments.

The mocks are stateless: authorization codes and access tokens carry the test
identity, so no database or shared service is required.

## Quick Start

Run both providers without installing anything permanently:

```bash
uvx oauth-mocks
```

This starts:

- GitHub at <http://127.0.0.1:9001>
- Google at <http://127.0.0.1:9002>

Install the command for regular use:

```bash
uv tool install oauth-mocks
oauth-mocks
```

`oauth-mocks start` is an equivalent explicit form.

## CLI

Start only one provider:

```bash
oauth-mocks --provider github
oauth-mocks --provider google --port 9002
```

Choose the base port or bind address:

```bash
oauth-mocks --port 9100
oauth-mocks --host 0.0.0.0
```

Selected providers receive consecutive ports beginning at `--port`, in the
order supplied to `--provider`. Run `oauth-mocks --help` for all options.

## Run from a Source Checkout

Install the locked development environment and run both mocks:

```bash
uv sync
uv run oauth-mocks
```

Each FastAPI app can also be run independently from its provider folder with
auto-reload:

```bash
cd github
uv run fastapi dev --reload-dir ../src --port 9001
```

```bash
cd google
uv run fastapi dev --reload-dir ../src --port 9002
```

## Provider Endpoints

GitHub:

| Endpoint | Description |
| --- | --- |
| `/login/oauth/authorize` | OAuth authorization form and submit endpoint |
| `/login/oauth/access_token` | OAuth token exchange |
| `/api/user` | Authenticated user profile |
| `/api/user/emails` | Authenticated user emails |
| `/api/user/installations` | GitHub App installations |

Google:

| Endpoint | Description |
| --- | --- |
| `/.well-known/openid-configuration` | OIDC discovery metadata |
| `/o/oauth2/v2/auth` | OAuth authorization form and submit endpoint |
| `/token` | OAuth token exchange |
| `/oauth2/v3/certs` | JWKS for ID token verification |
| `/oauth2/v2/userinfo` | Authenticated user profile |

Google ID tokens are signed with RS256, and the matching public key is exposed
through the JWKS endpoint so applications can exercise their normal OIDC
validation path.

## Test Conventions

Email verification follows the same convention in both mocks:

| Email pattern | Verified |
| --- | --- |
| `unverified@*` | `false` |
| Any other email | `true` |

Using the client ID `fail-client-id` makes authorization and token exchange
fail intentionally.

## Development

```bash
uv run pytest
uv build
```

Releases use `RELEASE.md` and AutoPub.

## License

MIT
