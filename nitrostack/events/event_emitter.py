import inspect
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple


class EventEmitter:
    _instance = None

    @classmethod
    def get_instance(cls) -> "EventEmitter":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def __init__(self):
        # Maps event_name -> list of (unbound_func, class_type)
        self._listeners: Dict[str, List[Tuple[Callable, Optional[Any]]]] = {}
        # Maps event_name -> list of bound_callables
        self._bound_listeners: Dict[str, List[Callable]] = {}

    def register_listener(self, event_name: str, func: Callable, class_type: Optional[Any] = None) -> None:
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        self._listeners[event_name].append((func, class_type))

    def bind_instance(self, event_name: str, func: Callable, instance: Any) -> None:
        if event_name not in self._bound_listeners:
            self._bound_listeners[event_name] = []

        bound_func = func.__get__(instance, type(instance))
        self._bound_listeners[event_name].append(bound_func)

    def on(self, event_name: str, listener: Callable) -> None:
        self._bound_listeners.setdefault(event_name, []).append(listener)

    def off(self, event_name: str, listener: Callable) -> None:
        bound = self._bound_listeners.get(event_name)
        if not bound:
            return
        self._bound_listeners[event_name] = [item for item in bound if item is not listener]

    def once(self, event_name: str, listener: Callable) -> Callable:
        def wrapper(payload: Any):
            self.off(event_name, wrapper)
            return listener(payload)

        self.on(event_name, wrapper)
        return wrapper

    def listener_count(self, event_name: str) -> int:
        return len(self._bound_listeners.get(event_name, []))

    def event_names(self) -> List[str]:
        return [name for name, items in self._bound_listeners.items() if items]

    def remove_all_listeners(self, event_name: Optional[str] = None) -> None:
        if event_name is None:
            self._bound_listeners.clear()
            return
        self._bound_listeners.pop(event_name, None)

    async def emit(self, event_name: str, payload: Any) -> None:
        listeners = list(self._bound_listeners.get(event_name, []))
        for listener in listeners:
            try:
                result = listener(payload)
                if inspect.iscoroutine(result):
                    await result
            except Exception as e:
                sys.stderr.write(f"Event emitter error: handler for '{event_name}' failed: {e}\n")
                sys.stderr.flush()

    def emit_sync(self, event_name: str, payload: Any) -> None:
        listeners = list(self._bound_listeners.get(event_name, []))
        for listener in listeners:
            try:
                result = listener(payload)
                if inspect.iscoroutine(result):
                    result.close()
                    sys.stderr.write(
                        f"Event emitter warning: async handler for '{event_name}' "
                        "cannot run inside emit_sync; use 'await emit()' instead\n"
                    )
                    sys.stderr.flush()
            except Exception as e:
                sys.stderr.write(f"Event emitter error: handler for '{event_name}' failed: {e}\n")
                sys.stderr.flush()


def on_event(event_name: str):
    """
    Decorator to mark a service or controller method as an event listener.
    """
    def decorator(func: Callable):
        func._mcp_event_name = event_name
        EventEmitter.get_instance().register_listener(event_name, func)
        return func
    return decorator
