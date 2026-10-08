"""A token bucket: a rate limit that allows short bursts."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Bucket:
    """`rate` tokens a second, holding at most `burst` of them."""

    rate: float
    burst: float
    tokens: float = field(init=False)
    stamp: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = self.burst
        self.stamp = time.monotonic()

    def take(self, cost: float = 1.0) -> bool:
        """Spend `cost` tokens if they are there. Never waits."""
        now = time.monotonic()
        self.tokens = min(self.burst, self.tokens + (now - self.stamp) * self.rate)
        self.stamp = now
        if self.tokens < cost:
            return False
        self.tokens -= cost
        return True
