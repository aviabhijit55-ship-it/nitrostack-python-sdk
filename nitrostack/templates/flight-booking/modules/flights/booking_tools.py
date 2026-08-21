from nitrostack import injectable, tool, widget, use_guards, OAuthGuard, ExecutionContext, WidgetOptions
from nitrostack.widgets.flight_transforms import (
    transform_cancel_order,
    transform_create_order,
    transform_order_details,
    transform_seat_map,
)
from services.duffel_service import DuffelService
from guards.oauth_guard import create_scope_guard
from pydantic import BaseModel, Field
import json


class CreateOrderInput(BaseModel):
    offerId: str = Field(description="The offer ID to book")
    passengers: str = Field(description="JSON string containing array of passenger objects. Each passenger must have: title (mr/ms/mrs/miss/dr), givenName (first name), familyName (last name), gender (M/F), bornOn (YYYY-MM-DD), email, phoneNumber.")


class OrderDetailsInput(BaseModel):
    orderId: str = Field(description="The order ID")


class SeatMapInput(BaseModel):
    offerId: str = Field(description="The offer ID to get seats for")


class CancelOrderInput(BaseModel):
    orderId: str = Field(description="The order ID to cancel")


def _parse_passengers(raw) -> list:
    if isinstance(raw, list):
        passengers_array = raw
    elif isinstance(raw, str):
        passenger_str = raw
        if passenger_str.startswith('\\"') or '\\"' in passenger_str:
            passenger_str = passenger_str.replace('\\"', '"').replace('\\\\', '\\')
        passengers_array = json.loads(passenger_str)
    else:
        raise ValueError("Passengers must be a JSON string or array")
    if not passengers_array:
        raise ValueError("At least one passenger is required to create an order")
    passengers = []
    for pax in passengers_array:
        passengers.append({
            "title": pax.get("title", "mr"),
            "given_name": pax.get("givenName") or pax.get("given_name"),
            "family_name": pax.get("familyName") or pax.get("family_name"),
            "gender": pax.get("gender", "M"),
            "born_on": pax.get("bornOn") or pax.get("born_on"),
            "email": pax.get("email"),
            "phone_number": pax.get("phoneNumber") or pax.get("phone_number"),
        })
    return passengers


@injectable(deps=[DuffelService])
class BookingTools:
    def __init__(self, service: DuffelService):
        self.service = service

    @tool(
        name="create_order",
        title="Create Order",
        description="Create a flight order with hold (no payment required). Collect passenger details first.",
        input_schema=CreateOrderInput
    )
    @use_guards(OAuthGuard, create_scope_guard(["write"]))
    @widget(WidgetOptions(route="order-summary", prefers_border=True))
    async def create_order(self, input: CreateOrderInput, context: ExecutionContext) -> dict:
        context.logger.info(f"Creating flight order for offer {input.offerId}")
        passengers = _parse_passengers(input.passengers)
        res = await self.service.create_order({
            "selectedOffers": [input.offerId],
            "passengers": passengers,
        })
        return transform_create_order(res)

    @tool(
        name="get_order_details",
        title="Get Order Details",
        description="Get detailed information about an order.",
        input_schema=OrderDetailsInput
    )
    @use_guards(OAuthGuard, create_scope_guard(["read"]))
    @widget(WidgetOptions(route="order-summary", prefers_border=True))
    async def get_order_details(self, input: OrderDetailsInput, context: ExecutionContext) -> dict:
        context.logger.info(f"Fetching details for order {input.orderId}")
        res = await self.service.get_order(input.orderId)
        return transform_order_details(res)

    @tool(
        name="get_seat_map",
        title="Get Seat Map",
        description="Get available seats for a flight offer to allow seat selection.",
        input_schema=SeatMapInput
    )
    @use_guards(OAuthGuard, create_scope_guard(["read"]))
    @widget(WidgetOptions(route="seat-selection", prefers_border=True))
    async def get_seat_map(self, input: SeatMapInput, context: ExecutionContext) -> dict:
        context.logger.info(f"Fetching seat map for offer {input.offerId}")
        res = await self.service.get_seats_for_offer(input.offerId)
        return transform_seat_map(input.offerId, res)

    @tool(
        name="cancel_order",
        title="Cancel Order",
        description="Cancel a flight order and request refund if applicable.",
        input_schema=CancelOrderInput
    )
    @use_guards(OAuthGuard, create_scope_guard(["write"]))
    @widget(WidgetOptions(route="order-cancellation", prefers_border=True))
    async def cancel_order(self, input: CancelOrderInput, context: ExecutionContext) -> dict:
        context.logger.info(f"Cancelling order {input.orderId}")
        res = await self.service.cancel_order(input.orderId)
        return transform_cancel_order(input.orderId, res)
