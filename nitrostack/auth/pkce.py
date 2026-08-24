"""
PKCE (Proof Key for Code Exchange) utilities — RFC 7636.

PKCE defends the OAuth "authorization code" flow against code-interception attacks:
a client generates a secret `code_verifier` it never discloses, derives a one-way
`code_challenge` from it, and sends only the challenge when starting the flow. When
later exchanging the authorization code for a token, it presents the original
verifier; the authorization server re-derives the challenge and checks it matches.
An attacker who only intercepted the authorization code (never the verifier) cannot
complete the exchange. OAuth 2.1 requires PKCE for all public clients.

nitrostack is an OAuth *resource server* (it validates incoming Bearer tokens), never
an *authorization server* (it never issues codes or tokens itself) — so these are
provided as standalone, directly-portable utilities, not wired into a local
code-exchange endpoint that doesn't exist in this SDK or its TypeScript counterpart.
"""
from __future__ import annotations

import base64
import hashlib
import re
import secrets
from typing import Dict, List, Optional

_VERIFIER_CHARSET_RE = re.compile(r"^[A-Za-z0-9\-._~]+$")


def _b64url_encode(data: bytes) -> str:
    """Base64url without padding — the encoding RFC 7636 requires for both the
    verifier and the challenge."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_code_verifier() -> str:
    """
    Generate a cryptographically random code verifier.

    Per RFC 7636: a high-entropy random string, 43-128 characters, from the
    unreserved URI character set. `secrets` (not `random`) is used because this
    value must be unguessable — `random` is a statistical PRNG, not a
    cryptographic one.
    """
    # 32 random bytes -> 256 bits of entropy -> 43 base64url characters.
    return _b64url_encode(secrets.token_bytes(32))


def generate_code_challenge(verifier: str, method: str = "S256") -> str:
    """
    Derive a code challenge from a code verifier.

    method="S256" (default, the only method OAuth 2.1 requires support for):
        code_challenge = BASE64URL(SHA256(verifier))
    method="plain":
        code_challenge = verifier, unchanged. NOT RECOMMENDED — offers no
        protection beyond what a plain authorization code already has, since the
        "challenge" sent up front is now just the verifier itself. Only exists
        for constrained clients that can't compute SHA-256.
    """
    if method == "plain":
        return verifier
    if method == "S256":
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        return _b64url_encode(digest)
    raise ValueError(f"Unsupported PKCE method: {method!r} (expected 'S256' or 'plain')")


def generate_pkce_params(method: str = "S256") -> Dict[str, str]:
    """Generate a complete verifier/challenge pair for starting an authorization flow."""
    verifier = generate_code_verifier()
    challenge = generate_code_challenge(verifier, method)
    return {
        "code_verifier": verifier,
        "code_challenge": challenge,
        "code_challenge_method": method,
    }


def verify_pkce(verifier: str, challenge: str, method: str = "S256") -> bool:
    """
    Verify that a code verifier matches a previously-issued code challenge.

    Plain string equality is used deliberately, not a constant-time comparison
    like `hmac.compare_digest`. `code_challenge` is not a secret — it travels in
    the (public) authorization request URL — so there is no secret value being
    defended against a timing side-channel here, unlike e.g. an HMAC signature
    check. This intentionally matches the TypeScript SDK's `verifyPKCE`.
    """
    return generate_code_challenge(verifier, method) == challenge


def is_valid_code_verifier(verifier: str) -> bool:
    """
    Check that a string is a well-formed RFC 7636 code verifier: 43-128
    characters from [A-Za-z0-9\\-._~].
    """
    if not (43 <= len(verifier) <= 128):
        return False
    return bool(_VERIFIER_CHARSET_RE.match(verifier))


def validate_pkce_support(supported_methods: Optional[List[str]]) -> bool:
    """
    Check whether an authorization server's advertised `code_challenge_methods_supported`
    satisfies OAuth 2.1: S256 support is required. An authorization server that
    doesn't advertise S256 (or advertises nothing) must be treated as not usable.
    """
    if not supported_methods:
        return False
    return "S256" in supported_methods
