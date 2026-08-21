"""Python-rendered widget bodies from tool ``structuredContent``.

Hosts that inject data later still use the HTML document's small host-bridge
script. First paint (Inspector ``tools/call`` HTML, live preview) uses these
builders so the iframe matches the actual tool output — not sample JSON.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from nitrostack.widgets.html_util import (
    as_dict,
    as_list,
    esc,
    format_duration,
    mapbox_static_url,
    money,
    pick,
    place_code,
    place_name,
)
from nitrostack.widgets.ui import action_row, call_attrs, maps_url


def _safe_int(
    value: Any,
    default: int = 0,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    try:
        # OverflowError covers infinities: `json.loads("1e400")` yields `inf`, and
        # `int(float("inf"))` raises. NaN already surfaces as ValueError.
        n = int(float(value))
    except (TypeError, ValueError, OverflowError):
        n = default
    if minimum is not None:
        n = max(minimum, n)
    if maximum is not None:
        n = min(maximum, n)
    return n


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    if n != n or n in (float("inf"), float("-inf")):
        return default
    return n


def pizza_list_body(data: Any | None) -> str:
    payload = as_dict(data)
    shops = as_list(payload.get("shops"))
    total = payload.get("totalShops")
    if total is None:
        total = len(shops)
    if data is None:
        meta = "Waiting for show_pizza_list result."
        cards = ""
    elif not shops:
        meta = f"{total} shops"
        cards = '<div class="empty">No shops match these filters.</div>'
    else:
        meta = f"{total} shop" + ("" if total == 1 else "s")
        parts = []
        for shop in shops:
            shop = as_dict(shop)
            open_cls = "open" if shop.get("openNow") else "closed"
            open_label = "Open" if shop.get("openNow") else "Closed"
            price = "$" * _safe_int(shop.get("priceLevel"), 1, minimum=1, maximum=4)
            img = ""
            if shop.get("image"):
                img = f'<img class="img" src="{esc(shop["image"])}" alt="" />'
            rating = f"★ {esc(shop.get('rating'))}" if shop.get("rating") is not None else ""
            shop_id = shop.get("id") or ""
            parts.append(
                f'<article class="shop ns-card" {call_attrs("show_pizza_shop", {"shopId": shop_id})}>'
                f"{img}"
                f'<div class="row"><span class="name">{esc(shop.get("name") or shop_id or "Shop")}</span>'
                f'<span class="rating">{rating}</span></div>'
                f'<div class="addr">{esc(shop.get("address"))}</div>'
                f'<div><span class="badge {open_cls}">{open_label}</span> '
                f'<span class="badge">{esc(price)}</span></div>'
                "</article>"
            )
        cards = "".join(parts)
    return (
        "<h1>Pizza shops</h1>"
        f'<div class="meta" id="meta">{esc(meta)}</div>'
        '<div class="sorts" id="sorts">'
        '<button type="button" data-sort="rating" class="is-on">Rating</button>'
        '<button type="button" data-sort="name">Name</button>'
        "</div>"
        f'<div class="scroller" id="list">{cards}</div>'
        '<div id="root"></div>'
    )


def _pizza_map_card(shop: dict) -> str:
    name = shop.get("name") or shop.get("id") or "Shop"
    shop_id = shop.get("id") or ""
    rating = f"★ {esc(shop.get('rating'))}" if shop.get("rating") is not None else ""
    return (
        f'<article class="map-card ns-card" data-shop-id="{esc(shop_id)}" '
        f'{call_attrs("show_pizza_shop", {"shopId": shop_id})}>'
        f'<div class="name">{esc(name)}</div>'
        f'<div class="muted">{esc(shop.get("address"))}</div>'
        f'<div class="rating">{rating}</div></article>'
    )


def pizza_map_body(data: Any | None) -> str:
    payload = as_dict(data)
    shops = as_list(payload.get("shops"))
    static = ""
    if data is None or not shops:
        meta = "Waiting for show_pizza_map result."
        cards = ""
    else:
        filt = payload.get("filter") or "all"
        total = payload.get("totalShops")
        if total is None:
            total = len(shops)
        meta = f"{total} shops · filter: {filt}"
        cards = "".join(_pizza_map_card(as_dict(shop)) for shop in shops)
        static_src = mapbox_static_url(shops)
        static = (
            f'<img class="static-map" id="static-map" alt="Pizza shop map" '
            f'src="{esc(static_src)}" />'
            if static_src
            else ""
        )
    return (
        f'<div class="meta" id="meta">{esc(meta)}</div>'
        f'<div class="map" id="map" data-nitro-needs-client="1">'
        f'<div class="map-live" id="map-live"></div>{static}</div>'
        f'<div class="cards" id="cards">{cards}</div>'
        '<div id="root"></div>'
    )


def pizza_shop_body(data: Any | None) -> str:
    payload = as_dict(data)
    shop = as_dict(payload.get("shop") or payload if data is not None else {})
    if data is None or not shop.get("name"):
        return (
            '<div class="card">'
            '<img class="hero" id="hero" alt="" style="display:none" />'
            '<h1 id="name">Pizza shop</h1>'
            '<div class="rating" id="rating"></div>'
            '<p class="muted" id="desc">Waiting for show_pizza_shop result.</p>'
            '<p class="muted" id="addr"></p>'
            '<p class="muted" id="hours"></p>'
            '<p class="muted" id="phone"></p>'
            '<div class="chips" id="chips"></div>'
            '<div class="ns-actions" id="actions"></div>'
            "</div>"
            '<div id="root"></div>'
        )
    img = ""
    if shop.get("image"):
        img = f'<img class="hero" id="hero" src="{esc(shop["image"])}" alt="" />'
    else:
        img = '<img class="hero" id="hero" alt="" style="display:none" />'
    rating = ""
    if shop.get("rating") is not None:
        rating = f"★ {esc(shop.get('rating'))} ({esc(shop.get('reviews') or 0)} reviews)"
    hours = as_dict(shop.get("hours"))
    hours_text = ""
    if hours.get("open") or hours.get("close"):
        hours_text = f"Hours: {esc(hours.get('open'))} – {esc(hours.get('close'))}"
    chips = "".join(
        f'<span class="chip">{esc(item)}</span>' for item in as_list(shop.get("specialties"))
    )
    actions = action_row(maps=maps_url(shop), phone=str(shop.get("phone") or ""), website=str(shop.get("website") or ""))
    return (
        '<div class="card ns-surface">'
        f"{img}"
        f'<h1 id="name">{esc(shop.get("name"))}</h1>'
        f'<div class="rating" id="rating">{rating}</div>'
        f'<p class="muted" id="desc">{esc(shop.get("description"))}</p>'
        f'<p class="muted" id="addr">{esc(shop.get("address"))}</p>'
        f'<p class="muted" id="hours">{hours_text}</p>'
        f'<p class="muted" id="phone">{esc(shop.get("phone"))}</p>'
        f'<div class="chips" id="chips">{chips}</div>'
        f"{actions}"
        "</div>"
        '<div id="root"></div>'
    )


def calculator_result_body(data: Any | None) -> str:
    payload = as_dict(data)
    expr = payload.get("expression") or "—"
    result = payload.get("result")
    if result is None:
        result = payload.get("value")
    result_text = "—" if result is None else str(result)
    return (
        '<div class="card">'
        f'<div class="expr" id="expr">{esc(expr)}</div>'
        f'<div class="result" id="result">{esc(result_text)}</div>'
        "</div>"
        '<div id="root"></div>'
        '<div class="meta" id="meta"></div>'
    )


def card_body(data: Any | None) -> str:
    payload = as_dict(data)
    name = payload.get("name") or "—"
    price = payload.get("price")
    price_text = f"${float(price):.2f}" if isinstance(price, (int, float)) else (str(price) if price else "—")
    desc = payload.get("description") or ""
    return (
        '<div class="card">'
        f'<h2 id="name">{esc(name)}</h2>'
        f'<div class="price" id="price">{esc(price_text)}</div>'
        f'<p class="desc" id="desc">{esc(desc)}</p>'
        "</div>"
    )


def table_body(data: Any | None) -> str:
    payload = as_dict(data)
    rows = as_list(payload.get("rows"))
    cols = as_list(payload.get("columns"))
    if not cols and rows:
        cols = list(as_dict(rows[0]).keys())
    header = "".join(f"<th>{esc(c)}</th>" for c in cols)
    body_rows = []
    for row in rows:
        row = as_dict(row)
        cells = "".join(f"<td>{esc(row.get(c, ''))}</td>" for c in cols)
        body_rows.append(f"<tr>{cells}</tr>")
    return (
        "<table>"
        f'<thead><tr id="header">{header}</tr></thead>'
        f'<tbody id="body">{"".join(body_rows)}</tbody>'
        "</table>"
    )


def chart_body(data: Any | None) -> str:
    payload = as_dict(data)
    title = payload.get("title") or "Chart"
    items = as_list(payload.get("items"))
    values = [_safe_float(as_dict(i).get("value"), 0.0) for i in items]
    max_v = max(values or [1], default=1) or 1
    bars = []
    for item, value in zip(items, values):
        item = as_dict(item)
        height = (value / max_v) * 140
        bars.append(
            '<div class="bar-wrap">'
            f'<div class="bar" style="height:{height:.1f}px"></div>'
            f'<div class="label">{esc(item.get("label"))}</div>'
            "</div>"
        )
    return f'<h3 id="title">{esc(title)}</h3><div class="chart" id="chart">{"".join(bars)}</div>'


def _offer_slice_html(sl: dict) -> str:
    origin = place_code(sl.get("origin"))
    dest = place_code(sl.get("destination"))
    duration = format_duration(sl.get("duration"))
    segs = as_list(sl.get("segments"))
    first = as_dict(segs[0] if segs else {})
    last = as_dict(segs[-1] if segs else first)
    dep = pick(first, "departing_at", "departingAt", "departureTime", default="") or pick(
        sl, "departing_at", "departingAt", "departureTime", default=""
    )
    arr = pick(last, "arriving_at", "arrivingAt", "arrivalTime", default="") or pick(
        sl, "arriving_at", "arrivingAt", "arrivalTime", default=""
    )
    carrier = first.get("marketing_carrier") or first.get("airline") or sl.get("airline")
    if isinstance(carrier, str):
        airline = carrier
        flight_no = pick(first, "marketing_carrier_flight_number", "flightNumber", default="") or pick(
            sl, "flightNumber", "marketing_carrier_flight_number", default=""
        )
    else:
        carrier = as_dict(carrier)
        airline = pick(carrier, "name", default="") or pick(first, "airline", default="") or pick(sl, "airline", default="")
        flight_no = pick(carrier, "flight_number", "flightNumber", default="") or pick(
            first, "marketing_carrier_flight_number", "flightNumber", default=""
        ) or pick(sl, "flightNumber", default="")
    return (
        f'<div class="slice"><strong>{esc(origin)} → {esc(dest)}</strong>'
        f'<div class="muted">{esc(dep)} – {esc(arr)} · {esc(duration)}</div>'
        f'<div class="muted">{esc(airline)} {esc(flight_no)}</div></div>'
    )


def _offer_itinerary_html(offer: dict) -> str:
    slices = as_list(offer.get("slices"))
    if slices:
        return "".join(_offer_slice_html(as_dict(s)) for s in slices)
    parts = []
    outbound = offer.get("outbound")
    if outbound:
        parts.append(_offer_slice_html(as_dict(outbound)))
    ret = offer.get("return")
    if ret:
        parts.append(_offer_slice_html(as_dict(ret)))
    return "".join(parts) or _offer_slice_html(offer)


def flight_search_results_body(data: Any | None) -> str:
    payload = as_dict(data)
    offers = as_list(payload.get("offers") or payload.get("results"))
    if data is None:
        return (
            "<h1>Flight search</h1>"
            '<div class="meta" id="meta">Waiting for search_flights result.</div>'
            '<div id="list"></div><div id="root"></div>'
        )
    params = as_dict(payload.get("searchParams"))
    total = payload.get("totalOffers")
    if total is None:
        total = len(offers)
    if params.get("origin") and params.get("destination"):
        meta = f"{params.get('origin')} → {params.get('destination')} · {total} offer" + ("" if total == 1 else "s")
    else:
        meta = f"{total} offer" + ("" if total == 1 else "s")
    cards = []
    for offer in offers:
        offer = as_dict(offer)
        amount = pick(offer, "total_amount", "totalAmount", default="")
        currency = pick(offer, "total_currency", "totalCurrency", default="")
        slice_html = _offer_itinerary_html(offer)
        offer_id = offer.get("id") or ""
        cards.append(
            f'<article class="offer ns-card" {call_attrs("get_flight_details", {"offerId": offer_id})}>'
            f'<div class="row"><span class="price">{esc(money(amount, currency))}</span>'
            f'<span class="id">{esc(offer_id)}</span></div>{slice_html}</article>'
        )
    if not cards:
        cards.append('<div class="empty">No flight offers.</div>')
    return (
        "<h1>Flight search</h1>"
        f'<div class="meta" id="meta">{esc(meta)}</div>'
        f'<div id="list">{"".join(cards)}</div><div id="root"></div>'
    )


def flight_details_body(data: Any | None) -> str:
    payload = as_dict(data)
    if data is None or not payload:
        return (
            "<h1>Flight details</h1>"
            '<div class="meta" id="meta">Waiting for get_flight_details result.</div>'
            '<div id="root"></div>'
        )
    amount = pick(payload, "total_amount", "totalAmount", default="")
    currency = pick(payload, "total_currency", "totalCurrency", default="")
    slices = as_list(payload.get("slices"))
    slice_html = "".join(_offer_slice_html(as_dict(s)) for s in slices)
    offer_id = payload.get("id") or ""
    seats = ""
    if offer_id:
        seats = (
            f'<div class="ns-actions"><button type="button" class="ns-btn ns-btn-primary" '
            f'{call_attrs("get_seat_map", {"offerId": offer_id})}>Seat map</button></div>'
        )
    return (
        "<h1>Flight details</h1>"
        f'<div class="meta" id="meta">Offer {esc(offer_id)} · {esc(money(amount, currency))}</div>'
        f'<div id="root">{slice_html}{seats}</div>'
    )


def airport_search_body(data: Any | None) -> str:
    payload = as_dict(data)
    results = as_list(payload.get("results") or payload.get("airports") or payload.get("places"))
    query = payload.get("query") or ""
    if data is None:
        return (
            "<h1>Airport search</h1>"
            '<div class="meta" id="meta">Waiting for search_airports result.</div>'
            '<div id="list"></div><div id="root"></div>'
        )
    rows = []
    for item in results:
        item = as_dict(item)
        code = pick(item, "iata_code", "iataCode", default="")
        name = pick(item, "name", default="")
        city = pick(item, "city_name", "cityName", "city", default="")
        kind = pick(item, "type", default="airport")
        rows.append(
            f'<div class="row"><span class="code">{esc(code)}</span>'
            f'<div><div class="name">{esc(name)}</div>'
            f'<div class="muted">{esc(city)} · {esc(kind)}</div></div></div>'
        )
    if not rows:
        rows.append('<div class="empty">No airports found.</div>')
    return (
        "<h1>Airport search</h1>"
        f'<div class="meta" id="meta">Query: {esc(query)} · {len(results)} result(s)</div>'
        f'<div id="list">{"".join(rows)}</div><div id="root"></div>'
    )


def order_summary_body(data: Any | None) -> str:
    payload = as_dict(data)
    if data is None or not payload:
        return (
            "<h1>Order summary</h1>"
            '<div class="meta" id="meta">Waiting for order result.</div>'
            '<div id="root"></div>'
        )
    status = str(pick(payload, "status", default="held"))
    ref = pick(payload, "booking_reference", "bookingReference", default="")
    amount = pick(payload, "total_amount", "totalAmount", default="")
    currency = pick(payload, "total_currency", "totalCurrency", default="")
    passengers = as_list(payload.get("passengers"))
    pax = []
    for p in passengers:
        p = as_dict(p)
        name = pick(p, "name", default="") or " ".join(
            str(x) for x in (p.get("given_name") or p.get("givenName"), p.get("family_name") or p.get("familyName")) if x
        )
        pax.append(f'<div class="muted">{esc(name or p.get("id"))}</div>')
    slices = "".join(_offer_slice_html(as_dict(s)) for s in as_list(payload.get("slices")))
    order_id = payload.get("id") or payload.get("orderId") or ""
    cancel = ""
    if order_id and status.lower() not in {"cancelled", "canceled"}:
        cancel = (
            f'<div class="ns-actions"><button type="button" class="ns-btn" '
            f'{call_attrs("cancel_order", {"orderId": order_id})}>Cancel order</button></div>'
        )
    return (
        '<div class="card ns-surface">'
        f'<h1>Order {esc(status)}</h1>'
        f'<div class="meta">Ref {esc(ref)} · {esc(order_id)}</div>'
        f'<div class="price">{esc(money(amount, currency))}</div>'
        f'<h2>Passengers</h2>{"".join(pax) or "<div class=muted>None listed</div>"}'
        f'<h2>Itinerary</h2>{slices}'
        f"{cancel}"
        "</div>"
        '<div id="root"></div>'
    )


def _seat_cells(cabin: dict) -> str:
    rows_html = []
    rows = as_list(cabin.get("rows"))
    if rows:
        for row in rows:
            row = as_dict(row)
            seats = as_list(row.get("seats") or row.get("elements"))
            if not seats:
                for section in as_list(row.get("sections")):
                    seats.extend(as_list(as_dict(section).get("elements")))
            cells = []
            for seat in seats:
                seat = as_dict(seat)
                if seat.get("type") and seat.get("type") != "seat":
                    continue
                designator = pick(seat, "designator", "id", "column", default="")
                available = seat.get("available")
                if available is None:
                    available = bool(seat.get("available_services") is not None)
                cls = "seat ok" if available else "seat no"
                cells.append(f'<span class="{cls}">{esc(designator)}</span>')
            rows_html.append(
                f'<div class="seat-row"><span class="rn">{esc(row.get("row_number") or row.get("rowNumber") or "")}</span>'
                f"{''.join(cells)}</div>"
            )
    return "".join(rows_html)


def seat_selection_body(data: Any | None) -> str:
    payload = as_dict(data)
    cabins = as_list(payload.get("cabins"))
    if data is None:
        return (
            "<h1>Seat map</h1>"
            '<div class="meta" id="meta">Waiting for get_seat_map result.</div>'
            '<div id="root"></div>'
        )
    blocks = []
    for cabin in cabins:
        cabin = as_dict(cabin)
        klass = pick(cabin, "cabin_class", "cabinClass", default="cabin")
        blocks.append(f'<h2>{esc(klass)}</h2>{_seat_cells(cabin)}')
    if not blocks:
        blocks.append('<div class="empty">No seat map data.</div>')
    return (
        "<h1>Seat map</h1>"
        f'<div class="meta" id="meta">Offer {esc(payload.get("offerId") or payload.get("offer_id"))}</div>'
        f'<div id="root">{"".join(blocks)}</div>'
    )


def order_cancellation_body(data: Any | None) -> str:
    payload = as_dict(data)
    if data is None or not payload:
        return (
            "<h1>Cancellation</h1>"
            '<div class="meta" id="meta">Waiting for cancel_order result.</div>'
            '<div id="root"></div>'
        )
    refund = pick(payload, "refund_amount", "refundAmount", default="")
    currency = pick(payload, "refund_currency", "refundCurrency", default="")
    status = pick(payload, "status", default="cancelled")
    msg = pick(payload, "message", default="Booking cancelled.")
    cid = pick(payload, "id", "cancellationId", default="")
    return (
        '<div class="card">'
        "<h1>Booking cancelled</h1>"
        f'<div class="meta">{esc(status)} · {esc(cid)}</div>'
        f'<p>{esc(msg)}</p>'
        f'<div class="price">Refund {esc(money(refund, currency) or "n/a")}</div>'
        "</div>"
        '<div id="root"></div>'
    )


def generic_body(route: str, data: Any | None) -> str:
    import json

    if data is None:
        preview = "Waiting for host to send tool output…"
    else:
        preview = json.dumps(data, indent=2, default=str)
    return (
        f"<h1>{esc(route)}</h1>"
        '<div class="meta" id="meta">Tool output</div>'
        f'<pre id="root">{esc(preview)}</pre>'
    )


def missing_body(route: str) -> str:
    return (
        "<h1>Widget template missing</h1>"
        f'<div class="meta" id="meta">No HTML found for route <strong>{esc(route)}</strong>. '
        f"Create <code>widgets/out/{esc(route)}.html</code> or run <code>nitrostack-py init</code> again.</div>"
        '<div id="root"></div>'
    )


BODY_BUILDERS: Dict[str, Callable[[Any | None], str]] = {
    "pizza-list": pizza_list_body,
    "pizza-map": pizza_map_body,
    "pizza-shop": pizza_shop_body,
    "calculator-result": calculator_result_body,
    "card": card_body,
    "table": table_body,
    "chart": chart_body,
    "flight-search-results": flight_search_results_body,
    "flight-details": flight_details_body,
    "airport-search": airport_search_body,
    "order-summary": order_summary_body,
    "seat-selection": seat_selection_body,
    "order-cancellation": order_cancellation_body,
}


def render_body(route: str, data: Any | None = None) -> str:
    builder = BODY_BUILDERS.get(route)
    if builder is None:
        return generic_body(route, data)
    return builder(data)
