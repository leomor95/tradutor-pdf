from __future__ import annotations

from collections import deque


def format_eta(seconds: float | None) -> str:
    """Format remaining time in seconds to a human-readable pt-BR string."""
    if seconds is None:
        return ""
    if seconds <= 0:
        return "concluído"

    total_secs = round(seconds)
    if total_secs < 60:
        return f"~{max(1, total_secs)} s"

    minutes = total_secs // 60
    secs = total_secs % 60
    if minutes < 60:
        if secs > 0:
            return f"~{minutes} min {secs} s"
        return f"~{minutes} min"

    hours = total_secs // 3600
    rem_min = (total_secs % 3600) // 60
    if rem_min > 0:
        return f"~{hours} h {rem_min} min"
    return f"~{hours} h"


class MovingAverageEstimator:
    """Estimates remaining time using a moving average over recent item durations."""

    def __init__(self, window_size: int = 10) -> None:
        self.window_size = max(1, window_size)
        self.durations: deque[float] = deque(maxlen=self.window_size)

    def record(self, duration: float) -> None:
        """Record the duration of a completed item in seconds."""
        if duration > 0:
            self.durations.append(duration)

    @property
    def average_duration(self) -> float | None:
        """Return the average duration in seconds, or None if no items recorded."""
        if not self.durations:
            return None
        return sum(self.durations) / len(self.durations)

    def estimate_remaining(self, remaining_count: int) -> float | None:
        """Estimate remaining seconds for the given number of remaining items."""
        if remaining_count <= 0:
            return 0.0
        avg = self.average_duration
        if avg is None:
            return None
        return remaining_count * avg
