from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class LoginAttempt:
    failures: int = 0
    locked_until: float = 0
    window_started_at: float = 0


class LoginAttemptLimiter:
    def __init__(self, max_failures: int = 5, lock_seconds: int = 15 * 60) -> None:
        self.max_failures = max_failures
        self.lock_seconds = lock_seconds
        self._attempts: dict[str, LoginAttempt] = {}

    def is_locked(self, key: str) -> bool:
        attempt = self._attempts.get(key)
        return bool(attempt and attempt.locked_until > time.time())

    def record_failure(self, key: str) -> None:
        now = time.time()
        attempt = self._attempts.setdefault(key, LoginAttempt(window_started_at=now))
        if now - attempt.window_started_at > self.lock_seconds:
            attempt.failures = 0
            attempt.window_started_at = now
        attempt.failures += 1
        if attempt.failures >= self.max_failures:
            attempt.locked_until = now + self.lock_seconds

    def record_success(self, key: str) -> None:
        self._attempts.pop(key, None)


login_attempt_limiter = LoginAttemptLimiter()
