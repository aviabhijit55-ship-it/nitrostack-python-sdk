"""
Streamable HTTP transport for NitroStack (Phase 3).

The official `mcp` SDK's `StreamableHTTPSessionManager` already provides most
of what the TypeScript SDK hand-rolls in Express: per-session isolation (one
transport + one `Server.run()` task per session), SSE streaming, resumability
via an event store, idle-session timeouts, and DNS-rebinding protection via
`TransportSecuritySettings`. This module does NOT reimplement any of that —
it wires those existing features through NitroStack's config/env vars and
adds the handful of pieces the manager does not provide out of the box:

- CORS (matching the header set the TS SDK exposes)
- A concurrent-session cap with a `429` response (the manager has no public
  session-count API or creation hook, so this is tracked via a thin ASGI
  middleware watching the `mcp-session-id` header)
- A `/mcp/health` endpoint
- Legacy SSE (`/sse` + `/mcp/messages/`) for older HTTP+SSE-only clients

See `dev-plan/PHASE-3-http-transport.md` for the full scope.
"""
from __future__ import annotations

import contextlib
import logging
import os
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings

if TYPE_CHECKING:
    from nitrostack.core.app import McpApplication

logger = logging.getLogger("nitrostack.transports.http")

DEFAULT_ENDPOINT = "/mcp"

# Mirrors the header set the TypeScript SDK's `StreamableHttpTransport` exposes
# in `setupMiddleware()` so browser-based MCP clients behave identically
# regardless of which SDK the server is built with.
CORS_ALLOW_HEADERS = [
    "Content-Type",
    "Accept",
    "Authorization",
    "Mcp-Session-Id",
    "MCP-Protocol-Version",
    "Last-Event-ID",
]
CORS_EXPOSE_HEADERS = ["Mcp-Session-Id"]

_PROCESS_START = time.monotonic()


def _env_list(name: str) -> List[str]:
    raw = os.environ.get(name)
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


class SessionCapMiddleware:
    """
    Enforce a `max_sessions` concurrent-session cap on the Streamable HTTP
    mount, returning a `429` JSON-RPC error once at capacity — mirroring the
    cap the TS SDK enforces manually in `StreamableHttpTransport.handleMcpRequest`.

    `StreamableHTTPSessionManager` doesn't expose a public session count or a
    session-created/closed hook, so this middleware tracks session ids itself
    by observing the `mcp-session-id` request header (existing sessions) and
    the `Mcp-Session-Id` response header (newly created sessions), and prunes
    entries locally after `session_idle_timeout` so the count self-heals even
    if a client disconnects without sending `DELETE`.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_sessions: Optional[int],
        session_idle_timeout: Optional[float] = None,
    ) -> None:
        self.app = app
        self.max_sessions = max_sessions
        self.session_idle_timeout = session_idle_timeout
        self._sessions: Dict[str, float] = {}

    def _prune_stale(self) -> None:
        if not self.session_idle_timeout:
            return
        cutoff = time.monotonic() - self.session_idle_timeout
        for sid in [s for s, seen in self._sessions.items() if seen < cutoff]:
            self._sessions.pop(sid, None)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.max_sessions:
            await self.app(scope, receive, send)
            return

        self._prune_stale()

        headers = dict(scope.get("headers") or [])
        raw_session_id = headers.get(b"mcp-session-id")
        session_id = raw_session_id.decode() if raw_session_id else None
        is_known = session_id is not None and session_id in self._sessions

        if not is_known and len(self._sessions) >= self.max_sessions:
            response = JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32000,
                        "message": "Too many sessions: server at capacity, retry later",
                    },
                    "id": None,
                },
                status_code=429,
            )
            await response(scope, receive, send)
            return

        if is_known:
            self._sessions[session_id] = time.monotonic()

        new_session_id: Dict[str, Optional[str]] = {"value": None}

        async def send_wrapper(message: Any) -> None:
            if message["type"] == "http.response.start":
                for key, value in message.get("headers", []):
                    if key.lower() == b"mcp-session-id":
                        new_session_id["value"] = value.decode()
            await send(message)

        await self.app(scope, receive, send_wrapper)

        if new_session_id["value"]:
            self._sessions[new_session_id["value"]] = time.monotonic()

        if scope.get("method") == "DELETE" and session_id:
            self._sessions.pop(session_id, None)

    @property
    def active_session_count(self) -> int:
        self._prune_stale()
        return len(self._sessions)


def build_http_app(
    mcp_app: "McpApplication",
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    max_sessions: Optional[int] = None,
    session_idle_timeout: Optional[float] = None,
    enable_cors: bool = True,
    stateless: bool = False,
) -> Starlette:
    """
    Build the Starlette app exposing NitroStack's owned low-level server over
    Streamable HTTP (`/mcp`), legacy SSE (`/sse` + `/mcp/messages/`), and a
    health check (`/mcp/health`).

    Args:
        mcp_app: The bootstrapped `McpApplication` whose `mcp_server` (and
            registered tools/resources/prompts) this app serves.
        endpoint: Streamable HTTP mount path (default `/mcp`).
        max_sessions: Optional concurrent-session cap; `None`/`0` disables the cap.
        session_idle_timeout: Optional idle timeout in seconds for stateful
            sessions (ignored when `stateless=True`).
        enable_cors: Whether to add permissive CORS headers (default `True`,
            matching the TS SDK's default). When `False`, DNS-rebinding
            protection (Origin/Host validation) is enabled instead, configured
            via `MCP_ALLOWED_HOSTS`/`MCP_ALLOWED_ORIGINS` env vars.
        stateless: When `True`, every request gets a fresh transport with no
            session id and no session tracking (see `StreamableHTTPSessionManager`).
            This is the primitive the `2026-07-28` stateless MCP spec needs;
            exposed here as a config knob so adopting that spec later doesn't
            require touching this wiring again.
    """
    security_settings = None
    if not enable_cors:
        allowed_hosts = _env_list("MCP_ALLOWED_HOSTS") or ["localhost:*", "127.0.0.1:*"]
        allowed_origins = _env_list("MCP_ALLOWED_ORIGINS")
        security_settings = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
        )

    session_manager = StreamableHTTPSessionManager(
        app=mcp_app.mcp_server,
        stateless=stateless,
        session_idle_timeout=None if stateless else session_idle_timeout,
        security_settings=security_settings,
    )
    # Trailing slash is required: Starlette's Mount("/mcp/messages") only matches
    # "/mcp/messages/" (or deeper), NOT bare "/mcp/messages". Without the slash the
    # endpoint event points at a path that falls through to Mount("/mcp") (Streamable
    # HTTP), which then 406s SSE clients that don't send Streamable Accept headers.
    # Matches the mcp SDK's own SseServerTransport example ("/messages/").
    sse_messages_path = f"{endpoint.rstrip('/')}/messages/"
    sse_transport = SseServerTransport(sse_messages_path)

    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    mcp_asgi_app: ASGIApp = handle_streamable_http
    session_cap: Optional[SessionCapMiddleware] = None
    if max_sessions and not stateless:
        session_cap = SessionCapMiddleware(
            mcp_asgi_app, max_sessions=max_sessions, session_idle_timeout=session_idle_timeout
        )
        mcp_asgi_app = session_cap

    async def handle_sse(request):
        async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
            await mcp_app.mcp_server.run(streams[0], streams[1], mcp_app.mcp_server.create_initialization_options())
        return Response()

    async def health_check(request):
        return JSONResponse(
            {
                "status": "ok",
                "transport": "streamable-http",
                "protocolVersion": "2025-06-18",
                "stateless": stateless,
                "sessions": session_cap.active_session_count if session_cap else None,
                "uptimeSeconds": round(time.monotonic() - _PROCESS_START, 2),
            }
        )

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with session_manager.run():
            logger.info(
                "StreamableHTTP session manager started (stateless=%s, max_sessions=%s, "
                "session_idle_timeout=%s)",
                stateless,
                max_sessions,
                session_idle_timeout,
            )
            yield

    routes = [
        # More specific paths MUST come before the catch-all `Mount(endpoint, ...)`
        # below — Starlette matches routes in order, and a `Mount` matches any
        # path under its prefix, so `/mcp/health` would otherwise be swallowed
        # by the `/mcp` mount before ever reaching the health route.
        Route(f"{endpoint}/health", endpoint=health_check, methods=["GET"]),
        Mount(sse_messages_path, app=sse_transport.handle_post_message),
        # `handle_streamable_http`/`sse_transport.handle_post_message` are raw
        # ASGI apps (scope, receive, send), so they must be `Mount`ed rather
        # than used as `Route` endpoints (which expect `Request -> Response`).
        Mount(endpoint, app=mcp_asgi_app),
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
    ]

    middleware = []
    if enable_cors:
        middleware.append(
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                allow_headers=CORS_ALLOW_HEADERS,
                expose_headers=CORS_EXPOSE_HEADERS,
            )
        )

    return Starlette(routes=routes, middleware=middleware, lifespan=lifespan)
