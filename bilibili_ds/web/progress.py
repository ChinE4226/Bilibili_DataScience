"""Process-local progress reporting for browser requests."""

from __future__ import annotations

from bilibili_ds.web import state


def set_progress(message: str, *, running: bool | None = None, percent: int | None = None, count: int | None = None) -> None:
    if running is not None:
        state.PROGRESS["running"] = running
    state.PROGRESS["message"] = message
    if percent is not None:
        state.PROGRESS["percent"] = max(0, min(100, percent))
    if count is not None:
        state.PROGRESS["count"] = count
