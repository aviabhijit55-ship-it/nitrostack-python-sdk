from nitrostack import (
    injectable,
    tool,
    widget,
    use_guards,
    OAuthGuard,
    ExecutionContext,
    WidgetOptions,
    ToolExamples,
)
from nitrostack.widgets.flight_transforms import (
    build_passengers,
    transform_airport_results,
    transform_flight_details,
    transform_flight_search,
)
from services.duffel_service import DuffelService
from guards.oauth_guard import create_scope_guard
from pydantic import BaseModel, Field, field_validator
from typing import Optional


class SearchFlightsInput(BaseModel):
    origin: str = Field(description="Origin airport IATA code (e.g., 'JFK', 'DEL', 'LHR')")
    destination: str = Field(description="Destination airport IATA code (e.g., 'LAX', 'LHR', 'CDG')")
    departureDate: str = Field(description="Departure date in YYYY-MM-DD format")
    returnDate: Optional[str] = Field(default=None, description="Return date in YYYY-MM-DD format for round trip")
    adults: int = Field(default=1, description="Number of adult passengers (18+)")
    children: int = Field(default=0, description="Number of child passengers (2-17)")
    infants: int = Field(default=0, description="Number of infant passengers (under 2)")
    cabinClass: str = Field(default="economy", description="Preferred cabin class (economy, premium_economy, business, first)")
    maxConnections: Optional[int] = Field(default=None, description="Maximum number of connections (0 for direct flights only)")
    departureTimeFrom: Optional[str] = Field(default=None, description="Earliest departure time in HH:MM format")
    departureTimeTo: Optional[str] = Field(default=None, description="Latest departure time in HH:MM format")

    @field_validator("origin", "destination")
    @classmethod
    def upper_iata(cls, value: str) -> str:
        return (value or "").strip().upper()


class FlightDetailsInput(BaseModel):
    offerId: str = Field(description="The flight offer ID from search results")


class AirportSearchInput(BaseModel):
    query: str = Field(min_length=2, description="City name or airport code to search for (e.g., 'Delhi', 'DEL', 'London')")


class GetAirlinesInput(BaseModel):
    pass


@injectable(deps=[DuffelService])
class FlightTools:
    def __init__(self, service: DuffelService):
        self.service = service

    @tool(
        name="search_flights",
        title="Search Flights",
        description="Search for flight offers based on origin, destination, dates, and preferences.",
        input_schema=SearchFlightsInput,
        examples=ToolExamples(
            input={"origin": "DEL", "destination": "LHR", "departureDate": "2026-08-19", "adults": 2, "cabinClass": "economy"},
            output={
                "requestId": "orq_mock123456",
                "searchParams": {"origin": "DEL", "destination": "LHR", "departureDate": "2026-08-19", "passengers": {"adults": 2, "children": 0, "infants": 0}, "cabinClass": "economy"},
                "totalOffers": 1,
                "offers": [{"id": "off_mock123456", "totalAmount": "450.00", "totalCurrency": "USD"}],
            },
            description="DEL → LHR mock search used by Studio / Inspector",
        ),
    )
    @use_guards(OAuthGuard, create_scope_guard(["read"]))
    @widget(WidgetOptions(route="flight-search-results", prefers_border=True))
    async def search_flights(self, input: SearchFlightsInput, context: ExecutionContext) -> dict:
        context.logger.info(f"Searching flights from {input.origin} to {input.destination}")
        passengers = build_passengers(input.adults, input.children, input.infants)
        departure_time = None
        if input.departureTimeFrom and input.departureTimeTo:
            departure_time = {"from": input.departureTimeFrom, "to": input.departureTimeTo}
        res = await self.service.search_flights(
            {
                **input.model_dump(),
                "passengers": passengers,
                "departureTime": departure_time,
            }
        )
        return transform_flight_search(input.model_dump(), res)

    @tool(
        name="get_flight_details",
        title="Get Flight Details",
        description="Get detailed information about a specific flight offer including baggage allowance, conditions.",
        input_schema=FlightDetailsInput,
        examples=ToolExamples(
            input={"offerId": "off_mock123456"},
            output={"id": "off_mock123456", "totalAmount": "450.00", "totalCurrency": "USD"},
            description="Details for the mock offer from the last search",
        ),
    )
    @use_guards(OAuthGuard, create_scope_guard(["read"]))
    @widget(WidgetOptions(route="flight-details", prefers_border=True))
    async def get_flight_details(self, input: FlightDetailsInput, context: ExecutionContext) -> dict:
        context.logger.info(f"Fetching flight details for offer {input.offerId}")
        res = await self.service.get_offer(input.offerId)
        return transform_flight_details(res)

    @tool(
        name="search_airports",
        title="Search Airports",
        description="Search for airports by city name or airport code. Useful for finding IATA codes.",
        input_schema=AirportSearchInput,
        examples=ToolExamples(
            input={"query": "Delhi"},
            output={"query": "Delhi", "results": [{"iataCode": "DEL", "name": "Indira Gandhi International Airport", "cityName": "Delhi"}]},
            description="Airport lookup used by Studio / Inspector",
        ),
    )
    @use_guards(OAuthGuard, create_scope_guard(["read"]))
    @widget(WidgetOptions(route="airport-search", prefers_border=True))
    async def search_airports(self, input: AirportSearchInput, context: ExecutionContext) -> dict:
        context.logger.info(f"Searching airports for query: {input.query}")
        places = await self.service.search_airports(input.query)
        return transform_airport_results(input.query, places)

    @tool(
        name="get_airlines",
        title="Get Airlines",
        description="Get list of common airlines.",
        input_schema=GetAirlinesInput
    )
    @use_guards(OAuthGuard, create_scope_guard(["read"]))
    async def get_airlines(self, input: GetAirlinesInput, context: ExecutionContext) -> dict:
        context.logger.info("Fetching common airlines")
        res = await self.service.get_airlines()
        return {"airlines": res}
