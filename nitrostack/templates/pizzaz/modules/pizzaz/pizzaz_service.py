from nitrostack import injectable
from modules.pizzaz.pizzaz_data import PIZZA_SHOPS


def _as_bool(value):
    """Inspector checkboxes sometimes send \"true\"/\"false\" strings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no", ""):
            return False
    return value


@injectable()
class PizzazService:
    def get_all_shops(self):
        return PIZZA_SHOPS

    def get_shop_by_id(self, shop_id: str):
        for shop in PIZZA_SHOPS:
            if shop["id"] == shop_id:
                return shop
        return None

    def get_shops_filtered(self, filters: dict):
        # Match the TypeScript SDK: copy then apply each filter.
        shops = list(PIZZA_SHOPS)
        if not filters:
            return shops
        if "openNow" in filters and filters.get("openNow") is not None:
            # True → open shops only. False / empty / "false" → no filter (all shops).
            # A model passing openNow=false to mean "I don't care" must not get closed-only.
            if _as_bool(filters.get("openNow")) is True:
                shops = [shop for shop in shops if shop["openNow"]]
        if filters.get("minRating") is not None:
            shops = [shop for shop in shops if shop["rating"] >= filters["minRating"]]
        if filters.get("maxPrice") is not None:
            shops = [shop for shop in shops if shop["priceLevel"] <= filters["maxPrice"]]
        if filters.get("cuisine"):
            cuisine_lower = str(filters["cuisine"]).lower()
            shops = [
                shop for shop in shops
                if any(cuisine_lower in c.lower() for c in shop["cuisine"])
            ]
        return shops

    def get_top_rated_shops(self, limit: int = 5):
        sorted_shops = sorted(PIZZA_SHOPS, key=lambda x: x["rating"], reverse=True)
        return sorted_shops[:limit]
