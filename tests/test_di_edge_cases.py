"""Phase 6 — DI edge cases (circular deps, missing tokens, singletons)."""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack import DIContainer, injectable, module
from nitrostack.core.app import McpApplicationFactory, ServerConfig, mcp_app
from nitrostack.core.errors import DependencyResolutionError


def setup_function() -> None:
    DIContainer.reset()


def teardown_function() -> None:
    DIContainer.reset()


def test_missing_string_token_raises_at_resolve():
    container = DIContainer.get_instance()

    @injectable(deps=["NeverRegistered"])
    class NeedsMissing:
        def __init__(self, missing):
            self.missing = missing

    try:
        container.resolve(NeedsMissing)
        raise AssertionError("expected DependencyResolutionError")
    except DependencyResolutionError as exc:
        assert "NeverRegistered" in str(exc)


def test_circular_dependency_raises_clear_error():
    @injectable(deps=[])
    class ServiceA:
        def __init__(self, other=None):
            self.other = other

    @injectable(deps=[])
    class ServiceB:
        def __init__(self, other=None):
            self.other = other

    ServiceA._mcp_deps = [ServiceB]
    ServiceB._mcp_deps = [ServiceA]

    container = DIContainer.get_instance()
    try:
        container.resolve(ServiceA)
        raise AssertionError("expected circular dependency error")
    except DependencyResolutionError as exc:
        assert "Circular dependency" in str(exc)
        assert "ServiceA" in str(exc)
        assert "ServiceB" in str(exc)


def test_singleton_same_instance_across_resolves():
    @injectable()
    class Counter:
        def __init__(self):
            self.n = 0

    container = DIContainer.get_instance()
    first = container.resolve(Counter)
    second = container.resolve(Counter)
    first.n = 7
    assert first is second
    assert second.n == 7


def test_register_value_and_has_value():
    container = DIContainer.get_instance()

    class Token:
        pass

    instance = Token()
    assert container.has_value(Token) is False
    container.register_value(Token, instance)
    assert container.has_value(Token) is True
    assert container.resolve(Token) is instance


def test_constructor_failure_is_wrapped():
    @injectable()
    class Broken:
        def __init__(self):
            raise RuntimeError("cannot build")

    try:
        DIContainer.get_instance().resolve(Broken)
        raise AssertionError("expected DependencyResolutionError")
    except DependencyResolutionError as exc:
        assert "Broken" in str(exc)
        assert "cannot build" in str(exc)


def test_missing_dep_fails_at_app_bootstrap():
    @injectable(deps=["NeverRegistered"])
    class NeedsMissing:
        def __init__(self, missing):
            self.missing = missing

    @module(name="broken-boot", controllers=[NeedsMissing])
    class BrokenModule:
        pass

    @mcp_app(module=BrokenModule, server=ServerConfig(name="broken-boot"))
    class BrokenApp:
        pass

    try:
        asyncio.run(McpApplicationFactory.create(BrokenApp))
        raise AssertionError("expected DependencyResolutionError at bootstrap")
    except DependencyResolutionError as exc:
        assert "bootstrap" in str(exc)
        assert "NeverRegistered" in str(exc)
