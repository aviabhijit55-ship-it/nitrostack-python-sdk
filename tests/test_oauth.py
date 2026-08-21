import asyncio
import os
import sys
import time
from unittest.mock import MagicMock, patch

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack import DIContainer, ExecutionContext, OAuthGuard
from nitrostack.auth.oauth import OAuthModule, OAuthService
from nitrostack.auth.oauth_module import (
    build_authorization_server_metadata,
    build_protected_resource_metadata,
    build_registration_response,
    is_client_registration_enabled,
)
from nitrostack.auth.pkce import (
    generate_code_challenge,
    generate_code_verifier,
    generate_pkce_params,
    is_valid_code_verifier,
    validate_pkce_support,
    verify_pkce,
)


async def _test_oauth_guard_validation():
    print("Testing OAuthGuard and OAuth 2.1 validation flow...")

    # 1. Setup DIContainer and OAuthModule
    DIContainer.reset()
    OAuthModule.for_root(
        resource_uri="http://localhost:8000/mcp",
        authorization_servers=["http://localhost:3000/oauth"],
        scopes_supported=["flight:read", "flight:write"],
        token_introspection_endpoint="http://localhost:3000/oauth/introspect"
    )

    guard = OAuthGuard()

    # Case A: Missing Authorization Header — Studio default (OAUTH_REQUIRED unset)
    os.environ.pop("OAUTH_REQUIRED", None)
    ctx_missing = ExecutionContext(
        request_id="test-req-1",
        tool_name="test-tool",
        logger=MagicMock(),
        metadata={}
    )
    res_missing = await guard.can_activate(ctx_missing)
    print("Missing authorization header (auth optional):", res_missing)
    assert res_missing is True

    os.environ["OAUTH_REQUIRED"] = "true"
    try:
        ctx_required = ExecutionContext(
            request_id="test-req-1b",
            tool_name="test-tool",
            logger=MagicMock(),
            metadata={}
        )
        try:
            await guard.can_activate(ctx_required)
            raise AssertionError("OAUTH_REQUIRED=true must reject a missing token")
        except PermissionError as exc:
            assert "OAuth token required" in str(exc)
    finally:
        os.environ.pop("OAUTH_REQUIRED", None)

    # Case B: Malformed Authorization Header (no Bearer prefix)
    ctx_malformed = ExecutionContext(
        request_id="test-req-2",
        tool_name="test-tool",
        logger=MagicMock(),
        metadata={"authorization": "Basic abcdef"}
    )
    res_malformed = await guard.can_activate(ctx_malformed)
    print("Malformed authorization header check (auth optional):", res_malformed)
    assert res_malformed is True

    # Case C: Valid Bearer Token but Introspection returns active = False
    ctx_invalid = ExecutionContext(
        request_id="test-req-3",
        tool_name="test-tool",
        logger=MagicMock(),
        metadata={"authorization": "Bearer invalid-token"}
    )

    # Mock introspect_token to return inactive
    oauth_service = DIContainer.get_instance().resolve(OAuthService)

    with patch.object(oauth_service, 'introspect_token', return_value={"active": False}) as mock_introspect:
        res_invalid = await guard.can_activate(ctx_invalid)
        print("Invalid token check (auth optional):", res_invalid)
        assert res_invalid is True
        mock_introspect.assert_called_once_with("invalid-token")

    os.environ["OAUTH_REQUIRED"] = "true"
    try:
        with patch.object(oauth_service, "introspect_token", return_value={"active": False}):
            res_invalid_required = await guard.can_activate(ctx_invalid)
            assert res_invalid_required is False
    finally:
        os.environ.pop("OAUTH_REQUIRED", None)

    # Case D: Valid Bearer Token and Introspection returns active = True with scopes
    ctx_valid = ExecutionContext(
        request_id="test-req-4",
        tool_name="test-tool",
        logger=MagicMock(),
        metadata={"authorization": "Bearer valid-token"}
    )

    introspection_payload = {
        "active": True,
        "scope": "flight:read flight:write",
        "sub": "user_12345",
        "client_id": "client_abc",
        "aud": "http://localhost:8000/mcp",
        "exp": 1900000000
    }

    with patch.object(oauth_service, 'introspect_token', return_value=introspection_payload) as mock_introspect:
        res_valid = await guard.can_activate(ctx_valid)
        print("Valid token check:", res_valid)
        assert res_valid is True
        mock_introspect.assert_called_once_with("valid-token")

        # Verify AuthContext properties populated on the context
        assert ctx_valid.auth is not None
        assert ctx_valid.auth.subject == "user_12345"
        assert "flight:read" in ctx_valid.auth.scopes
        assert "flight:write" in ctx_valid.auth.scopes
        assert ctx_valid.auth.client_id == "client_abc"
        # A string `aud` claim must come out normalized to a list, not left as a
        # bare string (which would give substring-match semantics downstream).
        assert ctx_valid.auth.aud == ["http://localhost:8000/mcp"]

    print("Success! OAuthGuard and OAuth 2.1 token validations work perfectly.")


def test_oauth_guard_validation():
    asyncio.run(_test_oauth_guard_validation())


# ---------------------------------------------------------------------------
# PKCE (RFC 7636)
# ---------------------------------------------------------------------------

def test_pkce_round_trip():
    print("Testing PKCE verifier/challenge round-trip (S256)...")
    params = generate_pkce_params()
    assert params["code_challenge_method"] == "S256"
    assert is_valid_code_verifier(params["code_verifier"])
    assert verify_pkce(params["code_verifier"], params["code_challenge"]) is True
    print("Success! S256 verifier/challenge round-trip matches.")


def test_pkce_rejects_mismatched_verifier():
    print("Testing PKCE rejects a verifier that doesn't match the challenge...")
    params = generate_pkce_params()
    other_verifier = generate_code_verifier()
    assert other_verifier != params["code_verifier"]
    assert verify_pkce(other_verifier, params["code_challenge"]) is False
    print("Success! Mismatched verifier is rejected.")


def test_pkce_plain_method():
    print("Testing PKCE 'plain' method (challenge == verifier, unhashed)...")
    verifier = generate_code_verifier()
    challenge = generate_code_challenge(verifier, method="plain")
    assert challenge == verifier
    assert verify_pkce(verifier, challenge, method="plain") is True
    print("Success! 'plain' method behaves as challenge == verifier.")


def test_pkce_unknown_method_raises():
    print("Testing PKCE raises on an unsupported challenge method...")
    try:
        generate_code_challenge("x" * 43, method="bogus")
        raise AssertionError("expected ValueError for an unknown PKCE method")
    except ValueError:
        pass
    print("Success! Unknown method raises ValueError.")


def test_pkce_verifier_format_boundaries():
    print("Testing PKCE code_verifier format boundaries (RFC 7636: 43-128 chars)...")
    assert is_valid_code_verifier("a" * 42) is False  # too short
    assert is_valid_code_verifier("a" * 43) is True   # minimum length
    assert is_valid_code_verifier("a" * 128) is True  # maximum length
    assert is_valid_code_verifier("a" * 129) is False  # too long
    assert is_valid_code_verifier("a" * 43 + "!") is False  # invalid charset ('!' not allowed)
    print("Success! Verifier length/charset boundaries enforced correctly.")


def test_pkce_support_requires_s256():
    print("Testing validate_pkce_support requires S256 (OAuth 2.1 mandate)...")
    assert validate_pkce_support(["S256"]) is True
    assert validate_pkce_support(["S256", "plain"]) is True
    assert validate_pkce_support(["plain"]) is False
    assert validate_pkce_support([]) is False
    assert validate_pkce_support(None) is False
    print("Success! S256 support is correctly required.")


# ---------------------------------------------------------------------------
# Audience / resource-indicator validation (RFC 8707)
# ---------------------------------------------------------------------------

async def _test_audience_validation_endpoint_path():
    print("Testing RFC 8707 audience validation on the introspection-endpoint path...")
    service = OAuthService(
        resource_uri="https://api.example.com",
        authorization_servers=["https://idp.example.com"],
        scopes_supported=["read"],
        token_introspection_endpoint="https://idp.example.com/introspect",
    )

    with patch.object(
        service, "_introspect_via_endpoint",
        return_value={"active": True, "aud": "https://other-service.example.com", "scope": "read"},
    ):
        result = await service.introspect_token("wrong-audience-token")
        print("Wrong-audience token result:", result)
        assert result == {"active": False}

    with patch.object(
        service, "_introspect_via_endpoint",
        return_value={"active": True, "aud": "https://api.example.com", "scope": "read", "sub": "u1"},
    ):
        result = await service.introspect_token("correct-audience-token")
        assert result["active"] is True

    print("Success! Audience mismatch rejected, audience match accepted (endpoint path).")


def test_audience_validation_endpoint_path():
    asyncio.run(_test_audience_validation_endpoint_path())


def test_audience_validation_list_form():
    print("Testing RFC 8707 audience validation when `aud` is a list, not a string...")
    service = OAuthService(
        resource_uri="https://api.example.com",
        authorization_servers=["https://idp.example.com"],
        scopes_supported=["read"],
    )
    assert service._validate_audience({"aud": ["https://api.example.com", "https://other.example.com"]}) is True
    assert service._validate_audience({"aud": ["https://other.example.com"]}) is False
    assert service._validate_audience({}) is True  # no aud claim at all -> permissive
    print("Success! List-form `aud` claims are validated by membership, not exact match.")


# ---------------------------------------------------------------------------
# Removed mock-active fallback -- explicit regression test
# ---------------------------------------------------------------------------

async def _test_unconfigured_service_rejects_by_default():
    print("Testing an unconfigured OAuthService rejects tokens instead of mock-accepting them...")
    service = OAuthService(
        resource_uri="https://api.example.com",
        authorization_servers=["https://idp.example.com"],
        scopes_supported=["read"],
        # Deliberately no jwks_uri and no token_introspection_endpoint.
    )
    result = await service.introspect_token("any-token-at-all")
    assert result == {"active": False}, (
        "REGRESSION: an unconfigured OAuthService must reject tokens by default. "
        "It must never fall back to treating every token as valid."
    )
    print("Success! Unconfigured service correctly rejects (no mock-active fallback).")


def test_unconfigured_service_rejects_by_default():
    asyncio.run(_test_unconfigured_service_rejects_by_default())


# ---------------------------------------------------------------------------
# Discovery metadata (RFC 8414 / RFC 9728)
# ---------------------------------------------------------------------------

def test_discovery_document_has_required_fields():
    print("Testing RFC 8414 discovery document has all required fields...")
    service = OAuthService(
        resource_uri="https://api.example.com",
        authorization_servers=["https://idp.example.com"],
        scopes_supported=["read", "write"],
        token_introspection_endpoint="https://idp.example.com/introspect",
        jwks_uri="https://idp.example.com/.well-known/jwks.json",
        issuer="https://idp.example.com",
    )
    metadata = build_authorization_server_metadata(service)

    required_fields = {
        "issuer",
        "authorization_endpoint",
        "token_endpoint",
        "introspection_endpoint",
        "jwks_uri",
        "response_types_supported",
        "grant_types_supported",
        "subject_types_supported",
        "code_challenge_methods_supported",
    }
    missing = required_fields - set(metadata.keys())
    assert not missing, f"RFC 8414 document is missing required fields: {missing}"
    assert metadata["code_challenge_methods_supported"] == ["S256"]
    assert "registration_endpoint" not in metadata  # not passed in this call
    print("Success! All RFC 8414 required fields present.")


def test_discovery_document_includes_registration_endpoint_when_given():
    print("Testing RFC 8414 document includes registration_endpoint when DCR is enabled...")
    service = OAuthService(
        resource_uri="https://api.example.com",
        authorization_servers=["https://idp.example.com"],
        scopes_supported=["read"],
    )
    metadata = build_authorization_server_metadata(service, registration_endpoint="/oauth/v2/register")
    assert metadata["registration_endpoint"] == "/oauth/v2/register"
    print("Success! registration_endpoint included when supplied.")


def test_protected_resource_metadata_shape():
    print("Testing RFC 9728 protected-resource metadata shape...")
    service = OAuthService(
        resource_uri="https://api.example.com",
        authorization_servers=["https://idp.example.com"],
        scopes_supported=["read", "write"],
    )
    metadata = build_protected_resource_metadata(service)
    assert metadata == {
        "resource": "https://api.example.com",
        "authorization_servers": ["https://idp.example.com"],
        "scopes_supported": ["read", "write"],
    }
    print("Success! RFC 9728 document matches expected shape.")


# ---------------------------------------------------------------------------
# Dynamic Client Registration (RFC 7591) -- simplified/static variant
# ---------------------------------------------------------------------------

def test_client_registration_disabled_by_default():
    print("Testing Dynamic Client Registration is disabled by default...")
    service = OAuthService(
        resource_uri="https://api.example.com",
        authorization_servers=["https://idp.example.com"],
        scopes_supported=["read"],
    )
    assert is_client_registration_enabled(service) is False
    print("Success! DCR is disabled unless explicitly opted into.")


def test_client_registration_requires_both_flag_and_client_id():
    print("Testing DCR requires BOTH the opt-in flag AND a configured client id...")
    flag_only = OAuthService(
        resource_uri="https://api.example.com",
        authorization_servers=["https://idp.example.com"],
        scopes_supported=["read"],
        enable_client_registration=True,
        # no static_client_id
    )
    assert is_client_registration_enabled(flag_only) is False, "flag alone must not be enough"

    client_id_only = OAuthService(
        resource_uri="https://api.example.com",
        authorization_servers=["https://idp.example.com"],
        scopes_supported=["read"],
        enable_client_registration=False,
        static_client_id="configured-client",
    )
    assert is_client_registration_enabled(client_id_only) is False, "client id alone must not be enough"

    both = OAuthService(
        resource_uri="https://api.example.com",
        authorization_servers=["https://idp.example.com"],
        scopes_supported=["read"],
        enable_client_registration=True,
        static_client_id="configured-client",
    )
    assert is_client_registration_enabled(both) is True
    print("Success! DCR requires both conditions, matching the TypeScript SDK.")


def test_client_registration_response_shape():
    print("Testing DCR response returns the operator's static credentials...")
    service = OAuthService(
        resource_uri="https://api.example.com",
        authorization_servers=["https://idp.example.com"],
        scopes_supported=["read"],
        enable_client_registration=True,
        static_client_id="configured-client",
        static_client_secret="configured-secret",
    )
    response = build_registration_response(service, {"redirect_uris": ["myapp://callback"]})
    assert response["client_id"] == "configured-client"
    assert response["client_secret"] == "configured-secret"
    assert response["client_secret_expires_at"] == 0
    assert response["token_endpoint_auth_method"] == "client_secret_post"
    assert response["redirect_uris"] == ["myapp://callback"]

    # A public client (no secret) must get 'none' as its auth method -- that's
    # the OAuth 2.1 signal for "this client authenticates via PKCE, not a secret."
    public_service = OAuthService(
        resource_uri="https://api.example.com",
        authorization_servers=["https://idp.example.com"],
        scopes_supported=["read"],
        enable_client_registration=True,
        static_client_id="public-client",
    )
    public_response = build_registration_response(public_service, {})
    assert public_response["token_endpoint_auth_method"] == "none"
    print("Success! DCR response shape correct for both confidential and public clients.")


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

async def _test_jwks_client_is_cached():
    print("Testing the JWKS client is constructed once and reused across calls...")
    service = OAuthService(
        resource_uri="https://api.example.com",
        authorization_servers=["https://idp.example.com"],
        scopes_supported=["read"],
        jwks_uri="https://idp.example.com/.well-known/jwks.json",
    )
    with patch("jwt.PyJWKClient") as mock_client_cls:
        mock_client_cls.return_value.get_signing_key_from_jwt.side_effect = Exception("not a real token")
        await service.introspect_token("token-1")
        await service.introspect_token("token-2")
        assert mock_client_cls.call_count == 1, (
            f"expected PyJWKClient to be constructed once and cached, got {mock_client_cls.call_count} calls"
        )
    print("Success! PyJWKClient constructed once, reused on subsequent calls.")


def test_jwks_client_is_cached():
    asyncio.run(_test_jwks_client_is_cached())


async def _test_token_result_is_cached():
    print("Testing a successful introspection result is cached and reused...")
    service = OAuthService(
        resource_uri="https://api.example.com",
        authorization_servers=["https://idp.example.com"],
        scopes_supported=["read"],
        token_introspection_endpoint="https://idp.example.com/introspect",
    )
    with patch.object(
        service, "_introspect_via_endpoint",
        return_value={"active": True, "aud": "https://api.example.com", "sub": "u1"},
    ) as mock_call:
        r1 = await service.introspect_token("same-token")
        r2 = await service.introspect_token("same-token")
        assert r1 == r2
        assert mock_call.call_count == 1, (
            f"expected the underlying introspection call to run once, got {mock_call.call_count}"
        )
    print("Success! Token result cached, underlying introspection call only made once.")


def test_token_result_is_cached():
    asyncio.run(_test_token_result_is_cached())


def test_token_cache_respects_ttl_expiry():
    print("Testing the token cache expires entries after token_cache_seconds...")
    service = OAuthService(
        resource_uri="https://api.example.com",
        authorization_servers=["https://idp.example.com"],
        scopes_supported=["read"],
        token_cache_seconds=1,
    )
    service._cache_set("t1", {"active": True, "sub": "u1"})
    assert service._cache_get("t1") is not None
    with patch("time.monotonic", return_value=time.monotonic() + 2):
        assert service._cache_get("t1") is None, "expected the cached entry to expire after its TTL"
    print("Success! Cache entries expire after their TTL.")



# ---------------------------------------------------------------------------
# Introspection endpoint env-var resolution
# ---------------------------------------------------------------------------

def _clear_introspection_env():
    for key in (
        "OAUTH_INTROSPECTION_ENDPOINT",
        "INTROSPECTION_ENDPOINT",
        "INTROSPECTION_CLIENT_ID",
        "INTROSPECTION_CLIENT_SECRET",
        "JWKS_URI",
    ):
        os.environ.pop(key, None)


def _service():
    return OAuthService(
        resource_uri="http://localhost:3000/mcp",
        authorization_servers=["https://idp.example.com"],
        scopes_supported=["read"],
    )


def test_documented_introspection_env_var_is_honored():
    """OAUTH_SETUP.md, the CLI setup guide, and the flight-booking example all
    document `OAUTH_INTROSPECTION_ENDPOINT`, but the generated app modules read
    `INTROSPECTION_ENDPOINT`. Following the docs used to leave introspection
    silently unconfigured, which after the mock-fallback removal means every
    token is rejected. Both spellings must resolve."""
    print("Testing OAUTH_INTROSPECTION_ENDPOINT (the documented name) is honored...")
    saved = dict(os.environ)
    try:
        _clear_introspection_env()
        os.environ["OAUTH_INTROSPECTION_ENDPOINT"] = "https://idp.example.com/introspect"
        assert _service().token_introspection_endpoint == "https://idp.example.com/introspect"

        _clear_introspection_env()
        os.environ["INTROSPECTION_ENDPOINT"] = "https://legacy.example.com/introspect"
        assert _service().token_introspection_endpoint == "https://legacy.example.com/introspect"

        # Both set: the OAUTH_-prefixed name wins.
        _clear_introspection_env()
        os.environ["OAUTH_INTROSPECTION_ENDPOINT"] = "https://a.example.com/i"
        os.environ["INTROSPECTION_ENDPOINT"] = "https://b.example.com/i"
        assert _service().token_introspection_endpoint == "https://a.example.com/i"

        # Neither set: stays None, so the service has no verifier and rejects.
        _clear_introspection_env()
        assert _service().token_introspection_endpoint is None
    finally:
        os.environ.clear()
        os.environ.update(saved)
    print("Success! Both introspection env var spellings resolve.")


def test_explicit_introspection_arg_beats_env():
    print("Testing an explicit introspection endpoint argument overrides the environment...")
    saved = dict(os.environ)
    try:
        _clear_introspection_env()
        os.environ["OAUTH_INTROSPECTION_ENDPOINT"] = "https://env.example.com/i"
        service = OAuthService(
            resource_uri="http://localhost:3000/mcp",
            authorization_servers=["https://idp.example.com"],
            scopes_supported=["read"],
            token_introspection_endpoint="https://explicit.example.com/i",
        )
        assert service.token_introspection_endpoint == "https://explicit.example.com/i"
    finally:
        os.environ.clear()
        os.environ.update(saved)
    print("Success! Explicit configuration takes precedence over the environment.")


def test_introspection_client_credentials_resolve_from_env():
    print("Testing introspection client credentials fall back to the environment...")
    saved = dict(os.environ)
    try:
        _clear_introspection_env()
        os.environ["INTROSPECTION_CLIENT_ID"] = "client-abc"
        os.environ["INTROSPECTION_CLIENT_SECRET"] = "secret-xyz"
        service = _service()
        assert service.token_introspection_client_id == "client-abc"
        assert service.token_introspection_client_secret == "secret-xyz"
    finally:
        os.environ.clear()
        os.environ.update(saved)
    print("Success! Introspection client credentials resolve from the environment.")


if __name__ == "__main__":
    test_oauth_guard_validation()
    test_pkce_round_trip()
    test_pkce_rejects_mismatched_verifier()
    test_pkce_plain_method()
    test_pkce_unknown_method_raises()
    test_pkce_verifier_format_boundaries()
    test_pkce_support_requires_s256()
    test_audience_validation_endpoint_path()
    test_audience_validation_list_form()
    test_unconfigured_service_rejects_by_default()
    test_discovery_document_has_required_fields()
    test_discovery_document_includes_registration_endpoint_when_given()
    test_protected_resource_metadata_shape()
    test_client_registration_disabled_by_default()
    test_client_registration_requires_both_flag_and_client_id()
    test_client_registration_response_shape()
    test_jwks_client_is_cached()
    test_token_result_is_cached()
    test_token_cache_respects_ttl_expiry()
    test_documented_introspection_env_var_is_honored()
    test_explicit_introspection_arg_beats_env()
    test_introspection_client_credentials_resolve_from_env()
    print("\nAll OAuth tests passed successfully!")
