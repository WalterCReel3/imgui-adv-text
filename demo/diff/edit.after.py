"""Retry a flaky call a bounded number of times."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

DEFAULT_ATTEMPTS = 3
BASE_DELAY = 0.25


class GaveUp(RuntimeError):
    """Every attempt failed; the last error is the cause."""


def delays(attempts: int, base: float = BASE_DELAY) -> list[float]:
    """The wait before each retry: doubling, starting at `base`."""
    return [base * 2**n for n in range(attempts - 1)]


def retry(call: Callable[[], T], attempts: int = DEFAULT_ATTEMPTS) -> T:
    """Call `call` until it returns, at most `attempts` times."""
    waits = delays(attempts)
    for attempt in range(attempts):
        try:
            return call()
        except Exception as error:
            if attempt == attempts - 1:
                raise GaveUp(f"gave up after {attempts} attempts") from error
            # Jitter, so that a fleet of clients does not retry in step.
            time.sleep(jittered(waits[attempt]))
    raise AssertionError("unreachable")


def jittered(wait: float, spread: float = 0.1) -> float:
    """`wait`, moved by up to `spread` of itself either way."""
    return wait * (1.0 + random.uniform(-spread, spread))


def describe(attempts: int) -> str:
    """One line for a log: how long the whole thing may take."""
    total = sum(delays(attempts))
    return f"up to {attempts} attempts over {total:.2f}s"
