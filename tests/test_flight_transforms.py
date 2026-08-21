"""TS-parity transforms for flight tools and the mock airport catalog."""
from nitrostack.widgets.flight_catalog import search_mock_airports
from nitrostack.widgets.flight_transforms import (
    transform_airport_results,
    transform_flight_details,
    transform_flight_search,
    transform_seat_map,
)
from nitrostack.widgets.views import render_body


def test_delhi_and_london_catalog():
    delhi = search_mock_airports("Delhi")
    assert delhi[0]["iata_code"] == "DEL"
    assert "Indira Gandhi" in delhi[0]["name"]
    assert search_mock_airports("new delhi")[0]["iata_code"] == "DEL"
    london = search_mock_airports("London")
    assert {a["iata_code"] for a in london} >= {"LHR", "LGW", "STN"}
    assert search_mock_airports("x") == []
    assert search_mock_airports("no-such-city") == []


def test_transform_airport_results_camelcase():
    raw = search_mock_airports("DEL")
    out = transform_airport_results("DEL", raw)
    assert out["results"][0]["iataCode"] == "DEL"
    assert out["results"][0]["cityName"] == "Delhi"


def test_transform_flight_search_matches_ts_widget_shape():
    raw = {
        "id": "orq_mock123456",
        "offers": [
            {
                "id": "off_mock123456",
                "total_amount": "450.00",
                "total_currency": "USD",
                "expires_at": "2026-12-31T12:00:00Z",
                "slices": [
                    {
                        "origin": {"iata_code": "DEL", "name": "Indira Gandhi International Airport", "city_name": "Delhi"},
                        "destination": {"iata_code": "LHR", "name": "London Heathrow Airport", "city_name": "London"},
                        "duration": "PT6H30M",
                        "segments": [
                            {
                                "origin": {"iata_code": "DEL"},
                                "destination": {"iata_code": "LHR"},
                                "departing_at": "2026-08-19T08:00:00Z",
                                "arriving_at": "2026-08-19T14:30:00Z",
                                "marketing_carrier": {"name": "Mock Airlines", "iata_code": "MK"},
                                "marketing_carrier_flight_number": "MK123",
                                "aircraft": {"name": "Boeing 787"},
                            }
                        ],
                    }
                ],
            }
        ],
    }
    out = transform_flight_search(
        {"origin": "del", "destination": "lhr", "departureDate": "2026-08-19", "adults": 2, "cabinClass": "economy"},
        raw,
    )
    assert out["searchParams"]["origin"] == "DEL"
    assert out["searchParams"]["destination"] == "LHR"
    assert out["searchParams"]["passengers"]["adults"] == 2
    offer = out["offers"][0]
    assert offer["totalAmount"] == "450.00"
    assert offer["outbound"]["origin"] == "DEL"
    assert offer["outbound"]["destination"] == "LHR"
    assert offer["outbound"]["airline"] == "Mock Airlines"
    html = render_body("flight-search-results", out)
    assert "DEL" in html and "LHR" in html
    details = transform_flight_details(raw["offers"][0])
    assert details["slices"][0]["origin"]["code"] == "DEL"


def test_transform_seat_map_matches_ts_widget_shape():
    out = transform_seat_map(
        "off_mock123456",
        [
            {
                "cabin_class": "economy",
                "rows": [
                    {
                        "row_number": 10,
                        "sections": [
                            {
                                "elements": [
                                    {
                                        "type": "seat",
                                        "id": "seat_10a",
                                        "designator": "10A",
                                        "available_services": [{"total_amount": "25.00", "total_currency": "USD"}],
                                        "disclosures": ["window"],
                                    }
                                ]
                            }
                        ],
                    }
                ],
            }
        ],
    )
    seat = out["cabins"][0]["rows"][0]["seats"][0]
    assert seat["column"] == "10A"
    assert seat["available"] is True
    assert seat["price"] == "25.00"
