"""Widget HTML for all three official Python templates (starter, pizzaz, oauth)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pathlib import Path

from nitrostack.widgets.component import Component
from nitrostack.widgets.route_templates import get_builtin_route_html, render_widget_html
from nitrostack.widgets.views import pizza_list_body, render_body

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "nitrostack" / "templates"


def test_starter_calculator_html_exists():
    path = TEMPLATES / "starter" / "widgets" / "out" / "calculator-result.html"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "Calculator result" in text
    assert text == get_builtin_route_html("calculator-result")


def test_oauth_flight_html_files_exist():
    routes = (
        "flight-search-results",
        "flight-details",
        "airport-search",
        "order-summary",
        "seat-selection",
        "order-cancellation",
    )
    out = TEMPLATES / "flight-booking" / "widgets" / "out"
    for route in routes:
        path = out / f"{route}.html"
        assert path.is_file(), f"missing {path}"
        builtin = get_builtin_route_html(route)
        assert builtin is not None
        assert path.read_text(encoding="utf-8") == builtin


def test_python_pizza_list_renders_all_tool_shops():
    shops = [
        {"id": "a", "name": "Shop A", "rating": 4.5, "address": "1 Main", "priceLevel": 2, "openNow": True},
        {"id": "b", "name": "Shop B", "rating": 4.1, "address": "2 Main", "priceLevel": 1, "openNow": False},
        {"id": "c", "name": "Shop C", "rating": 4.9, "address": "3 Main", "priceLevel": 3, "openNow": True},
    ]
    html = pizza_list_body({"shops": shops, "totalShops": 3})
    assert "Shop A" in html
    assert "Shop B" in html
    assert "Shop C" in html
    assert "3 shops" in html
    empty = pizza_list_body(None)
    assert "Waiting" in empty
    assert "Shop A" not in empty


def test_component_html_with_data_matches_tool_output():
    component = Component(id="pizza-list", name="Pizza list", html=get_builtin_route_html("pizza-list") or "")
    filled = component.html_with_data(
        {
            "shops": [
                {"id": "a", "name": "Live Shop", "rating": 5, "address": "A St", "priceLevel": 1, "openNow": True}
            ],
            "totalShops": 1,
        }
    )
    assert "Live Shop" in filled
    assert 'data-nitro-ssr="1"' in filled
    static = get_builtin_route_html("pizza-list") or ""
    assert "Live Shop" not in static


def test_flight_search_body_uses_ts_camelcase_shape():
    html = render_body(
        "flight-search-results",
        {
            "searchParams": {"origin": "DEL", "destination": "LHR", "departureDate": "2026-08-19"},
            "totalOffers": 1,
            "offers": [
                {
                    "id": "off_1",
                    "totalAmount": "450.00",
                    "totalCurrency": "USD",
                    "outbound": {
                        "origin": "DEL",
                        "destination": "LHR",
                        "departureTime": "2026-08-19T08:00:00Z",
                        "arrivalTime": "2026-08-19T14:30:00Z",
                        "duration": "PT6H30M",
                        "airline": "Mock Airlines",
                        "flightNumber": "MK123",
                    },
                }
            ],
        },
    )
    assert "DEL" in html
    assert "LHR" in html
    assert "450.00" in html
    assert "Mock Airlines" in html


def test_airport_search_body_uses_ts_camelcase_shape():
    html = render_body(
        "airport-search",
        {
            "query": "Delhi",
            "results": [
                {
                    "iataCode": "DEL",
                    "name": "Indira Gandhi International Airport",
                    "cityName": "Delhi",
                    "type": "airport",
                }
            ],
        },
    )
    assert "DEL" in html
    assert "Indira Gandhi" in html
    assert "Delhi" in html


def test_flight_search_body_uses_duffel_shape():
    html = render_body(
        "flight-search-results",
        {
            "offers": [
                {
                    "id": "off_1",
                    "total_amount": "450.00",
                    "total_currency": "USD",
                    "slices": [
                        {
                            "origin": {"iata_code": "JFK"},
                            "destination": {"iata_code": "LAX"},
                            "duration": "PT6H30M",
                        }
                    ],
                }
            ]
        },
    )
    assert "JFK" in html
    assert "LAX" in html
    assert "450.00" in html


def test_render_widget_html_unknown_route():
    assert render_widget_html("not-a-real-route") is None
    assert get_builtin_route_html("calculator-result") is not None
