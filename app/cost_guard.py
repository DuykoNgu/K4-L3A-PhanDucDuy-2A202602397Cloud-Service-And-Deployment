"""Chi tiêu theo user/tháng UTC, lưu trong Redis."""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from redis import Redis

KEY_TTL_SECONDS = 40 * 24 * 3600


class CostGuard:
    def __init__(self, client: Redis, monthly_budget_usd: float) -> None:
        self.client = client
        self.budget = monthly_budget_usd

    @staticmethod
    def current_month() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    @classmethod
    def _key(cls, user_id: str, month: str | None = None) -> str:
        return f"cost:{user_id}:{month or cls.current_month()}"

    def spent(self, user_id: str, month: str | None = None) -> float:
        return float(self.client.get(self._key(user_id, month)) or 0.0)

    def check(
        self,
        user_id: str,
        estimated_cost: float = 0.0,
        month: str | None = None,
    ) -> None:
        if self.spent(user_id, month) + estimated_cost > self.budget:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="monthly budget exceeded",
            )

    def record(self, user_id: str, cost: float, month: str | None = None) -> float:
        key = self._key(user_id, month)
        with self.client.pipeline() as pipe:
            pipe.incrbyfloat(key, cost)
            pipe.expire(key, KEY_TTL_SECONDS)
            return float(pipe.execute()[0])
