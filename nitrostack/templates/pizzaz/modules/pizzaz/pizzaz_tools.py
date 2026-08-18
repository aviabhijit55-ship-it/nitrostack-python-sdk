from nitrostack import (
    injectable,
    tool,
    widget,
    ExecutionContext,
    WidgetOptions,
    WidgetCsp,
    ToolExamples,
)
from pydantic import BaseModel, Field, field_validator
from typing import Any, Literal, Optional
from modules.pizzaz.pizzaz_service import PizzazService


def pizzaz_widget(route: str) -> WidgetOptions:
    return WidgetOptions(
        route=route,
        prefers_border=True,
        csp=WidgetCsp(
            resource_domains=[
                "https://images.unsplash.com",
                "https://api.mapbox.com",
                "https://events.mapbox.com",
                "https://docs.mapbox.com",
            ],
            connect_domains=["https://api.mapbox.com", "https://events.mapbox.com"],
        ),
    )


class ShowMapInput(BaseModel):
    filter: Literal["open_now", "top_rated", "all"] = Field(
        default="all",
        description="Filter to apply. Use open_now to hide closed shops. Leave empty for all shops.",
    )

    @field_validator("filter", mode="before")
    @classmethod
    def _blank_filter_is_all(cls, value: Any) -> Any:
        # Inspector sends "" when the dropdown is left empty (TS: args.filter || "all").
        if value is None or (isinstance(value, str) and not value.strip()):
            return "all"
        if isinstance(value, str):
            return value.strip()
        return value

class ShowListInput(BaseModel):
    openNow: Optional[bool] = Field(
        default=None,
        description="Set true to list only shops that are currently open. Omit to include closed shops.",
    )
    minRating: Optional[float] = Field(default=None, description="Minimum rating (1-5)")
    maxPrice: Optional[float] = Field(default=None, description="Maximum price level (1-3)")

class ShowShopInput(BaseModel):
    shopId: str = Field(description="ID of the pizza shop to display, e.g. tonys-pizza")


class PizzaListOutput(BaseModel):
    shops: list[dict[str, Any]]
    totalShops: int
    filters: Optional[dict[str, Any]] = None
    filter: Optional[str] = None


class PizzaShopOutput(BaseModel):
    shop: dict[str, Any]
    relatedShops: Optional[list[dict[str, Any]]] = None

_OPEN_SHOP_EXAMPLE = {
    "id": "tonys-pizza",
    "name": "Tony's New York Pizza",
    "address": "123 Main St, San Francisco, CA 94102",
    "rating": 4.5,
    "openNow": True,
}


@injectable(deps=[PizzazService])
class PizzazTools:
    def __init__(self, service: PizzazService):
        self.service = service

    @tool(
        name="show_pizza_map",
        description=(
            "Display an interactive map of pizza shops in San Francisco. "
            "Set filter=open_now when the user asks for shops that are open now."
        ),
        input_schema=ShowMapInput,
        output_schema=PizzaListOutput,
        examples=ToolExamples(
            input={"filter": "open_now"},
            output={"shops": [_OPEN_SHOP_EXAMPLE], "filter": "open_now", "totalShops": 1},
            description="Map of shops that are currently open",
        ),
    )
    @widget(pizzaz_widget("pizza-map"))
    async def show_pizza_map(self, input: ShowMapInput, context: ExecutionContext) -> dict:
        context.logger.info(f"Showing pizza map with filter: {input.filter}")
        if input.filter == "open_now":
            shops = self.service.get_shops_filtered({"openNow": True})
        elif input.filter == "top_rated":
            shops = self.service.get_top_rated_shops()
        else:
            shops = self.service.get_all_shops()

        return {
            "shops": shops,
            "filter": input.filter,
            "totalShops": len(shops)
        }

    @tool(
        name="show_pizza_list",
        description=(
            "Display a list of pizza shops with details, ratings, and filters. "
            "When the user asks for open shops only, you MUST pass openNow=true; "
            "omitting it returns closed shops as well."
        ),
        input_schema=ShowListInput,
        output_schema=PizzaListOutput,
        examples=ToolExamples(
            input={"openNow": True},
            output={
                "shops": [_OPEN_SHOP_EXAMPLE],
                "filters": {"openNow": True},
                "totalShops": 1,
            },
            description="List only shops that are currently open",
        ),
    )
    @widget(pizzaz_widget("pizza-list"))
    async def show_pizza_list(self, input: ShowListInput, context: ExecutionContext) -> dict:
        context.logger.info(f"Showing pizza list openNow={input.openNow}")
        filters = {}
        if input.openNow is not None:
            filters["openNow"] = input.openNow
        if input.minRating is not None:
            filters["minRating"] = input.minRating
        if input.maxPrice is not None:
            filters["maxPrice"] = input.maxPrice

        shops = self.service.get_shops_filtered(filters)
        return {
            "shops": shops,
            "filters": {
                "openNow": input.openNow,
                "minRating": input.minRating,
                "maxPrice": input.maxPrice
            },
            "totalShops": len(shops)
        }

    @tool(
        name="show_pizza_shop",
        description="Display detailed page for a single pizza shop, including menu, ratings, hours, and photos",
        input_schema=ShowShopInput,
        output_schema=PizzaShopOutput,
        examples=ToolExamples(
            input={"shopId": "tonys-pizza"},
            output={"shop": _OPEN_SHOP_EXAMPLE, "relatedShops": []},
            description="Detail page for Tony's New York Pizza",
        ),
    )
    @widget(pizzaz_widget("pizza-shop"))
    async def show_pizza_shop(self, input: ShowShopInput, context: ExecutionContext) -> dict:
        context.logger.info(f"Showing pizza shop: {input.shopId}")
        shop = self.service.get_shop_by_id(input.shopId)
        if not shop:
            raise ValueError(f"Pizza shop not found: {input.shopId}")
        return {
            "shop": shop,
            "relatedShops": [
                s for s in self.service.get_top_rated_shops(3) if s["id"] != shop["id"]
            ],
        }
