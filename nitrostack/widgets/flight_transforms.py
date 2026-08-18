"""TypeScript flight-tool output transforms, in Python.

Mirrors ``typescript-oauth`` ``flights.tools.ts`` / ``booking.tools.ts`` so
Python widgets receive the same camelCase ``structuredContent``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _place_code(place: Any) -> str:
    if isinstance(place, str):
        return place
    place = _as_dict(place)
    return str(place.get("iata_code") or place.get("iataCode") or place.get("code") or "")


def _carrier_name(seg: dict) -> str:
    carrier = seg.get("marketing_carrier") or seg.get("airline")
    if isinstance(carrier, str):
        return carrier
    carrier = _as_dict(carrier)
    return str(carrier.get("name") or "")


def _carrier_code(seg: dict) -> str:
    carrier = _as_dict(seg.get("marketing_carrier") or seg.get("airline"))
    return str(carrier.get("iata_code") or carrier.get("iataCode") or carrier.get("code") or "")


def _flight_number(seg: dict) -> str:
    return str(
        seg.get("marketing_carrier_flight_number")
        or seg.get("flightNumber")
        or _as_dict(seg.get("airline")).get("flightNumber")
        or ""
    )


def transform_airport_results(query: str, places: Any, limit: int = 10) -> Dict[str, Any]:
    results = []
    for place in _as_list(places)[:limit]:
        place = _as_dict(place)
        results.append(
            {
                "id": place.get("id"),
                "name": place.get("name"),
                "iataCode": place.get("iata_code") or place.get("iataCode"),
                "icaoCode": place.get("icao_code") or place.get("icaoCode"),
                "cityName": place.get("city_name") or place.get("cityName"),
                "type": place.get("type") or "airport",
                "latitude": place.get("latitude"),
                "longitude": place.get("longitude"),
                "timeZone": place.get("time_zone") or place.get("timeZone"),
            }
        )
    return {"query": query, "results": results}


def _slice_leg(slice_data: Any) -> Optional[Dict[str, Any]]:
    sl = _as_dict(slice_data)
    if not sl:
        return None
    segs = _as_list(sl.get("segments"))
    first = _as_dict(segs[0] if segs else {})
    last = _as_dict(segs[-1] if segs else first)
    return {
        "origin": _place_code(sl.get("origin") or first.get("origin")),
        "destination": _place_code(sl.get("destination") or last.get("destination")),
        "departureTime": first.get("departing_at") or first.get("departingAt") or sl.get("departureTime"),
        "arrivalTime": last.get("arriving_at") or last.get("arrivingAt") or sl.get("arrivalTime"),
        "duration": sl.get("duration"),
        "stops": max(len(segs) - 1, 0) if segs else 0,
        "airline": _carrier_name(first) or sl.get("airline"),
        "flightNumber": _flight_number(first) or sl.get("flightNumber"),
        "segments": [
            {
                "origin": _place_code(seg.get("origin")),
                "destination": _place_code(seg.get("destination")),
                "departingAt": seg.get("departing_at") or seg.get("departingAt"),
                "arrivingAt": seg.get("arriving_at") or seg.get("arrivingAt"),
                "airline": _carrier_name(seg),
                "flightNumber": _flight_number(seg),
                "aircraft": _as_dict(seg.get("aircraft")).get("name") if isinstance(seg.get("aircraft"), dict) else seg.get("aircraft"),
            }
            for seg in (_as_dict(s) for s in segs)
        ],
    }


def transform_flight_search(params: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    origin = str(params.get("origin") or "").upper()
    destination = str(params.get("destination") or "").upper()
    adults = int(params.get("adults") or 1)
    children = int(params.get("children") or 0)
    infants = int(params.get("infants") or 0)
    cabin = params.get("cabinClass") or "economy"

    offers: List[Dict[str, Any]] = []
    for offer in _as_list(_as_dict(result).get("offers")):
        offer = _as_dict(offer)
        slices = _as_list(offer.get("slices"))
        outbound = _slice_leg(slices[0] if slices else offer.get("outbound"))
        ret = _slice_leg(slices[1] if len(slices) > 1 else offer.get("return"))
        conditions = _as_dict(offer.get("conditions"))
        item: Dict[str, Any] = {
            "id": offer.get("id"),
            "totalAmount": offer.get("total_amount") or offer.get("totalAmount"),
            "totalCurrency": offer.get("total_currency") or offer.get("totalCurrency"),
            "expiresAt": offer.get("expires_at") or offer.get("expiresAt"),
            "outbound": outbound,
            "fareType": "International" if offer.get("passenger_identity_documents_required") else "Domestic",
            "refundable": bool(_as_dict(conditions.get("refund_before_departure")).get("allowed")),
            "changeable": bool(_as_dict(conditions.get("change_before_departure")).get("allowed")),
        }
        if ret:
            item["return"] = ret
        offers.append(item)

    return {
        "requestId": _as_dict(result).get("id") or _as_dict(result).get("requestId"),
        "searchParams": {
            "origin": origin,
            "destination": destination,
            "departureDate": params.get("departureDate"),
            "returnDate": params.get("returnDate"),
            "passengers": {"adults": adults, "children": children, "infants": infants},
            "cabinClass": cabin,
        },
        "totalOffers": len(offers),
        "offers": offers[:10],
        "message": f"Found {len(offers)} flight options. Showing top 10 results.",
    }


def transform_flight_details(offer: Dict[str, Any]) -> Dict[str, Any]:
    offer = _as_dict(offer)
    conditions = _as_dict(offer.get("conditions"))
    refund = _as_dict(conditions.get("refund_before_departure"))
    change = _as_dict(conditions.get("change_before_departure"))
    payment = _as_dict(offer.get("payment_requirements"))
    slices = []
    for sl in _as_list(offer.get("slices")):
        sl = _as_dict(sl)
        slices.append(
            {
                "origin": {
                    "code": _place_code(sl.get("origin")),
                    "name": _as_dict(sl.get("origin")).get("name"),
                    "city": _as_dict(sl.get("origin")).get("city_name") or _as_dict(sl.get("origin")).get("city"),
                },
                "destination": {
                    "code": _place_code(sl.get("destination")),
                    "name": _as_dict(sl.get("destination")).get("name"),
                    "city": _as_dict(sl.get("destination")).get("city_name") or _as_dict(sl.get("destination")).get("city"),
                },
                "duration": sl.get("duration"),
                "segments": [
                    {
                        "id": seg.get("id"),
                        "origin": _place_code(seg.get("origin")),
                        "destination": _place_code(seg.get("destination")),
                        "departingAt": seg.get("departing_at") or seg.get("departingAt"),
                        "arrivingAt": seg.get("arriving_at") or seg.get("arrivingAt"),
                        "duration": seg.get("duration"),
                        "airline": {
                            "name": _carrier_name(seg),
                            "code": _carrier_code(seg),
                            "flightNumber": _flight_number(seg),
                        },
                        "aircraft": _as_dict(seg.get("aircraft")).get("name") if isinstance(seg.get("aircraft"), dict) else seg.get("aircraft"),
                        "operatingCarrier": _as_dict(seg.get("operating_carrier")).get("name"),
                        "distance": seg.get("distance"),
                    }
                    for seg in (_as_dict(s) for s in _as_list(sl.get("segments")))
                ],
            }
        )
    return {
        "id": offer.get("id"),
        "totalAmount": offer.get("total_amount") or offer.get("totalAmount"),
        "totalCurrency": offer.get("total_currency") or offer.get("totalCurrency"),
        "expiresAt": offer.get("expires_at") or offer.get("expiresAt"),
        "slices": slices,
        "passengers": [
            {
                "id": pax.get("id"),
                "type": pax.get("type"),
                "fareType": pax.get("fare_type") or pax.get("fareType"),
                "baggageAllowance": [
                    {"type": bag.get("type"), "quantity": bag.get("quantity")}
                    for bag in _as_list(pax.get("baggages") or pax.get("baggageAllowance"))
                ],
            }
            for pax in (_as_dict(p) for p in _as_list(offer.get("passengers")))
        ],
        "conditions": {
            "refundBeforeDeparture": {
                "allowed": bool(refund.get("allowed")),
                "penaltyAmount": refund.get("penalty_amount") or refund.get("penaltyAmount"),
                "penaltyCurrency": refund.get("penalty_currency") or refund.get("penaltyCurrency"),
            },
            "changeBeforeDeparture": {
                "allowed": bool(change.get("allowed")),
                "penaltyAmount": change.get("penalty_amount") or change.get("penaltyAmount"),
                "penaltyCurrency": change.get("penalty_currency") or change.get("penaltyCurrency"),
            },
        },
        "paymentRequirements": {
            "requiresInstantPayment": payment.get("requires_instant_payment"),
            "priceGuaranteeExpiresAt": payment.get("price_guarantee_expires_at"),
            "paymentRequiredBy": payment.get("payment_required_by"),
        },
    }


def transform_create_order(order: Dict[str, Any]) -> Dict[str, Any]:
    order = _as_dict(order)
    slices = []
    for sl in _as_list(order.get("slices")):
        sl = _as_dict(sl)
        segs = _as_list(sl.get("segments"))
        first = _as_dict(segs[0] if segs else {})
        last = _as_dict(segs[-1] if segs else first)
        slices.append(
            {
                "origin": _place_code(sl.get("origin")),
                "destination": _place_code(sl.get("destination")),
                "departureTime": first.get("departing_at") or first.get("departingAt") or sl.get("departureTime"),
                "arrivalTime": last.get("arriving_at") or last.get("arrivingAt") or sl.get("arrivalTime"),
            }
        )
    return {
        "orderId": order.get("id") or order.get("orderId"),
        "status": order.get("status") or "held",
        "totalAmount": order.get("total_amount") or order.get("totalAmount"),
        "totalCurrency": order.get("total_currency") or order.get("totalCurrency"),
        "expiresAt": order.get("expires_at") or order.get("expiresAt"),
        "bookingReference": order.get("booking_reference") or order.get("bookingReference"),
        "passengers": [
            {
                "id": pax.get("id"),
                "name": pax.get("name")
                or " ".join(x for x in (pax.get("given_name") or pax.get("givenName"), pax.get("family_name") or pax.get("familyName")) if x),
                "type": pax.get("type"),
            }
            for pax in (_as_dict(p) for p in _as_list(order.get("passengers")))
        ],
        "slices": slices,
        "message": "Order created and held successfully.",
    }


def transform_order_details(order: Dict[str, Any]) -> Dict[str, Any]:
    order = _as_dict(order)
    details = transform_flight_details(order)
    details.pop("conditions", None)
    details.pop("paymentRequirements", None)
    return {
        "orderId": order.get("id") or order.get("orderId"),
        "status": order.get("status") or "confirmed",
        "bookingReference": order.get("booking_reference") or order.get("bookingReference"),
        "totalAmount": details.get("totalAmount"),
        "totalCurrency": details.get("totalCurrency"),
        "createdAt": order.get("created_at") or order.get("createdAt"),
        "expiresAt": order.get("expires_at") or order.get("expiresAt"),
        "passengers": [
            {
                "id": pax.get("id"),
                "name": pax.get("name")
                or " ".join(x for x in (pax.get("given_name") or pax.get("givenName"), pax.get("family_name") or pax.get("familyName")) if x),
                "type": pax.get("type"),
                "email": pax.get("email"),
                "phoneNumber": pax.get("phone_number") or pax.get("phoneNumber"),
            }
            for pax in (_as_dict(p) for p in _as_list(order.get("passengers")))
        ],
        "slices": details.get("slices") or [],
    }


def transform_seat_map(offer_id: str, seat_maps: Any) -> Dict[str, Any]:
    cabins = []
    for cabin in _as_list(seat_maps):
        cabin = _as_dict(cabin)
        rows = []
        for row in _as_list(cabin.get("rows")):
            row = _as_dict(row)
            seats = []
            raw_seats = _as_list(row.get("seats"))
            if not raw_seats:
                for section in _as_list(row.get("sections")):
                    raw_seats.extend(_as_list(_as_dict(section).get("elements")))
            for seat in raw_seats:
                seat = _as_dict(seat)
                kind = seat.get("type")
                if kind and kind not in ("seat", "window", "middle", "aisle", "standard"):
                    if kind != "seat" and seat.get("designator") is None and seat.get("column") is None:
                        continue
                services = _as_list(seat.get("available_services"))
                first = _as_dict(services[0] if services else {})
                available = seat.get("available")
                if available is None:
                    available = bool(services)
                seats.append(
                    {
                        "id": seat.get("id"),
                        "column": seat.get("designator") or seat.get("column"),
                        "available": bool(available),
                        "price": first.get("total_amount") or seat.get("price"),
                        "currency": first.get("total_currency") or seat.get("currency"),
                        "type": ", ".join(_as_list(seat.get("disclosures"))) or seat.get("type") or "standard",
                    }
                )
            rows.append({"rowNumber": row.get("row_number") or row.get("rowNumber"), "seats": seats})
        cabins.append({"cabinClass": cabin.get("cabin_class") or cabin.get("cabinClass"), "rows": rows})
    return {
        "offerId": offer_id,
        "cabins": cabins,
        "message": "Select your preferred seats from the available options",
    }


def transform_cancel_order(order_id: str, cancellation: Dict[str, Any]) -> Dict[str, Any]:
    cancellation = _as_dict(cancellation)
    refund = cancellation.get("refund_amount") or cancellation.get("refundAmount")
    currency = cancellation.get("refund_currency") or cancellation.get("refundCurrency")
    return {
        "orderId": order_id,
        "cancellationId": cancellation.get("id") or cancellation.get("cancellationId"),
        "status": "cancelled",
        "refundAmount": refund,
        "refundCurrency": currency,
        "confirmedAt": cancellation.get("confirmed_at") or cancellation.get("confirmedAt"),
        "message": (
            f"Order cancelled. Refund of {currency} {refund} will be processed."
            if refund
            else "Order cancelled. No refund available for this booking."
        ),
    }


def build_passengers(adults: int = 1, children: int = 0, infants: int = 0) -> List[Dict[str, Any]]:
    passengers: List[Dict[str, Any]] = [{"type": "adult"} for _ in range(max(adults, 1))]
    passengers.extend({"type": "child", "age": 12} for _ in range(max(children, 0)))
    passengers.extend({"type": "infant_without_seat"} for _ in range(max(infants, 0)))
    return passengers
