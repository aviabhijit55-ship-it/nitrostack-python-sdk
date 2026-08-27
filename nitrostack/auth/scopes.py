"""Scope helpers for AuthContext (TS ``hasScope`` / ``@RequireScopes``)."""
from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Callable, Iterable, Sequence

from nitrostack.core.context import AuthContext, ExecutionContext


def _scope_list(auth: AuthContext | None) -> list:
    if auth is None:
        return []
    scopes = getattr(auth, "scopes", None) or []
    if isinstance(scopes, str):
        return [part for part in scopes.split() if part]
    return list(scopes)


def has_scope(auth: AuthContext | None, scope: str) -> bool:
    return scope in _scope_list(auth)


def has_any_scope(auth: AuthContext | None, scopes: Iterable[str]) -> bool:
    have = set(_scope_list(auth))
    return any(scope in have for scope in scopes)


def has_all_scopes(auth: AuthContext | None, scopes: Iterable[str]) -> bool:
    have = set(_scope_list(auth))
    return all(scope in have for scope in scopes)


def require_scopes(*needed: str) -> Callable:
    """Reject the handler when ``context.auth`` is missing any of ``needed``.

    Works with async and sync handlers; the wrapper itself is always async.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any):
            context = kwargs.get("context")
            if context is None:
                for arg in args:
                    if isinstance(arg, ExecutionContext):
                        context = arg
                        break
            auth = getattr(context, "auth", None) if context is not None else None
            if auth is None:
                raise PermissionError("Not authenticated")
            if needed and not has_all_scopes(auth, needed):
                raise PermissionError(f"Missing required scopes: {', '.join(needed)}")
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        return wrapper

    return decorator


def scopes_from_sequence(values: Sequence[str] | str | None) -> list:
    if values is None:
        return []
    if isinstance(values, str):
        return [part for part in values.split() if part]
    return list(values)
