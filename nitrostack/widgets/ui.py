"""Shared Python HTML primitives and host-token CSS for widgets."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote_plus

from nitrostack.widgets.html_util import as_dict, esc

SHARED_CSS = """
html { color-scheme: light dark; }
:root {
  --ns-bg: var(--color-background-primary, light-dark(#f7f7f5, #161615));
  --ns-surface: var(--color-background-secondary, light-dark(#ffffff, #242422));
  --ns-text: var(--color-text-primary, light-dark(#141413, #f5f4ef));
  --ns-muted: var(--color-text-secondary, light-dark(#6b6b66, #a8a8a0));
  --ns-border: var(--color-border-primary, light-dark(#e6e4de, #3a3a36));
  --ns-accent: #ea580c;
  --ns-accent-soft: #ffedd5;
  --ns-ok: #166534;
  --ns-ok-bg: #dcfce7;
  --ns-bad: #991b1b;
  --ns-bad-bg: #fee2e2;
  --ns-radius: var(--border-radius-md, 14px);
  --ns-shadow: 0 1px 2px rgb(0 0 0 / 6%);
  --ns-shadow-hover: 0 8px 24px rgb(0 0 0 / 12%);
}
[data-theme="dark"] {
  --ns-accent-soft: #3b2414;
  --ns-ok-bg: #14532d;
  --ns-ok: #bbf7d0;
  --ns-bad-bg: #7f1d1d;
  --ns-bad: #fecaca;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: var(--font-sans, system-ui, -apple-system, sans-serif);
  background: var(--ns-bg);
  color: var(--ns-text);
  padding: max(12px, env(safe-area-inset-top)) max(16px, env(safe-area-inset-right))
    max(12px, env(safe-area-inset-bottom)) max(16px, env(safe-area-inset-left));
}
body.ns-flush { padding: 0; overflow: hidden; }
h1 { font-size: 1.1rem; font-weight: 700; margin: 0 0 4px; letter-spacing: -0.02em; }
h2 { font-size: 0.95rem; margin: 14px 0 6px; }
.meta { color: var(--ns-muted); font-size: 0.82rem; margin-bottom: 12px; }
.muted { color: var(--ns-muted); font-size: 0.85rem; }
.empty { color: var(--ns-muted); padding: 24px 0; text-align: center; }
.ns-chrome {
  display: flex; justify-content: flex-end; gap: 6px; margin: -4px 0 8px;
}
body.ns-flush .ns-chrome {
  position: absolute; top: 12px; right: 12px; z-index: 5; margin: 0;
}
.ns-icon-btn, .ns-btn {
  appearance: none; font: inherit; cursor: pointer;
  border: 1px solid var(--ns-border); background: var(--ns-surface);
  color: var(--ns-text); border-radius: 999px; text-decoration: none;
}
.ns-icon-btn {
  width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center;
  box-shadow: var(--ns-shadow);
}
.ns-btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 8px 12px; font-size: 0.82rem; font-weight: 600;
  box-shadow: var(--ns-shadow);
}
.ns-btn-primary { background: var(--ns-accent); color: #fff; border-color: transparent; }
.ns-icon-btn:hover, .ns-btn:hover, .ns-card:hover {
  box-shadow: var(--ns-shadow-hover);
}
.ns-card:hover { transform: translateY(-1px); }
.ns-icon-btn:focus-visible, .ns-btn:focus-visible, .ns-card:focus-visible {
  outline: 2px solid var(--ns-accent); outline-offset: 2px;
}
.ns-card {
  background: var(--ns-surface); border: 1px solid var(--ns-border);
  border-radius: var(--ns-radius); padding: 12px 14px; box-shadow: var(--ns-shadow);
  cursor: pointer; text-align: left;
}
.ns-card.is-busy, .ns-btn.is-busy { opacity: 0.6; pointer-events: none; }
.ns-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.badge, .chip {
  display: inline-block; font-size: 0.72rem; font-weight: 600;
  padding: 2px 8px; border-radius: 999px; background: var(--ns-accent-soft); color: var(--ns-accent);
}
.badge.open, .seat.ok { background: var(--ns-ok-bg); color: var(--ns-ok); }
.badge.closed, .seat.no { background: var(--ns-bad-bg); color: var(--ns-bad); }
.rating { color: var(--ns-accent); font-weight: 700; font-variant-numeric: tabular-nums; }
.price { font-weight: 800; font-variant-numeric: tabular-nums; color: var(--ns-accent); }
.id, .code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.scroller, .cards {
  display: flex; gap: 12px; overflow-x: auto; padding-bottom: 8px;
  scroll-snap-type: x mandatory; -webkit-overflow-scrolling: touch;
}
.sorts { display: flex; gap: 6px; margin: 0 0 12px; }
.sorts button {
  appearance: none; font: inherit; font-size: 0.75rem; font-weight: 600;
  padding: 4px 10px; border-radius: 999px; border: 1px solid var(--ns-border);
  background: var(--ns-surface); color: var(--ns-muted); cursor: pointer;
}
.sorts button.is-on { background: var(--ns-accent); color: #fff; border-color: transparent; }
""".strip()


def attr_json(value: Any) -> str:
    return esc(json.dumps(value, separators=(",", ":")))


def call_attrs(tool: str, args: dict | None = None) -> str:
    payload = args or {}
    return (
        f'data-call-tool="{esc(tool)}" data-args="{attr_json(payload)}" '
        'role="button" tabindex="0"'
    )


def link_attrs(url: str) -> str:
    return f'data-open-link="{esc(url)}" href="{esc(url)}"'


def maps_url(shop: Any) -> str:
    shop = as_dict(shop)
    coords = shop.get("coords")
    if isinstance(coords, (list, tuple)) and len(coords) == 2:
        try:
            lon = float(coords[0])
            lat = float(coords[1])
            return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        except (TypeError, ValueError):
            pass
    address = shop.get("address")
    if address:
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(str(address))}"
    return ""


def phone_href(phone: Any) -> str:
    raw = "".join(ch for ch in str(phone or "") if ch.isdigit() or ch == "+")
    return f"tel:{raw}" if raw else ""


def action_row(*, maps: str = "", phone: str = "", website: str = "") -> str:
    parts: list[str] = []
    if maps:
        parts.append(f'<a class="ns-btn" {link_attrs(maps)}>Maps</a>')
    tel = phone_href(phone)
    if tel:
        parts.append(f'<a class="ns-btn" {link_attrs(tel)}>Call</a>')
    if website:
        parts.append(f'<a class="ns-btn ns-btn-primary" {link_attrs(str(website))}>Website</a>')
    return f'<div class="ns-actions" id="actions">{"".join(parts)}</div>'
