"""Phase 2/6 — PKCE S256 round-trip (Python-only)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack.auth.pkce import (
    generate_code_challenge,
    generate_code_verifier,
    generate_pkce_params,
    is_valid_code_verifier,
    validate_pkce_support,
    verify_pkce,
)


def test_s256_round_trip_and_mismatch():
    verifier = generate_code_verifier()
    assert is_valid_code_verifier(verifier)
    challenge = generate_code_challenge(verifier, "S256")
    assert verify_pkce(verifier, challenge, "S256") is True
    other = generate_code_verifier()
    assert verify_pkce(other, challenge, "S256") is False


def test_plain_method_and_params():
    params = generate_pkce_params("plain")
    assert params["code_challenge_method"] == "plain"
    assert params["code_challenge"] == params["code_verifier"]
    assert verify_pkce(params["code_verifier"], params["code_challenge"], "plain")


def test_verifier_length_and_charset():
    assert is_valid_code_verifier("a" * 42) is False
    assert is_valid_code_verifier("a" * 129) is False
    assert is_valid_code_verifier("a" * 43) is True
    assert is_valid_code_verifier("bad verifier!") is False


def test_pkce_support_requires_s256():
    assert validate_pkce_support([]) is False
    assert validate_pkce_support(["plain"]) is False
    assert validate_pkce_support(["plain", "S256"]) is True
