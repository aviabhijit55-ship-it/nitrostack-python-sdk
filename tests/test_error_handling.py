"""Phase 6 — exception types through filters and MCP tool error shape."""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any
from unittest.mock import MagicMock

from pydantic import BaseModel
from starlette.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack import (
    AudienceMismatchError,
    DIContainer,
    ExecutionContext,
    InvalidTaskTransitionError,
    PromptNotFoundError,
    ResourceNotFoundError,
    TaskAlreadyTerminalError,
    TaskCancelledError,
    TaskExpiredError,
    TaskNotFoundError,
    TokenInactiveError,
    ToolExecutionError,
    ValidationError,
    injectable,
    module,
    tool,
)
from nitrostack.core.app import McpApplicationFactory, ServerConfig, mcp_app
from nitrostack.core.pipeline import run_pipeline
from nitrostack.transports.http import build_http_app


def setup_function() -> None:
    DIContainer.reset()


def teardown_function() -> None:
    DIContainer.reset()


class CatchAllFilter:
    async def catch(self, error: Exception, context: ExecutionContext) -> Any:
        return {"filter": type(error).__name__, "message": str(error)}


def test_custom_exceptions_are_catchable_by_filter():
    DIContainer.get_instance().register_value(CatchAllFilter, CatchAllFilter())

    errors = [
        ValidationError("bad input"),
        ResourceNotFoundError("missing"),
        PromptNotFoundError("no prompt"),
        TaskNotFoundError("t1"),
        TaskExpiredError("t1"),
        TaskAlreadyTerminalError("t1", "completed"),
        InvalidTaskTransitionError("working", "cancelled"),
        TaskCancelledError("t1"),
        ToolExecutionError("tool boom"),
        TokenInactiveError(),
        AudienceMismatchError("expected", "actual"),
    ]

    for err in errors:

        async def handler(*args, boom=err, **kwargs):
            raise boom

        result = asyncio.run(
            run_pipeline(
                handler=handler,
                handler_instance=None,
                args=(None,),
                kwargs={},
                context=ExecutionContext(request_id="e", tool_name="x", logger=MagicMock()),
                guards=[],
                middleware=[],
                interceptors=[],
                pipes=[],
                filters=[CatchAllFilter],
            )
        )
        assert result["filter"] == type(err).__name__


class EmptyInput(BaseModel):
    pass


@injectable()
class BoomController:
    @tool(name="explode", description="raise", input_schema=EmptyInput)
    async def explode(self, input: EmptyInput, context: ExecutionContext) -> dict:
        raise RuntimeError("secret internals must not leak as HTML")


@module(name="boom", controllers=[BoomController])
class BoomModule:
    pass


def test_uncaught_tool_error_is_mcp_error_not_traceback():
    @mcp_app(module=BoomModule, server=ServerConfig(name="boom-server"))
    class BoomApp:
        pass

    app = asyncio.run(McpApplicationFactory.create(BoomApp))
    http_app = build_http_app(app, enable_cors=True, stateless=True, json_response=True)
    with TestClient(http_app) as client:
        resp = client.post(
            "/mcp",
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "explode", "arguments": {}},
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    result = body["result"]
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "secret internals" in text
    assert "Traceback" not in text
    assert "<html" not in resp.text.lower()


def test_filter_that_raises_is_skipped_then_original_error():
    class BadFilter:
        async def catch(self, error, context):
            raise RuntimeError("filter failed")

    DIContainer.get_instance().register_value(BadFilter, BadFilter())

    async def handler(*args, **kwargs):
        raise ValidationError("still boom")

    try:
        asyncio.run(
            run_pipeline(
                handler=handler,
                handler_instance=None,
                args=(None,),
                kwargs={},
                context=ExecutionContext(request_id="e", tool_name="x", logger=MagicMock()),
                guards=[],
                middleware=[],
                interceptors=[],
                pipes=[],
                filters=[BadFilter],
            )
        )
        raise AssertionError("original error should re-raise")
    except ValidationError as exc:
        assert "still boom" in str(exc)
