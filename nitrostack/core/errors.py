from typing import Any


class ToolExecutionError(Exception):
    """Raised when tool execution fails."""
    pass

class ValidationError(Exception):
    """Raised when inputs or outputs fail schema validation."""
    pass

class ResourceNotFoundError(Exception):
    """Raised when a requested resource is not found."""
    pass

class PromptNotFoundError(Exception):
    """Raised when a requested prompt template is not found."""
    pass

class DIError(Exception):
    """Base class for dependency injection errors."""
    pass

class DependencyResolutionError(DIError):
    """Raised when a dependency cannot be resolved by the DI container."""
    pass

class ConfigurationError(Exception):
    """Raised when configuration validation fails."""
    pass


class TaskNotFoundError(Exception):
    """Raised when a task ID is not present in the TaskManager store."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"Task {task_id} not found")


class TaskAlreadyTerminalError(Exception):
    """Raised when an operation is attempted on a task that is already terminal."""

    def __init__(self, task_id: str, status: Any):
        self.task_id = task_id
        self.status = status
        status_value = getattr(status, "value", status)
        super().__init__(
            f"Cannot modify task {task_id}: already in terminal status '{status_value}'"
        )


class InvalidTaskTransitionError(Exception):
    """Raised when a requested task status transition is not allowed."""

    def __init__(self, from_status: Any, to_status: Any):
        self.from_status = from_status
        self.to_status = to_status
        from_value = getattr(from_status, "value", from_status)
        to_value = getattr(to_status, "value", to_status)
        super().__init__(
            f"Invalid task status transition: {from_value} → {to_value}"
        )


class TaskExpiredError(Exception):
    """Raised when a task has expired (TTL elapsed) and cannot be used further."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"Task {task_id} has expired")


class TaskCancelledError(Exception):
    """Raised when an MCP background task has been cancelled."""

    def __init__(self, task_id: str | None = None, message: str | None = None):
        self.task_id = task_id
        if message is not None:
            super().__init__(message)
        elif task_id is not None:
            super().__init__(f"Task {task_id} has been cancelled.")
        else:
            super().__init__("Task has been cancelled.")
