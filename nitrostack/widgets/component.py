"""Python ``Component`` for static HTML widgets served as MCP resources."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

Transformer = Callable[[Any, Any], Any]
MetaTransformer = Callable[[Any, Any], Dict[str, Any]]


@dataclass
class WidgetCsp:
    connect_domains: List[str] = field(default_factory=list)
    resource_domains: List[str] = field(default_factory=list)
    frame_domains: List[str] = field(default_factory=list)


@dataclass
class WidgetOptions:
    route: str
    description: Optional[str] = None
    html: Optional[str] = None
    css: Optional[str] = None
    js: Optional[str] = None
    csp: Optional[WidgetCsp] = None
    domain: Optional[str] = None
    prefers_border: bool = False
    can_invoke_tools: bool = False


@dataclass
class Component:
    id: str
    name: str
    html: str
    description: Optional[str] = None
    css: Optional[str] = None
    js: Optional[str] = None
    csp: Optional[WidgetCsp] = None
    domain: Optional[str] = None
    prefers_border: bool = False
    can_invoke_tools: bool = False
    transformer: Optional[Transformer] = None
    meta_transformer: Optional[MetaTransformer] = None

    def __post_init__(self) -> None:
        if not (self.id or "").strip():
            raise ValueError("Component id is required")
        if not (self.name or "").strip():
            raise ValueError("Component name is required")

    @property
    def resource_uri(self) -> str:
        return f"ui://widget/{self.id}.html"

    def get_bundle(self) -> str:
        css_tag = f"<style>{self.css}</style>" if self.css else ""
        js_tag = f'<script type="module">{self.js}</script>' if self.js else ""
        return f"{self.html}\n{css_tag}\n{js_tag}".strip()

    def html_with_data(self, data: Any) -> str:
        """Python-render this widget with live tool output for Inspector / preview."""
        from nitrostack.widgets.html_util import inject_tool_data
        from nitrostack.widgets.route_templates import render_widget_html

        rendered = render_widget_html(self.id, data)
        if rendered:
            bundle_extra = ""
            if self.css:
                bundle_extra += f"<style>{self.css}</style>"
            if self.js:
                bundle_extra += f'<script type="module">{self.js}</script>'
            return f"{rendered}\n{bundle_extra}".strip()
        return inject_tool_data(self.get_bundle(), data)

    def get_openai_resource_metadata(self) -> Dict[str, Any]:
        """OpenAI widget keys used for tool list and resource-read ``meta``."""
        meta: Dict[str, Any] = {}
        if self.can_invoke_tools:
            meta["openai/widgetAccessible"] = True
        if self.description:
            meta["openai/widgetDescription"] = self.description
        if self.prefers_border:
            meta["openai/widgetPrefersBorder"] = True
        if self.domain:
            meta["openai/widgetDomain"] = self.domain
        if self.csp:
            csp_out: Dict[str, List[str]] = {}
            if self.csp.connect_domains:
                csp_out["connect_domains"] = list(self.csp.connect_domains)
            if self.csp.resource_domains:
                csp_out["resource_domains"] = list(self.csp.resource_domains)
            if self.csp.frame_domains:
                csp_out["frame_domains"] = list(self.csp.frame_domains)
            if csp_out:
                meta["openai/widgetCSP"] = csp_out
        return meta


def create_component(**kwargs: Any) -> Component:
    return Component(**kwargs)


def _route_id_from_spec(route: str) -> str:
    route = (route or "").strip()
    if not route:
        raise ValueError("widget route must not be empty")
    if route.startswith("ui://"):
        name = route.strip("/").removeprefix("widget/").removesuffix(".html").strip("/")
        if not name:
            raise ValueError("widget route must not be empty")
        return name
    return route.strip("/").removeprefix("widget/").removesuffix(".html").strip("/")


def parse_widget_options(spec: str | WidgetOptions | Dict[str, Any]) -> WidgetOptions:
    if isinstance(spec, WidgetOptions):
        if not (spec.route or "").strip():
            raise ValueError("widget route must not be empty")
        return spec
    if isinstance(spec, dict):
        opts = WidgetOptions(**spec)
        if not (opts.route or "").strip():
            raise ValueError("widget route must not be empty")
        return opts
    if isinstance(spec, str):
        route_id = _route_id_from_spec(spec)
        return WidgetOptions(route=route_id)
    raise TypeError(f"widget spec must be str, WidgetOptions, or dict, got {type(spec)}")


def _ancestor_widget_paths(start: Path, route_id: str) -> List[Path]:
    """Walk parents of a Python file looking for ``widgets/out/{route}.html``."""
    found: List[Path] = []
    current = start.parent if start.is_file() else start
    for parent in [current, *current.parents]:
        found.append(parent / "widgets" / "out" / f"{route_id}.html")
        if (parent / "main.py").is_file() or (parent / "app_module.py").is_file():
            break
    return found


def _project_root_paths(project_root: Path, route_id: str) -> List[Path]:
    """TS-parity search paths: ``widgets/out``, ``src/widgets/out``, ``dist/widgets/out``."""
    root = project_root.resolve()
    return [
        root / "widgets" / "out" / f"{route_id}.html",
        root / "src" / "widgets" / "out" / f"{route_id}.html",
        root / "dist" / "widgets" / "out" / f"{route_id}.html",
    ]


def find_project_root(start: Optional[Path] = None) -> Optional[Path]:
    """Find directory containing ``main.py`` or ``app_module.py``."""
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for parent in [current, *current.parents]:
        if (parent / "main.py").is_file() or (parent / "app_module.py").is_file():
            return parent
    return None


def load_widget_html(
    route: str,
    *,
    html: Optional[str] = None,
    search_paths: Optional[List[Path]] = None,
    from_file: Optional[Path] = None,
    project_root: Optional[Path] = None,
    allow_builtin: bool = True,
) -> Optional[str]:
    """Resolve widget HTML: explicit string, then disk paths, then built-in route templates."""
    if html:
        return html

    route_id = _route_id_from_spec(route)
    candidates: List[Path] = []
    if search_paths:
        for base in search_paths:
            if base.is_dir():
                candidates.append(base / f"{route_id}.html")
                candidates.append(base / "widgets" / "out" / f"{route_id}.html")
            else:
                candidates.append(base)
    if from_file is not None:
        candidates.extend(_ancestor_widget_paths(Path(from_file), route_id))
    root = project_root or find_project_root(from_file)
    if root is not None:
        candidates.extend(_project_root_paths(root, route_id))
    candidates.append(Path.cwd() / "widgets" / "out" / f"{route_id}.html")
    candidates.append(Path.cwd() / "src" / "widgets" / "out" / f"{route_id}.html")
    candidates.append(Path.cwd() / "dist" / "widgets" / "out" / f"{route_id}.html")

    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()) if path.is_absolute() or path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Failed to read widget HTML at %s: %s", path, exc)

    if allow_builtin:
        from nitrostack.widgets.route_templates import get_builtin_route_html

        builtin = get_builtin_route_html(route_id)
        if builtin:
            return builtin

    logger.error(
        "No widget HTML found for route %r (searched: %s)",
        route_id,
        ", ".join(str(p) for p in candidates),
    )
    return None
