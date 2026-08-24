"""Phase 6 — EventEmitter and @on_event (Python-only)."""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack.events.event_emitter import EventEmitter, on_event


def setup_function() -> None:
    EventEmitter.reset()


def teardown_function() -> None:
    EventEmitter.reset()


def test_on_event_registers_listener_and_emit_invokes_bound_method():
    seen = []

    class Listener:
        @on_event("order.created")
        async def handle(self, payload):
            seen.append(payload)

    emitter = EventEmitter.get_instance()
    emitter.bind_instance("order.created", Listener.handle, Listener())
    asyncio.run(emitter.emit("order.created", {"id": 9}))
    assert seen == [{"id": 9}]


def test_emit_swallows_handler_errors():
    class Broken:
        @on_event("x")
        def handle(self, payload):
            raise RuntimeError("listener boom")

    emitter = EventEmitter.get_instance()
    emitter.bind_instance("x", Broken.handle, Broken())
    asyncio.run(emitter.emit("x", {}))


def test_on_off_once_and_counts():
    emitter = EventEmitter.get_instance()
    seen = []

    def keep(payload):
        seen.append(("keep", payload))

    def once_fn(payload):
        seen.append(("once", payload))

    emitter.on("ping", keep)
    emitter.once("ping", once_fn)
    assert emitter.listener_count("ping") == 2
    assert "ping" in emitter.event_names()

    asyncio.run(emitter.emit("ping", 1))
    asyncio.run(emitter.emit("ping", 2))
    assert seen == [("keep", 1), ("once", 1), ("keep", 2)]

    emitter.off("ping", keep)
    asyncio.run(emitter.emit("ping", 3))
    assert ("keep", 3) not in seen

    emitter.on("other", keep)
    emitter.remove_all_listeners("other")
    assert emitter.listener_count("other") == 0
    emitter.remove_all_listeners()
    assert emitter.event_names() == []


def test_emit_sync_and_no_listeners():
    emitter = EventEmitter.get_instance()
    seen = []
    emitter.on("sync", lambda payload: seen.append(payload))
    emitter.emit_sync("sync", "ok")
    assert seen == ["ok"]
    asyncio.run(emitter.emit("missing", None))
    emitter.emit_sync("missing", None)
