"""HTML helpers for Python-rendered widgets (no React/TS)."""

from __future__ import annotations

import html
import json
import os
from typing import Any, Optional

def get_mapbox_token() -> str:
    """Mapbox public token from ``MAPBOX_TOKEN`` or ``NEXT_PUBLIC_MAPBOX_TOKEN``.

    Never ships a baked-in key — GitHub push protection treats ``pk.eyJ…`` as a secret.
    """
    raw = (
        os.environ.get("MAPBOX_TOKEN")
        or os.environ.get("NEXT_PUBLIC_MAPBOX_TOKEN")
        or ""
    ).strip()
    if not raw or raw.startswith("pk.your_") or raw in {"YOUR_MAPBOX_TOKEN", "changeme", "placeholder"}:
        return ""
    return raw


def inject_mapbox_token(html_doc: str) -> str:
    """Fill ``window.__NITRO_MAPBOX_TOKEN`` from env at serve time.

    ``widgets/out/pizza-map.html`` is committed with an empty token so git does
    not store a ``pk.eyJ`` secret. Studio ``resources/read`` uses that file via
    ``get_bundle()``; without this rewrite the live map stays blank.
    """
    if "window.__NITRO_MAPBOX_TOKEN" not in html_doc:
        return html_doc
    assignment = f"window.__NITRO_MAPBOX_TOKEN = {json.dumps(get_mapbox_token())};"
    marker = "window.__NITRO_MAPBOX_TOKEN ="
    start = html_doc.find(marker)
    if start < 0:
        return html_doc
    end = html_doc.find(";", start)
    if end < 0:
        return html_doc
    return html_doc[:start] + assignment + html_doc[end + 1 :]


def mapbox_static_url(shops: Any, width: int = 800, height: int = 520) -> str:
    """Python first-paint map (no React). Pins match filtered shops."""
    from urllib.parse import quote

    token = get_mapbox_token()
    if not token:
        return ""

    pins = []
    for shop in shops or []:
        if not isinstance(shop, dict):
            continue
        coords = shop.get("coords")
        if not (isinstance(coords, (list, tuple)) and len(coords) == 2):
            continue
        try:
            lon = float(coords[0])
            lat = float(coords[1])
        except (TypeError, ValueError):
            continue
        pins.append(f"pin-s+ea580c({lon},{lat})")
        if len(pins) >= 50:
            break
    overlay = ",".join(pins) if pins else "pin-s+ea580c(-122.4194,37.7749)"
    token = quote(token, safe="")
    return (
        f"https://api.mapbox.com/styles/v1/mapbox/streets-v12/static/{overlay}/auto/"
        f"{width}x{height}@2x?access_token={token}"
    )


def esc(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def json_script(data: Any) -> str:
    payload = "null" if data is None else json.dumps(data, default=str)
    payload = payload.replace("</", "<\\/")
    return f'<script type="application/json" id="nitrostack-tool-data">{payload}</script>'


def inject_tool_data(html_doc: str, data: Any) -> str:
    """Embed tool JSON in an existing widget document so first paint matches tools/call."""
    marker = json_script(data)
    if 'id="nitrostack-tool-data"' in html_doc:
        start = html_doc.find('<script type="application/json" id="nitrostack-tool-data">')
        if start >= 0:
            end = html_doc.find("</script>", start)
            if end >= 0:
                return html_doc[:start] + marker + html_doc[end + len("</script>") :]
    if "<body>" in html_doc:
        return html_doc.replace("<body>", "<body>\n  " + marker, 1)
    return marker + html_doc


def as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def pick(obj: Any, *keys: str, default: Any = None) -> Any:
    if not isinstance(obj, dict):
        return default
    for key in keys:
        if obj.get(key) not in (None, ""):
            return obj[key]
    return default


def place_code(place: Any) -> str:
    if isinstance(place, str):
        return place
    return str(pick(place, "iata_code", "iataCode", "code", "id", default="") or "")


def place_name(place: Any) -> str:
    if isinstance(place, str):
        return place
    return str(
        pick(place, "name", "city_name", "cityName", "city", "iata_code", "iataCode", default="") or ""
    )


def money(amount: Any, currency: Any = None) -> str:
    if amount in (None, ""):
        return ""
    cur = f" {currency}" if currency else ""
    return f"{amount}{cur}"


def format_duration(value: Any) -> str:
    text = str(value or "")
    if not text.startswith("PT"):
        return text
    hours = minutes = 0
    rest = text[2:]
    if "H" in rest:
        hours_s, rest = rest.split("H", 1)
        try:
            hours = int(hours_s or 0)
        except ValueError:
            hours = 0
    if "M" in rest:
        minutes_s = rest.split("M", 1)[0]
        try:
            minutes = int(minutes_s or 0)
        except ValueError:
            minutes = 0
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    if minutes:
        return f"{minutes}m"
    return text
