"""
MCP Task state machine (Phase 1).

Validated in-memory task store used by McpApplication for MCP Tasks.

State machine (ASCII)::

    [*] --> WORKING
    WORKING --> COMPLETED
    WORKING --> FAILED
    WORKING --> CANCELLED
    WORKING --> EXPIRED   (lazy TTL check-on-read)
    COMPLETED / FAILED / CANCELLED / EXPIRED are terminal — no further transitions

TTL: optional ``ttl_seconds`` sets ``expires_at``. Expiration is evaluated lazily
on read/mutate (no background thread). An expired non-terminal task is transitioned
to ``EXPIRED``.
"""

from __future__ import annotations

import asyncio
import datetime
import uuid
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Dict, List, Optional

from nitrostack.core.errors import (
    InvalidTaskTransitionError,
    TaskAlreadyTerminalError,
    TaskExpiredError,
    TaskNotFoundError,
)


class TaskStatus(Enum):
    """Task lifecycle statuses required by Phase 1."""

    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


TERMINAL_STATUSES = frozenset(
    {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.EXPIRED,
    }
)


def is_terminal_status(status: TaskStatus) -> bool:
    """Return True if ``status`` allows no further transitions."""
    return status in TERMINAL_STATUSES


@dataclass
class TaskData:
    """
    Snapshot of a task's protocol-visible and result state.

    ``progress`` holds the latest progress/status message. ``result`` / ``error``
    are populated on successful completion or failure respectively. Tasks created
    without a TTL have ``expires_at is None`` and never expire.

    Compatibility aliases (``task_id``, ``status_message``, ``ttl``) mirror the
    previous task-entry attribute names used by the public ``TaskRegistry`` API.
    """

    id: str
    status: TaskStatus
    progress: Optional[str] = None
    result: Any = None
    error: Any = None
    created_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    expires_at: Optional[datetime.datetime] = None
    last_updated_at: Optional[datetime.datetime] = None
    ttl_seconds: Optional[int] = None
    poll_interval: int = 5

    def __post_init__(self) -> None:
        if self.last_updated_at is None:
            self.last_updated_at = self.created_at

    @property
    def task_id(self) -> str:
        return self.id

    @property
    def status_message(self) -> Optional[str]:
        return self.progress

    @property
    def ttl(self) -> Optional[int]:
        return self.ttl_seconds


@dataclass
class _TaskEntry:
    """Internal store entry (not part of the public API)."""

    data: TaskData
    done_event: asyncio.Event = field(default_factory=asyncio.Event)


class TaskManager:
    """
    In-memory task store with validated transitions, result storage, and lazy TTL.

    Typical flow::

        manager = TaskManager()
        task = manager.create_task(ttl_seconds=60)
        manager.update_progress(task.id, "halfway")
        manager.complete_task(task.id, {"ok": True})
        assert manager.get_task(task.id).result == {"ok": True}
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, _TaskEntry] = {}

    def create_task(
        self,
        ttl_seconds: Optional[int] = None,
        *,
        task_id: Optional[str] = None,
    ) -> TaskData:
        """
        Create a new task in ``WORKING`` status.

        ``ttl_seconds=None`` means the task never expires. ``task_id`` is optional
        and intended for compatibility callers that supply their own ID.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        resolved_id = task_id or f"task_{uuid.uuid4().hex[:12]}"
        if resolved_id in self._tasks:
            raise ValueError(f"Task {resolved_id} already exists")
        expires_at = None
        if ttl_seconds is not None:
            expires_at = now + datetime.timedelta(seconds=ttl_seconds)

        data = TaskData(
            id=resolved_id,
            status=TaskStatus.WORKING,
            progress="Task started",
            created_at=now,
            last_updated_at=now,
            expires_at=expires_at,
            ttl_seconds=ttl_seconds,
            poll_interval=5,
        )
        self._tasks[resolved_id] = _TaskEntry(data=data)
        return self._snapshot(data)

    def get_task(self, task_id: str) -> TaskData:
        """
        Return a snapshot of the task.

        Missing IDs raise ``TaskNotFoundError``. Expired non-terminal tasks are
        lazily transitioned to ``EXPIRED`` before the snapshot is returned.
        """
        entry = self._get_entry(task_id)
        self._maybe_expire(entry)
        return self._snapshot(entry.data)

    def update_progress(self, task_id: str, progress: Any) -> None:
        """
        Update progress for a ``WORKING`` task.

        Raises ``TaskAlreadyTerminalError`` if the task is already terminal
        (including after lazy expiration).
        """
        entry = self._get_entry(task_id)
        self._maybe_expire(entry)
        if is_terminal_status(entry.data.status):
            if entry.data.status == TaskStatus.EXPIRED:
                raise TaskExpiredError(task_id)
            raise TaskAlreadyTerminalError(task_id, entry.data.status)
        entry.data.progress = progress
        entry.data.last_updated_at = datetime.datetime.now(datetime.timezone.utc)

    def complete_task(self, task_id: str, result: Any) -> None:
        """Transition ``WORKING`` → ``COMPLETED`` and store ``result``."""
        entry = self._get_entry(task_id)
        self._maybe_expire(entry)
        self._require_working_for_transition(entry, TaskStatus.COMPLETED)
        entry.data.result = result
        entry.data.error = None
        entry.data.progress = "Task completed successfully"
        self._set_status(entry, TaskStatus.COMPLETED)

    def fail_task(self, task_id: str, error: Any) -> None:
        """Transition ``WORKING`` → ``FAILED`` and store ``error``."""
        entry = self._get_entry(task_id)
        self._maybe_expire(entry)
        self._require_working_for_transition(entry, TaskStatus.FAILED)
        entry.data.error = error
        entry.data.progress = f"Task failed: {error}"
        self._set_status(entry, TaskStatus.FAILED)

    def cancel_task(self, task_id: str) -> None:
        """Transition ``WORKING`` → ``CANCELLED``."""
        entry = self._get_entry(task_id)
        self._maybe_expire(entry)
        if is_terminal_status(entry.data.status):
            if entry.data.status == TaskStatus.EXPIRED:
                raise TaskExpiredError(task_id)
            raise TaskAlreadyTerminalError(task_id, entry.data.status)
        entry.data.progress = "Task cancelled by client"
        self._set_status(entry, TaskStatus.CANCELLED)

    def list_tasks(self) -> List[TaskData]:
        """Return snapshots for all known tasks (applies lazy expiration)."""
        snapshots: List[TaskData] = []
        for entry in list(self._tasks.values()):
            self._maybe_expire(entry)
            snapshots.append(self._snapshot(entry.data))
        return snapshots

    def has_task(self, task_id: str) -> bool:
        """Return True if a task with ``task_id`` exists in the store."""
        return task_id in self._tasks

    def is_task_cancelled(self, task_id: str) -> bool:
        """Return True if the task exists and is in ``CANCELLED`` status."""
        if task_id not in self._tasks:
            return False
        entry = self._tasks[task_id]
        self._maybe_expire(entry)
        return entry.data.status == TaskStatus.CANCELLED

    async def wait_until_done(self, task_id: str) -> TaskData:
        """
        Block until the task reaches a terminal state, then return a snapshot.

        Applies lazy expiration before waiting when the task is still working.
        """
        entry = self._get_entry(task_id)
        self._maybe_expire(entry)
        if not is_terminal_status(entry.data.status):
            await entry.done_event.wait()
            # Re-fetch: status may have changed while waiting.
            entry = self._get_entry(task_id)
        return self._snapshot(entry.data)

    def get_result(self, task_id: str) -> Any:
        """
        Return the stored result for a completed task.

        Raises ``TaskNotFoundError``, ``TaskExpiredError``, or
        ``InvalidTaskTransitionError`` if the task is not completed.
        """
        data = self.get_task(task_id)
        if data.status == TaskStatus.EXPIRED:
            raise TaskExpiredError(task_id)
        if data.status != TaskStatus.COMPLETED:
            raise InvalidTaskTransitionError(data.status, TaskStatus.COMPLETED)
        return data.result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_entry(self, task_id: str) -> _TaskEntry:
        entry = self._tasks.get(task_id)
        if entry is None:
            raise TaskNotFoundError(task_id)
        return entry

    def _maybe_expire(self, entry: _TaskEntry) -> None:
        if entry.data.expires_at is None:
            return
        if is_terminal_status(entry.data.status):
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        if now >= entry.data.expires_at:
            entry.data.status = TaskStatus.EXPIRED
            entry.data.progress = "Task expired"
            entry.data.last_updated_at = now
            entry.done_event.set()

    def _require_working_for_transition(
        self, entry: _TaskEntry, to_status: TaskStatus
    ) -> None:
        current = entry.data.status
        if current == TaskStatus.EXPIRED:
            raise TaskExpiredError(entry.data.id)
        if is_terminal_status(current):
            raise TaskAlreadyTerminalError(entry.data.id, current)
        if current != TaskStatus.WORKING:
            raise InvalidTaskTransitionError(current, to_status)

    def _set_status(self, entry: _TaskEntry, status: TaskStatus) -> None:
        entry.data.status = status
        entry.data.last_updated_at = datetime.datetime.now(datetime.timezone.utc)
        if is_terminal_status(status):
            entry.done_event.set()

    @staticmethod
    def _snapshot(data: TaskData) -> TaskData:
        """Return a shallow copy so callers cannot mutate internal state."""
        return replace(data)


class TaskRegistry:
    """
    Deprecated public compatibility facade over :class:`TaskManager`.

    Prefer :class:`TaskManager` for new code. ``McpApplication`` uses a dedicated
    ``TaskManager`` instance; this facade keeps the historical classmethod API
    (``from nitrostack import TaskRegistry``) working for external callers.

    Behavioral notes vs the pre-Phase-1 registry:
    - Missing-task mutations remain no-ops (same as before).
    - Invalid transitions on existing tasks follow Phase 1 validation (may raise).
    - ``get_task`` still returns ``None`` when the ID is unknown.
    """

    _manager: TaskManager = TaskManager()

    @classmethod
    def create_task(cls, task_id: str, ttl: Optional[int] = None) -> TaskData:
        return cls._manager.create_task(ttl_seconds=ttl, task_id=task_id)

    @classmethod
    def get_task(cls, task_id: str) -> Optional[TaskData]:
        try:
            return cls._manager.get_task(task_id)
        except TaskNotFoundError:
            return None

    @classmethod
    def list_tasks(cls) -> List[TaskData]:
        return cls._manager.list_tasks()

    @classmethod
    def update_progress(cls, task_id: str, message: str) -> None:
        try:
            cls._manager.update_progress(task_id, message)
        except (TaskNotFoundError, TaskAlreadyTerminalError, TaskExpiredError):
            return

    @classmethod
    def cancel_task(cls, task_id: str) -> None:
        try:
            cls._manager.cancel_task(task_id)
        except (TaskNotFoundError, TaskAlreadyTerminalError, TaskExpiredError):
            return

    @classmethod
    def is_task_cancelled(cls, task_id: str) -> bool:
        return cls._manager.is_task_cancelled(task_id)

    @classmethod
    def complete_task(cls, task_id: str, result: Any) -> None:
        try:
            cls._manager.complete_task(task_id, result)
        except (TaskNotFoundError, TaskAlreadyTerminalError, TaskExpiredError, InvalidTaskTransitionError):
            return

    @classmethod
    def fail_task(cls, task_id: str, error: Any) -> None:
        try:
            cls._manager.fail_task(task_id, error)
        except (TaskNotFoundError, TaskAlreadyTerminalError, TaskExpiredError, InvalidTaskTransitionError):
            return
