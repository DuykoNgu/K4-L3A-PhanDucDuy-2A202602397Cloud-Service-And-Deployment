"""Lịch sử hội thoại dùng chung qua Redis, giới hạn độ dài và thời gian lưu."""

import json

import redis

from .config import get_settings
from .logging_utils import log_event

HISTORY_MAX_MESSAGES = 20
HISTORY_TTL_SECONDS = 7 * 24 * 3600


def get_redis_client(url: str | None = None) -> redis.Redis:
    url = url or get_settings().redis_url
    if url.startswith("fake://"):
        import fakeredis

        return fakeredis.FakeRedis(decode_responses=True)
    return redis.from_url(
        url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3
    )


class ConversationStore:
    def __init__(self, client: redis.Redis) -> None:
        self.client = client

    @staticmethod
    def _key(user_id: str) -> str:
        return f"history:{user_id}"

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except Exception as error:
            log_event(
                "redis_unavailable", level="error", error_type=type(error).__name__
            )
            return False

    def append(self, user_id: str, role: str, content: str) -> None:
        key = self._key(user_id)
        message = json.dumps({"role": role, "content": content}, ensure_ascii=False)
        with self.client.pipeline() as pipe:
            pipe.rpush(key, message)
            pipe.ltrim(key, -HISTORY_MAX_MESSAGES, -1)
            pipe.expire(key, HISTORY_TTL_SECONDS)
            pipe.execute()

    def get_history(self, user_id: str) -> list[dict[str, str]]:
        return [
            json.loads(message)
            for message in self.client.lrange(self._key(user_id), 0, -1)
        ]

    def clear(self, user_id: str) -> None:
        self.client.delete(self._key(user_id))
