"""Token and OpenID Connect helpers for the Google mock."""

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import jwt
from cryptography.hazmat.primitives import serialization
from jwt.algorithms import RSAAlgorithm

DEFAULT_SCOPE = "openid email profile"
FAIL_CLIENT_ID = "fail-client-id"
ISSUER = "https://accounts.google.com"
KEY_ID = "google-oauth-mock-key-1"

PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCeMduFI4I9hmVe
SM1ElLmMA0sqb373dLW24UAZSuTNJkntpYRTOTtE8m0H5aSoOhN5t8CswC3GSKVl
rgnh80xEJD+FI0bzwpLV8K7E+Sqp7U1bmqmISkclyXc+lFucEMXoB/h8fx1WuIbl
4DonSqllo8Eveg3ZppZxkOTPDDJUrrdQV+lFX9Gi9qpo8vSlMtP+mK5GDHmqCYjS
Q39ZehY+WMXjOmjvnELJtlKUL8gIJB31Bs8Sh+WTO2AFJZBLkiiRwTZ7ATlHgOvW
WcTxBd/1GaaTZFYkXfbfaWuW+mx4SwZinVyj8HLrWCvocna2r8xEn/0GTqbNicVa
Iq0MOjtFAgMBAAECggEAE3zt35lvvneTfkl2rBesQfDX7irdF8vzZMub82G0DQfF
/LYytnPq9sPspZfnMGgzJP/7huyH1xD0+zE0+3ZW82AJyTN+1qGmKB/lz9MoK9XV
fU7wyp7n4+JNQ9LP9Epmrv5oYKHiMeA6khAM6fE7LA+/yUL+eM0aZHQmk9EbVC4e
RTzVse9JjnjsZS7JVhaG6HKiC09B4Rze0T/6JuYIhwPM2Bt+RCNUfbWk9dUdLSbd
eA0/pbCNu/T9MWggQycLMoEKfFELbE9kn4AyxD62MI+xqRZy0rJbEhrMBoat7cq3
PTex5vevrTo04xjNEOlN0Jsmd49xfxy3xBFOu7tw4wKBgQDMlnt2CPofDFs4R1f1
9sQF7TnRag0xpYy7fe8kHwcIX5Bfs0BmwvVbFI16wAEMkYFR5SDVeYcsgTYxYyhI
5+UTXR5Gf7R1AcZv4qi4vL63lyzABq5jqDxqyg/mibV9NehRfprBSwlNldIxZFZw
tW8B7gGYM/hlWNtUS2N6vSeh9wKBgQDF8tKLFpHB0OuLz9rO1kNlWcq4VTGtH/B2
MK376n15C0aKbvB322U7exCgzJYB1RhCEY5fmz9t44c7BLA4rv2IUovKWRPLYTW4
2g+QEQjSDBbH3NG6Eg9SdEIJC3ijFIOuwdSP4SLtj65G1EdlUH9H8HRYhyB1ygjM
o5nVizv9owKBgQCYkH9w/jDHhodf6JQHsAVuBgHf0J4WL8ZK6xaycRDlhZ48P4f/
GdOuIB2BND2UCc3OLHfXudC7t3+aRL993rBNSFuTZxhDSReZyATZ/qaacfnFGTZi
ysqDODuzR243+UNNwoPVMQe2+8rLWm+7jRFC9yHpRpgtu52TtsRwey5a8QKBgQCy
/5xyV+tgR0rouAHWLhztxl+xhqCQPCSWy/hYqDfkQFT+k8lxqPyG6AcmUTqI16jC
/dswC1Q1S52aueecqmjrYDG2vgxPSk1pJg8SqMTAJFxpSP6B8xjV5/la8nuZhNB7
NB3CKcUK63Wd6RHSxRMD+6VJ9I9e1F5Wps5SM0EBXwKBgEiTjo8h/W237aw0nelo
9aOV2kZcL3Js06sFWlgg9Cbf6fSU8NUCX+RBHZJXiscV1WuzJcPlqQYrYEn1kmWA
q6fJ+kPyLjYqf4E4hfiTElGbF2gIhmdtAxtCLhL+N9K8OOpXlfij4S82VYmz3b6q
7vQobCMRc3cxVvKYXwf+Gb7v
-----END PRIVATE KEY-----"""


def encode_token(payload: dict[str, str]) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_token(token: str) -> dict[str, str] | None:
    try:
        padded = token + "=" * (-len(token) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode())
        if not isinstance(data, dict):
            return None
        return {str(key): str(value) for key, value in data.items()}
    except Exception:
        return None


def is_email_verified(email: str) -> bool:
    return not email.lower().startswith("unverified")


def generate_subject(email: str) -> str:
    digest = hashlib.sha256(email.encode()).hexdigest()[:24]
    return f"google-{digest}"


def generate_name(email: str) -> str:
    local_part = email.split("@", 1)[0]
    return local_part.replace(".", " ").replace("+", " ").title()


def build_redirect_url(redirect_uri: str, params: dict[str, str]) -> str:
    parsed = urlparse(redirect_uri)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(params)
    return urlunparse(parsed._replace(query=urlencode(query)))


def public_jwk() -> dict[str, object]:
    private_key = serialization.load_pem_private_key(
        PRIVATE_KEY.encode(),
        password=None,
    )
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = KEY_ID
    jwk["alg"] = "RS256"
    jwk["use"] = "sig"
    return jwk


def create_id_token(
    *,
    email: str,
    client_id: str,
    nonce: str | None = None,
) -> str:
    now = datetime.now(tz=UTC)
    name = generate_name(email)
    payload = {
        "iss": ISSUER,
        "aud": client_id,
        "sub": generate_subject(email),
        "email": email,
        "email_verified": is_email_verified(email),
        "name": name,
        "given_name": name.split(" ", 1)[0],
        "picture": f"https://lh3.googleusercontent.com/a/mock-{generate_subject(email)}",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    if nonce:
        payload["nonce"] = nonce

    return jwt.encode(
        payload,
        PRIVATE_KEY,
        algorithm="RS256",
        headers={"kid": KEY_ID},
    )
