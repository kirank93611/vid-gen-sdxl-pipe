"""
Per-API-key sliding-window rate limiting (in-process).

Used before GPU work on /generate, /jobs, and /inpaint to fail fast with 429.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

import api_config

_lock = threading.Lock()
_by_key: dict[str, "KeyRateState"] = {}


@dataclass
class KeyRateState:
    request_timestamps: deque[float] = field(default_factory=deque)


def check_and_record_rate_limit(api_key: str) -> bool:
    """
    Return True if the request is allowed and record it; False if rate limited.
    """
    now = time.monotonic()
    with _lock:
        state = _by_key.setdefault(api_key, KeyRateState())
        window_start = now - api_config.RATE_LIMIT_WINDOW_SECONDS
        while state.request_timestamps and state.request_timestamps[0] < window_start:
            state.request_timestamps.popleft()
        if len(state.request_timestamps) >= api_config.RATE_LIMIT_REQUESTS:
            return False
        state.request_timestamps.append(now)
        return True


def reset_for_tests() -> None:
    """Clear in-memory state between integration tests."""
    with _lock:
        _by_key.clear()
