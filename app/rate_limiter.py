"""Sliding window 60 giây với quota dùng chung giữa các instance."""

import time
import uuid

from fastapi import HTTPException, status
from redis import Redis, WatchError

WINDOW_SECONDS = 60


class RateLimiter:
    def __init__(self, client: Redis, limit_per_minute: int) -> None:
        self.client = client
        self.limit = limit_per_minute

    @staticmethod
    def _key(user_id: str) -> str:
        return f"ratelimit:{user_id}"

    def hit_count(self, user_id: str, now: float | None = None) -> int:
        now = time.time() if now is None else now
        with self.client.pipeline() as pipe:
            pipe.zremrangebyscore(self._key(user_id), "-inf", now - WINDOW_SECONDS)
            pipe.zcard(self._key(user_id))
            return int(pipe.execute()[-1])

    def check(self, user_id: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        key = self._key(user_id)
        with self.client.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(key)
                    count = pipe.zcount(key, f"({now - WINDOW_SECONDS}", "+inf")
                    if count >= self.limit:
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="rate limit exceeded",
                            headers={"Retry-After": str(WINDOW_SECONDS)},
                        )
                    pipe.multi()
                    pipe.zremrangebyscore(key, "-inf", now - WINDOW_SECONDS)
                    pipe.zadd(key, {f"{now}:{uuid.uuid4().hex}": now})
                    pipe.expire(key, WINDOW_SECONDS)
                    pipe.execute()
                    return
                except WatchError:
                    continue
