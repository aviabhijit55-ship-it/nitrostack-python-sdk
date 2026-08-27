"""Phase 6 — NitroTestingModule harness (Python-only)."""
from __future__ import annotations

import asyncio
import os
import sys

from pydantic import BaseModel

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack import (
    DIContainer,
    ExecutionContext,
    NitroTestingModule,
    injectable,
    module,
    prompt,
    resource,
    tool,
)
def setup_function() -> None:
    DIContainer.reset()


def teardown_function() -> None:
    DIContainer.reset()


class EchoIn(BaseModel):
    value: str = "hi"


@injectable()
class HarnessController:
    @tool(name="echo", description="echo", input_schema=EchoIn)
    async def echo(self, input: EchoIn, context: ExecutionContext) -> dict:
        return {"value": input.value}

    @resource(uri="note://hello", name="hello", description="json note")
    async def note(self, context: ExecutionContext) -> dict:
        return {"ok": True}

    @prompt(name="greet", description="greet")
    async def greet(self, arguments, context: ExecutionContext) -> list:
        return [{"role": "user", "content": "hello"}]


@module(name="harness", controllers=[HarnessController])
class HarnessModule:
    pass


def test_testing_module_tool_resource_prompt():
    harness = asyncio.run(NitroTestingModule.create(HarnessModule))
    assert asyncio.run(harness.call_tool("echo", {"value": "ada"})) == {"value": "ada"}
    assert asyncio.run(harness.read_resource("note://hello")) == {"ok": True}
    messages = asyncio.run(harness.get_prompt("greet", {}))
    assert messages[0].role == "user"


def test_testing_module_requires_bootstrapped_server():
    harness = NitroTestingModule.__new__(NitroTestingModule)
    harness.app = type("A", (), {"mcp_server": None})()
    try:
        asyncio.run(harness.call_tool("echo", {}))
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "bootstrapped" in str(exc)
