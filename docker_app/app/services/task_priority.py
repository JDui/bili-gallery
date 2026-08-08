from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Iterator


FOREGROUND = "foreground"
BACKGROUND = "background"


def classify_request(method: str, path: str, query_string: bytes = b"") -> str:
    """Classify interactive reads as foreground work and mutations as background work."""
    normalized_method = method.upper()
    if normalized_method == "POST" and path == "/api/sidebar-counts/refresh":
        return FOREGROUND
    if normalized_method not in {"GET", "HEAD"}:
        return BACKGROUND
    if path == "/api/duplicates/items" and b"force=true" in query_string.lower():
        return BACKGROUND
    return FOREGROUND


class TaskPriorityCoordinator:
    """Cooperatively pauses background work while foreground requests are active."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._active_foreground = 0
        self._waiting_background = 0
        self._background_wait_count = 0
        self._background_wait_seconds = 0.0

    @contextmanager
    def foreground(self) -> Iterator[None]:
        with self._condition:
            self._active_foreground += 1
            self._condition.notify_all()
        try:
            yield
        finally:
            with self._condition:
                self._active_foreground = max(0, self._active_foreground - 1)
                self._condition.notify_all()

    def background_checkpoint(self) -> float:
        started_at = time.monotonic()
        waited = False
        with self._condition:
            if self._active_foreground:
                waited = True
                self._waiting_background += 1
                try:
                    while self._active_foreground:
                        self._condition.wait(timeout=0.05)
                finally:
                    self._waiting_background = max(0, self._waiting_background - 1)
            elapsed = time.monotonic() - started_at
            if waited:
                self._background_wait_count += 1
                self._background_wait_seconds += elapsed
            return elapsed if waited else 0.0

    def snapshot(self) -> dict[str, int | float | bool]:
        with self._condition:
            return {
                "foreground_active": self._active_foreground,
                "background_waiting": self._waiting_background,
                "foreground_has_priority": True,
                "background_wait_count": self._background_wait_count,
                "background_wait_seconds": round(self._background_wait_seconds, 3),
            }


class TaskPriorityMiddleware:
    def __init__(self, app, coordinator: TaskPriorityCoordinator) -> None:
        self.app = app
        self.coordinator = coordinator

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        priority = classify_request(
            str(scope.get("method") or "GET"),
            str(scope.get("path") or ""),
            bytes(scope.get("query_string") or b""),
        )

        async def send_with_priority(message) -> None:
            if message.get("type") == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"x-task-priority", priority.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        if priority == FOREGROUND:
            with self.coordinator.foreground():
                await self.app(scope, receive, send_with_priority)
            return
        await self.app(scope, receive, send_with_priority)
