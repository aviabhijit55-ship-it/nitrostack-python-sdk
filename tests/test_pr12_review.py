"""Review fixes for PR #12 (widget render isolation, _meta merge, XSS, preview JSON)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import mcp.types as types

from nitrostack.core.app import McpApplication
from nitrostack.widgets.component import Component
from nitrostack.widgets.html_util import json_for_inline_script
from nitrostack.widgets.preview_page import render_preview_page
from nitrostack.widgets.ui import link_attrs, safe_href
from nitrostack.widgets.views import chart_body, pizza_list_body


class _Host:
    _widget_result_content = McpApplication._widget_result_content
    _to_call_tool_result = McpApplication._to_call_tool_result
    _call_tool_result_meta = staticmethod(McpApplication._call_tool_result_meta)


def test_widget_render_error_keeps_json_result():
    host = _Host()
    component = Component(id="pizza-list", name="Pizza list", html="<p>ok</p>")

    def boom(_data):
        raise ValueError("invalid literal for int() with base 10: 'expensive'")

    component.html_with_data = boom  # type: ignore[method-assign]
    structured = {"shops": [{"id": "x", "priceLevel": "expensive"}], "totalShops": 1}
    content = host._widget_result_content(structured, component)
    types_found = {getattr(block, "type", None) for block in content}
    assert "text" in types_found
    assert "resource" not in types_found
    assert "resource_link" in types_found
    text = next(block.text for block in content if getattr(block, "type", None) == "text")
    assert "expensive" in text


def test_custom_meta_merges_widget_meta():
    host = _Host()
    component = Component(id="sample", name="Sample", html="<p>ok</p>")
    result = types.CallToolResult(
        content=[types.TextContent(type="text", text="ok")],
        structuredContent={"ok": True},
        isError=False,
        **{"_meta": {"custom": 1}},
    )
    merged = host._to_call_tool_result(result, component)
    meta = merged.meta or {}
    assert meta["custom"] == 1
    assert meta["ui"]["resourceUri"] == component.resource_uri
    assert meta["openai/outputTemplate"] == component.resource_uri


def test_link_attrs_allowlists_schemes():
    assert "javascript:" not in link_attrs("javascript:alert(1)")
    assert safe_href("javascript:alert(1)") == ""
    assert safe_href("https://example.com/x") == "https://example.com/x"
    assert 'href="https://example.com/x"' in link_attrs("https://example.com/x")
    assert safe_href("mailto:a@b.com").startswith("mailto:")
    assert safe_href("tel:+1555").startswith("tel:")
    assert safe_href("//evil.example") == ""
    assert safe_href("data:text/html,hi") == ""


def test_pizza_list_coerces_bad_price_level():
    html = pizza_list_body(
        {
            "shops": [
                {
                    "id": "a",
                    "name": "Shop A",
                    "address": "1 Main",
                    "priceLevel": "expensive",
                    "openNow": True,
                }
            ],
            "totalShops": 1,
        }
    )
    assert "Shop A" in html
    assert "expensive" not in html


def test_chart_body_coerces_bad_values():
    html = chart_body({"title": "T", "items": [{"label": "A", "value": "nope"}]})
    assert "T" in html
    assert "A" in html


def test_preview_page_escapes_script_breaking_json():
    html = render_preview_page(
        [
            {
                "name": "</script><img src=x onerror=alert(1)>",
                "resourceUri": "ui://widget/x.html",
                "arguments": {},
            }
        ]
    )
    assert "</script><img" not in html
    assert json_for_inline_script(
        [{"name": "</script><img src=x onerror=alert(1)>"}]
    ).startswith("[")
