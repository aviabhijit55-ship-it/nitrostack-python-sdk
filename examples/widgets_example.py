"""
Widgets example — card, table, and chart tools with static HTML templates.

Run (stdio):
    cd examples && python widgets_example.py

Run (HTTP, stateless — good for MCP Inspector):
    MCP_TRANSPORT_TYPE=http MCP_STATELESS=true NITROSTACK_APP_MODE=universal \\
        python widgets_example.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pydantic import BaseModel, Field

from nitrostack import (
    ExecutionContext,
    McpApplicationFactory,
    ServerConfig,
    WidgetCsp,
    WidgetOptions,
    injectable,
    mcp_app,
    module,
    tool,
    widget,
)


class CardInput(BaseModel):
    product_id: str = Field(description="Product identifier")


class TableInput(BaseModel):
    limit: int = Field(default=3, description="Number of rows to return")


class ChartInput(BaseModel):
    title: str = Field(default="Sales", description="Chart title")


@injectable()
class WidgetsController:
    @tool(name="show_card", description="Show a product card widget", input_schema=CardInput)
    @widget("card")
    async def show_card(self, input: CardInput, context: ExecutionContext) -> dict:
        return {
            "id": input.product_id,
            "name": f"Product {input.product_id}",
            "price": 29.99,
            "description": "A sample product rendered in the card widget.",
        }

    @tool(name="show_table", description="Show a data table widget", input_schema=TableInput)
    @widget("table")
    async def show_table(self, input: TableInput, context: ExecutionContext) -> dict:
        rows = [
            {"name": "Alice", "score": 95},
            {"name": "Bob", "score": 87},
            {"name": "Carol", "score": 91},
        ][: max(1, input.limit)]
        return {"columns": ["name", "score"], "rows": rows}

    @tool(name="show_chart", description="Show a bar chart widget", input_schema=ChartInput)
    @widget(
        WidgetOptions(
            route="chart",
            prefers_border=True,
            domain="https://example.com",
            csp=WidgetCsp(connect_domains=["https://api.example.com"]),
        )
    )
    async def show_chart(self, input: ChartInput, context: ExecutionContext) -> dict:
        return {
            "title": input.title,
            "items": [
                {"label": "Jan", "value": 40},
                {"label": "Feb", "value": 65},
                {"label": "Mar", "value": 52},
            ],
        }


@module(name="widgets_example", controllers=[WidgetsController])
class WidgetsExampleModule:
    pass


@mcp_app(module=WidgetsExampleModule, server=ServerConfig(name="widgets-example", version="1.0.0"))
class WidgetsExampleApp:
    pass


async def main() -> None:
    app = await McpApplicationFactory.create(WidgetsExampleApp)
    await app.start()


if __name__ == "__main__":
    asyncio.run(main())
