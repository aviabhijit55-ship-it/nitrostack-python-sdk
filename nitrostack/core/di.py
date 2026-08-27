from typing import Any, Dict, List, Type, Union

class DIContainer:
    _instance = None

    @classmethod
    def get_instance(cls) -> "DIContainer":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton container (useful for testing)."""
        cls._instance = None

    def __init__(self):
        self._registry: Dict[Any, Type] = {}
        self._instances: Dict[Any, Any] = {}
        # List (not set) so the circular-dependency error reports the chain in order.
        self._resolving: list = []

    def register(self, cls: Type) -> None:
        """Register a provider class."""
        self._registry[cls] = cls

    def register_value(self, token: Any, value: Any) -> None:
        """Register a constant value or instantiated service with a token."""
        self._instances[token] = value
        # Also map token to its type if possible
        if not isinstance(token, str):
            self._registry[token] = type(value)

    def has_value(self, token: Any) -> bool:
        """True when ``register_value`` stored an instance for this token.

        Unlike ``resolve``, this does not auto-instantiate unregistered classes.
        """
        return token in self._instances

    def resolve(self, token: Any) -> Any:
        """
        Resolve a dependency by token (class type or string key).
        Instantiates classes if not already instantiated.
        """
        # 1. Check if we already have a cached instance
        if token in self._instances:
            return self._instances[token]

        # 2. Check if the token is registered as a class
        cls = self._registry.get(token)
        
        # 3. If not registered, but it's a class type, check if it's decorated with @injectable
        if cls is None and isinstance(token, type):
            cls = token
            # We auto-register it to make usage easier
            self.register(cls)

        from nitrostack.core.errors import DependencyResolutionError

        if cls is None:
            raise DependencyResolutionError(f"Dependency '{token}' is not registered in the DIContainer.")

        cycle_key = cls
        if cycle_key in self._resolving:
            chain = " -> ".join(getattr(item, "__name__", str(item)) for item in (*self._resolving, cycle_key))
            raise DependencyResolutionError(f"Circular dependency detected: {chain}")

        # 4. Resolve dependencies of the class
        deps = getattr(cls, "_mcp_deps", [])
        resolved_args = []
        self._resolving.append(cycle_key)
        try:
            for dep in deps:
                resolved_args.append(self.resolve(dep))
            instance = cls(*resolved_args)
        except DependencyResolutionError:
            raise
        except Exception as e:
            raise DependencyResolutionError(f"Failed to instantiate class '{cls.__name__}' due to: {e}") from e
        finally:
            self._resolving.remove(cycle_key)

        # 6. Cache and return the singleton instance
        self._instances[token] = instance
        return instance

def injectable(deps: List[Any] = None):
    """
    Decorator to mark a class as Injectable.
    Requires explicit list of dependencies.
    """
    if deps is None:
        deps = []
    def decorator(cls: Type):
        cls._mcp_deps = deps
        # Automatically register with the DIContainer
        DIContainer.get_instance().register(cls)
        return cls
    return decorator
