from __future__ import annotations

import threading

from app.services.task_priority import BACKGROUND, FOREGROUND, TaskPriorityCoordinator, classify_request


def test_request_classification_prioritizes_content_loading() -> None:
    assert classify_request("GET", "/api/gallery/items") == FOREGROUND
    assert classify_request("GET", "/storage/data/images/demo.webp") == FOREGROUND
    assert classify_request("GET", "/api/duplicates/items", b"force=false") == FOREGROUND
    assert classify_request("GET", "/api/duplicates/items", b"force=true") == BACKGROUND
    assert classify_request("POST", "/api/sidebar-counts/refresh") == FOREGROUND
    assert classify_request("POST", "/api/pull/run") == BACKGROUND
    assert classify_request("DELETE", "/api/subscriptions/42") == BACKGROUND


def test_background_checkpoint_waits_for_foreground_request() -> None:
    coordinator = TaskPriorityCoordinator()
    checkpoint_started = threading.Event()
    checkpoint_finished = threading.Event()

    def background_work() -> None:
        checkpoint_started.set()
        coordinator.background_checkpoint()
        checkpoint_finished.set()

    with coordinator.foreground():
        thread = threading.Thread(target=background_work)
        thread.start()
        assert checkpoint_started.wait(timeout=1)
        assert not checkpoint_finished.wait(timeout=0.05)
        snapshot = coordinator.snapshot()
        assert snapshot["foreground_active"] == 1
        assert snapshot["background_waiting"] == 1

    thread.join(timeout=1)
    assert checkpoint_finished.is_set()
    snapshot = coordinator.snapshot()
    assert snapshot["foreground_active"] == 0
    assert snapshot["background_waiting"] == 0
    assert snapshot["background_wait_count"] == 1
