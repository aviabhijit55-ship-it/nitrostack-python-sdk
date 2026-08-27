"""Phase 2/6 — scope helpers and @require_scopes (Python-only)."""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack import AuthContext, ExecutionContext, has_all_scopes, has_any_scope, has_scope, require_scopes
from nitrostack.auth.scopes import scopes_from_sequence


def test_scope_predicates():
    auth = AuthContext(subject="u", scopes=["read", "write"])
    assert has_scope(auth, "read") is True
    assert has_scope(auth, "admin") is False
    assert has_any_scope(auth, ["admin", "write"]) is True
    assert has_all_scopes(auth, ["read", "write"]) is True
    assert has_all_scopes(auth, ["read", "admin"]) is False
    assert has_scope(None, "read") is False


def test_require_scopes_allows_and_denies():
    @require_scopes("read")
    async def handler(context: ExecutionContext) -> str:
        return "ok"

    ctx = ExecutionContext(request_id="s", tool_name="t", logger=MagicMock())
    try:
        asyncio.run(handler(context=ctx))
        raise AssertionError("unauthenticated should fail")
    except PermissionError:
        pass

    ctx.auth = AuthContext(subject="u", scopes=["read"])
    assert asyncio.run(handler(context=ctx)) == "ok"

    ctx.auth = AuthContext(subject="u", scopes=["other"])
    try:
        asyncio.run(handler(context=ctx))
        raise AssertionError("missing scope should fail")
    except PermissionError as exc:
        assert "Missing required scopes" in str(exc)



def test_scopes_from_sequence_and_require_scopes_starargs():
    assert scopes_from_sequence(None) == []
    assert scopes_from_sequence("read write") == ["read", "write"]
    assert scopes_from_sequence(["admin"]) == ["admin"]

    @require_scopes("read", "write")
    async def handler(context: ExecutionContext) -> str:
        return "ok"

    ctx = ExecutionContext(request_id="s", tool_name="t", logger=MagicMock())
    ctx.auth = AuthContext(subject="u", scopes=["read"])
    try:
        asyncio.run(handler(ctx))
        raise AssertionError("partial scopes should fail")
    except PermissionError:
        pass

    ctx.auth = AuthContext(subject="u", scopes=["read", "write"])
    assert asyncio.run(handler(ctx)) == "ok"
