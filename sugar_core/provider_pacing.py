"""Process-wide request pacing shared by concurrent provider collectors."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable


class SharedRequestPacer:
    """Space collector request starts and share provider 429 cooldowns.

    The gate is intentionally process-wide: independent platform collectors
    still run concurrently, while their request starts share one conservative
    pacing interval and any active rate-limit cooldown.
    """

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._next_request_at = 0.0
        self._cooldown_until = 0.0

    def acquire(
        self,
        *,
        interval_seconds: float = 0.2,
        cancelled: Callable[[], bool] | None = None,
    ) -> bool:
        interval = min(60.0, max(0.0, float(interval_seconds)))
        with self._condition:
            while True:
                if cancelled is not None and cancelled():
                    return False
                now = time.monotonic()
                ready_at = max(self._next_request_at, self._cooldown_until)
                wait = ready_at - now
                if wait <= 0:
                    self._next_request_at = now + interval
                    return True
                self._condition.wait(timeout=min(wait, 0.25))

    def defer(self, seconds: float) -> None:
        delay = min(3600.0, max(0.0, float(seconds)))
        with self._condition:
            self._cooldown_until = max(self._cooldown_until, time.monotonic() + delay)
            self._condition.notify_all()


SHARED_REQUEST_PACER = SharedRequestPacer()
