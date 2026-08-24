"""Phase 6 — pipeline invocation order and short-circuit behavior."""
from __future__ import annotations

import asyncio
import time
import os
import sys
from typing import Any, Callable, List
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack import DIContainer, ExecutionContext
from nitrostack.auth.api_key import ApiKeyModule, ApiKeyService
from nitrostack.auth.jwt import JWTModule, JWTService
from nitrostack.core.pipeline import (
    ApiKeyGuard,
    JwtGuard,
    PipeMetadata,
    run_pipeline,
    use_filters,
    use_guards,
    use_interceptors,
    use_middleware,
    use_pipes,
)


def setup_function() -> None:
    DIContainer.reset()


def teardown_function() -> None:
    DIContainer.reset()


def _ctx() -> ExecutionContext:
    return ExecutionContext(request_id="p6", tool_name="probe", logger=MagicMock())


class RecordingGuard:
    def __init__(self, name: str, allow: bool, log: List[str]):
        self.name = name
        self.allow = allow
        self.log = log

    async def can_activate(self, context: ExecutionContext) -> bool:
        self.log.append(f"guard:{self.name}")
        return self.allow


class RecordingPipe:
    def __init__(self, name: str, log: List[str]):
        self.name = name
        self.log = log

    async def transform(self, value: Any, metadata: PipeMetadata) -> Any:
        self.log.append(f"pipe:{self.name}")
        return value


class RecordingMiddleware:
    def __init__(self, name: str, log: List[str]):
        self.name = name
        self.log = log

    async def use(self, context: ExecutionContext, next_fn: Callable) -> Any:
        self.log.append(f"middleware:{self.name}:before")
        result = await next_fn()
        self.log.append(f"middleware:{self.name}:after")
        return result


class RecordingInterceptor:
    def __init__(self, name: str, log: List[str]):
        self.name = name
        self.log = log

    async def intercept(self, context: ExecutionContext, next_fn: Callable) -> Any:
        self.log.append(f"interceptor:{self.name}:before")
        result = await next_fn()
        self.log.append(f"interceptor:{self.name}:after")
        return result


class RecordingFilter:
    def __init__(self, name: str, log: List[str]):
        self.name = name
        self.log = log

    async def catch(self, error: Exception, context: ExecutionContext) -> Any:
        self.log.append(f"filter:{self.name}")
        return {"caught": str(error)}


def _register(cls, instance) -> None:
    DIContainer.get_instance().register_value(cls, instance)


def test_pipeline_order_guards_pipes_middleware_interceptors_handler():
    log: List[str] = []
    _register(RecordingGuard, RecordingGuard("g", True, log))
    _register(RecordingPipe, RecordingPipe("p", log))
    _register(RecordingMiddleware, RecordingMiddleware("m", log))
    _register(RecordingInterceptor, RecordingInterceptor("i", log))

    async def handler(value, context):
        log.append("handler")
        return value

    asyncio.run(
        run_pipeline(
            handler=handler,
            handler_instance=None,
            args=("in",),
            kwargs={"context": _ctx()},
            context=_ctx(),
            guards=[RecordingGuard],
            middleware=[RecordingMiddleware],
            interceptors=[RecordingInterceptor],
            pipes=[RecordingPipe],
            filters=[],
        )
    )
    assert log == [
        "guard:g",
        "pipe:p",
        "middleware:m:before",
        "interceptor:i:before",
        "handler",
        "interceptor:i:after",
        "middleware:m:after",
    ]


def test_denied_guard_short_circuits_before_pipes():
    log: List[str] = []
    _register(RecordingGuard, RecordingGuard("deny", False, log))
    _register(RecordingPipe, RecordingPipe("p", log))
    _register(RecordingMiddleware, RecordingMiddleware("m", log))

    async def handler(value, context):
        log.append("handler")
        return value

    try:
        asyncio.run(
            run_pipeline(
                handler=handler,
                handler_instance=None,
                args=("in",),
                kwargs={},
                context=_ctx(),
                guards=[RecordingGuard],
                middleware=[RecordingMiddleware],
                interceptors=[],
                pipes=[RecordingPipe],
                filters=[],
            )
        )
        raise AssertionError("denied guard should raise")
    except PermissionError:
        pass
    assert log == ["guard:deny"]


def test_handler_exception_is_caught_by_filter():
    log: List[str] = []
    _register(RecordingFilter, RecordingFilter("f", log))

    async def handler(*args, **kwargs):
        log.append("handler")
        raise ValueError("boom")

    result = asyncio.run(
        run_pipeline(
            handler=handler,
            handler_instance=None,
            args=("in",),
            kwargs={},
            context=_ctx(),
            guards=[],
            middleware=[],
            interceptors=[],
            pipes=[],
            filters=[RecordingFilter],
        )
    )
    assert result == {"caught": "boom"}
    assert log == ["handler", "filter:f"]


def test_pipeline_decorators_attach_metadata():
    class G:
        async def can_activate(self, context):
            return True

    class M:
        async def use(self, context, next_fn):
            return await next_fn()

    class I:
        async def intercept(self, context, next_fn):
            return await next_fn()

    class P:
        async def transform(self, value, metadata):
            return value

    class F:
        async def catch(self, error, context):
            return error

    @use_guards(G)
    @use_middleware(M)
    @use_interceptors(I)
    @use_pipes(P)
    @use_filters(F)
    async def handler():
        return None

    assert handler._mcp_guards == [G]
    assert handler._mcp_middleware == [M]
    assert handler._mcp_interceptors == [I]
    assert handler._mcp_pipes == [P]
    assert handler._mcp_filters == [F]


def test_api_key_guard_rejects_missing_key():
    allowed = asyncio.run(ApiKeyGuard().can_activate(_ctx()))
    assert allowed is False


def test_api_key_guard_matches_env(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-key")
    ctx = _ctx()
    ctx.metadata["x-api-key"] = "secret-key"
    assert asyncio.run(ApiKeyGuard().can_activate(ctx)) is True
    ctx.metadata["x-api-key"] = "wrong"
    assert asyncio.run(ApiKeyGuard().can_activate(ctx)) is False


def test_jwt_guard_rejects_missing_bearer():
    assert asyncio.run(JwtGuard().can_activate(_ctx())) is False


def test_jwt_guard_accepts_valid_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "phase6-jwt")
    JWTModule.for_root(secret_env_var="JWT_SECRET", audience="mcp", issuer="nitro")
    token = DIContainer.get_instance().resolve(JWTService).create_token({"sub": "ada"})
    ctx = _ctx()
    ctx.metadata["authorization"] = f"Bearer {token}"
    assert asyncio.run(JwtGuard().can_activate(ctx)) is True
    assert ctx.auth is not None
    assert ctx.auth.subject == "ada"


def test_api_key_guard_uses_api_key_service(monkeypatch):
    monkeypatch.setenv("API_KEY", "from-service")
    ApiKeyModule.for_root(hashed=False)
    ctx = _ctx()
    ctx.metadata["x-api-key"] = "from-service"
    assert asyncio.run(ApiKeyGuard().can_activate(ctx)) is True
    assert DIContainer.get_instance().resolve(ApiKeyService).validate("from-service") is True



def test_jwt_guard_rejects_expired_and_mismatched_claims(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "phase6-jwt")
    JWTModule.for_root(secret_env_var="JWT_SECRET", audience="mcp", issuer="nitro")
    jwt = DIContainer.get_instance().resolve(JWTService)
    guard = JwtGuard()

    expired = jwt.create_token({"sub": "ada", "exp": int(time.time()) - 5})
    ctx = _ctx()
    ctx.metadata["authorization"] = f"Bearer {expired}"
    assert asyncio.run(guard.can_activate(ctx)) is False

    wrong_aud = jwt.create_token({"sub": "ada", "aud": "other"})
    ctx = _ctx()
    ctx.metadata["authorization"] = f"Bearer {wrong_aud}"
    assert asyncio.run(guard.can_activate(ctx)) is False

    wrong_iss = jwt.create_token({"sub": "ada", "iss": "other"})
    ctx = _ctx()
    ctx.metadata["authorization"] = f"Bearer {wrong_iss}"
    assert asyncio.run(guard.can_activate(ctx)) is False
