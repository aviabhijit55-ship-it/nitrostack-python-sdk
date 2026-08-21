"""Build mode-gated widget ``_meta`` for tools and resources."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from nitrostack.core.app_mode import is_mcp_app_mode, is_openai_mode
from nitrostack.widgets.component import Component, WidgetCsp

Visibility = Literal["visible", "hidden"]


def widget_csp_to_ui_csp(csp: Optional[WidgetCsp]) -> Optional[Dict[str, Any]]:
    if csp is None:
        return None
    out: Dict[str, Any] = {}
    if csp.connect_domains:
        out["connectDomains"] = list(csp.connect_domains)
    if csp.resource_domains:
        out["resourceDomains"] = list(csp.resource_domains)
    if csp.frame_domains:
        out["frameDomains"] = list(csp.frame_domains)
    return out or None


def openai_widget_csp(csp: Optional[WidgetCsp]) -> Optional[Dict[str, Any]]:
    if csp is None:
        return None
    out: Dict[str, Any] = {}
    if csp.connect_domains:
        out["connect_domains"] = list(csp.connect_domains)
    if csp.resource_domains:
        out["resource_domains"] = list(csp.resource_domains)
    if csp.frame_domains:
        out["frame_domains"] = list(csp.frame_domains)
    return out or None


def _ui_block_from_component(component: Component) -> Dict[str, Any]:
    ui: Dict[str, Any] = {}
    csp = widget_csp_to_ui_csp(component.csp)
    if csp:
        ui["csp"] = csp
    if component.prefers_border:
        ui["prefersBorder"] = True
    if component.domain:
        ui["domain"] = component.domain
    return ui


def merge_tool_ui_meta(
    resource_uri: str,
    component: Component,
    visibility: Optional[Visibility] = None,
) -> Dict[str, Any]:
    ui: Dict[str, Any] = {"resourceUri": resource_uri}
    ui.update(_ui_block_from_component(component))
    if visibility:
        ui["visibility"] = visibility
    return ui


def build_tool_list_meta(
    component: Component,
    visibility: Visibility,
    invocation: Optional[Any] = None,
) -> Dict[str, Any]:
    """Full ``_meta`` for ``tools/list``, gated by ``NITROSTACK_APP_MODE``."""
    resource_uri = component.resource_uri
    openai_meta = component.get_openai_resource_metadata()
    meta: Dict[str, Any] = {}

    meta["ui/template"] = resource_uri

    if is_openai_mode():
        meta["openai/outputTemplate"] = resource_uri
        meta.update(openai_meta)
        if component.can_invoke_tools and "openai/widgetAccessible" not in meta:
            meta["openai/widgetAccessible"] = True
        if invocation:
            if getattr(invocation, "invoking", None):
                meta["openai/toolInvocation/invoking"] = invocation.invoking
            if getattr(invocation, "invoked", None):
                meta["openai/toolInvocation/invoked"] = invocation.invoked

    if is_mcp_app_mode():
        meta["ui"] = merge_tool_ui_meta(resource_uri, component, visibility)

    return meta


def build_call_tool_result_meta(
    component: Component,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Result ``_meta`` for widget ``tools/call`` (direct and task paths)."""
    meta: Dict[str, Any] = dict(extra or {})
    resource_uri = component.resource_uri

    if is_mcp_app_mode():
        ui = meta.get("ui")
        if not isinstance(ui, dict):
            ui = {}
        if "resourceUri" not in ui:
            ui["resourceUri"] = resource_uri
        meta["ui"] = ui

    if is_openai_mode():
        if "openai/outputTemplate" not in meta:
            meta["openai/outputTemplate"] = resource_uri

    return meta


def resource_read_contents_meta(component: Component) -> Optional[Dict[str, Any]]:
    """``contents[]._meta`` for ``resources/read`` of a widget."""
    openai_meta = component.get_openai_resource_metadata()
    out: Dict[str, Any] = {}

    if is_mcp_app_mode():
        ui_block = _ui_block_from_component(component)
        if ui_block:
            out["ui"] = ui_block

    if is_openai_mode():
        for key in (
            "openai/widgetAccessible",
            "openai/widgetCSP",
            "openai/widgetDescription",
            "openai/widgetPrefersBorder",
            "openai/widgetDomain",
        ):
            if key in openai_meta:
                out[key] = openai_meta[key]

    return out or None
