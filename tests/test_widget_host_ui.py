"""Host-bridge RPCs and Python HTML builders for interactive widgets."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack.widgets.host_bridge import HOST_BRIDGE_JS
from nitrostack.widgets.route_templates import render_widget_html
from nitrostack.widgets.ui import action_row, maps_url, phone_href
from nitrostack.widgets.views import (
    flight_details_body,
    flight_search_results_body,
    order_summary_body,
    pizza_list_body,
    pizza_map_body,
    pizza_shop_body,
)


def test_host_bridge_exposes_mcp_and_openai_rpcs():
    assert "tools/call" in HOST_BRIDGE_JS
    assert "ui/open-link" in HOST_BRIDGE_JS
    assert "ui/request-display-mode" in HOST_BRIDGE_JS
    assert "ui/notifications/host-context-changed" in HOST_BRIDGE_JS
    assert "availableDisplayModes" in HOST_BRIDGE_JS
    assert "window.openai.callTool" in HOST_BRIDGE_JS
    assert "window.openai.openExternal" in HOST_BRIDGE_JS
    assert "window.openai.requestDisplayMode" in HOST_BRIDGE_JS
    assert "window.openai.setWidgetState" in HOST_BRIDGE_JS
    assert "window.nitrostack" in HOST_BRIDGE_JS


def test_pizza_list_cards_call_show_shop():
    html = pizza_list_body(
        {
            "shops": [
                {"id": "tonys-pizza", "name": "Tony's", "rating": 4.5, "address": "1 Main", "openNow": True}
            ],
            "totalShops": 1,
        }
    )
    assert 'data-call-tool="show_pizza_shop"' in html
    assert "tonys-pizza" in html
    assert "data-sort" in html


def test_pizza_map_cards_call_show_shop():
    html = pizza_map_body(
        {
            "shops": [
                {
                    "id": "tonys-pizza",
                    "name": "Tony's",
                    "address": "1 Main",
                    "coords": [-122.4, 37.7],
                    "rating": 4.5,
                }
            ],
            "totalShops": 1,
        }
    )
    assert 'data-call-tool="show_pizza_shop"' in html
    assert "tonys-pizza" in html


def test_pizza_shop_has_open_link_actions():
    html = pizza_shop_body(
        {
            "shop": {
                "id": "tonys-pizza",
                "name": "Tony's New York Pizza",
                "address": "123 Main St",
                "coords": [-122.4194, 37.7749],
                "phone": "(415) 555-0123",
                "website": "https://tonyspizza.example.com",
                "rating": 4.5,
                "reviews": 10,
            }
        }
    )
    assert "data-open-link" in html
    assert "tonyspizza.example.com" in html
    assert "tel:" in html
    assert "google.com/maps" in html


def test_maps_and_phone_helpers():
    assert maps_url({"coords": [-122.4, 37.8]}).endswith("37.8,-122.4")
    assert phone_href("(415) 555-0123") == "tel:4155550123"
    row = action_row(maps="https://maps.example", phone="555", website="https://x.example")
    assert "data-open-link" in row
    assert "Maps" in row
    assert "Call" in row
    assert "Website" in row


def test_flight_search_cards_call_details():
    html = flight_search_results_body(
        {
            "searchParams": {"origin": "DEL", "destination": "LHR"},
            "offers": [{"id": "off_1", "totalAmount": "450.00", "totalCurrency": "USD"}],
        }
    )
    assert 'data-call-tool="get_flight_details"' in html
    assert "off_1" in html


def test_flight_details_and_order_have_next_actions():
    details = flight_details_body({"id": "off_1", "totalAmount": "10", "slices": []})
    assert 'data-call-tool="get_seat_map"' in details
    order = order_summary_body({"id": "ord_1", "status": "held", "passengers": [], "slices": []})
    assert 'data-call-tool="cancel_order"' in order


def test_rendered_widgets_include_theme_and_not_generic_json_viewer():
    details = render_widget_html("flight-details", {"id": "off_1", "slices": []})
    assert details is not None
    assert "get_seat_map" in details
    assert "JSON.stringify(data, null, 2)" not in details
    assert "color-scheme" in details
    assert "--ns-bg" in details
    assert "data-display-mode" in details

    seats = render_widget_html("seat-selection", {"offerId": "off_1", "cabins": []})
    assert seats is not None
    assert "No seat map data" in seats
    assert "JSON.stringify(data, null, 2)" not in seats

    cancel = render_widget_html("order-cancellation", {"status": "cancelled", "message": "Done"})
    assert cancel is not None
    assert "Booking cancelled" in cancel
    assert "JSON.stringify(data, null, 2)" not in cancel
