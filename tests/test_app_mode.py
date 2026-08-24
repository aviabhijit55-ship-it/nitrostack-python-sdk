"""Phase 4 — NITROSTACK_APP_MODE parsing (Python-only)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack.core.app_mode import (
    RESOURCE_MIME_TYPE_MCP_APP,
    RESOURCE_MIME_TYPE_OPENAI,
    get_app_mode,
    get_widget_mime_type,
    is_mcp_app_mode,
    is_openai_mode,
)


def test_default_mode_is_universal(monkeypatch):
    monkeypatch.delenv("NITROSTACK_APP_MODE", raising=False)
    assert get_app_mode() == "universal"
    assert is_mcp_app_mode() is True
    assert is_openai_mode() is True
    assert get_widget_mime_type() == RESOURCE_MIME_TYPE_MCP_APP


def test_mcp_app_and_openai_aliases(monkeypatch):
    monkeypatch.setenv("NITROSTACK_APP_MODE", "mcp-app")
    assert get_app_mode() == "mcp-app"
    assert is_openai_mode() is False
    monkeypatch.setenv("NITROSTACK_APP_MODE", "openai")
    assert get_app_mode() == "openai"
    assert is_mcp_app_mode() is False
    assert get_widget_mime_type() == RESOURCE_MIME_TYPE_OPENAI
