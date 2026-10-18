"""One process-wide budget per Gemini instance; quota errors stop all optional AI calls."""

import asyncio
import time
from collections import deque
from datetime import datetime, timezone


class AIBudget:
    def __init__(self, settings):
        self.settings = settings
        self.lock = asyncio.Lock()
        self.calls = deque()
        self.day = None
        self.count = 0
        self.blocked_until = 0

    async def acquire(self, optional=False):
        from .generate import AIError
        async with self.lock:
            now = time.monotonic()
            day = datetime.now(timezone.utc).date()
            if self.day != day:
                self.day, self.count = day, 0
            while self.calls and self.calls[0] <= now - 60:
                self.calls.popleft()
            if now < self.blocked_until:
                raise AIError("provider_cooldown")
            per_min = max(0, self.settings.ai_requests_per_minute - (2 if optional else 0))
            per_day = max(0, self.settings.ai_requests_per_day - (
                self.settings.photo_ai_reserved_requests if optional else 0))
            if len(self.calls) >= per_min or self.count >= per_day:
                raise AIError("ai_local_limit")
            self.calls.append(now)
            self.count += 1

    def rate_limited(self):
        self.blocked_until = max(self.blocked_until, time.monotonic() + 60)
