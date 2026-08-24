"""Phase 0/6 — @module metadata (Python-only)."""
from __future__ import annotations

import asyncio
import os
import sys

from pydantic import BaseModel

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack import ExecutionContext, injectable, module, tool
from nitrostack.core.app import McpApplicationFactory, ServerConfig, mcp_app
from nitrostack.core.di import DIContainer


def setup_function() -> None:
    DIContainer.reset()


def teardown_function() -> None:
    DIContainer.reset()


def test_module_decorator_attaches_config():
    @module(name="billing", controllers=[], providers=[], imports=[], exports=[])
    class BillingModule:
        pass

    cfg = BillingModule._mcp_module_config
    assert cfg.name == "billing"
    assert cfg.controllers == []
    assert cfg.providers == []


def test_nested_module_imports_are_resolved_at_bootstrap():
    class PingInput(BaseModel):
        value: str = "x"

    @injectable()
    class ChildController:
        @tool(name="nested_ping", description="from imported module", input_schema=PingInput)
        async def ping(self, input: PingInput, context: ExecutionContext) -> str:
            return "pong"

    @module(name="nested-child", controllers=[ChildController])
    class NestedChildModule:
        pass

    @module(name="nested-parent", controllers=[], imports=[NestedChildModule])
    class NestedParentModule:
        pass

    @mcp_app(module=NestedParentModule, server=ServerConfig(name="nested-imports"))
    class NestedApp:
        pass

    app = asyncio.run(McpApplicationFactory.create(NestedApp))
    assert "nested_ping" in app._tools
