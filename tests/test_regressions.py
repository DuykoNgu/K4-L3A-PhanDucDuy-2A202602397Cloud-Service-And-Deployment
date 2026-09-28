"""Kiểm tra quota khi các request đồng thời có cùng timestamp."""

from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException
from redis import Redis

from app.rate_limiter import RateLimiter


def test_parallel_requests_share_one_quota(fake_redis: Redis) -> None:
    limiter = RateLimiter(fake_redis, limit_per_minute=3)

    def request(_index: int) -> bool:
        try:
            limiter.check("parallel-user", now=1000.0)
        except HTTPException as error:
            if error.status_code != 429:
                raise
            return False
        return True

    with ThreadPoolExecutor(max_workers=8) as pool:
        accepted = list(pool.map(request, range(32)))
    assert sum(accepted) == 3
