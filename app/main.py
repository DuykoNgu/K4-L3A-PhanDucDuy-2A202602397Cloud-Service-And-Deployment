"""API agent: xác thực, quota, ngân sách và history dùng chung."""

from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from redis import RedisError

from utils.mock_llm import ask_llm

from .auth import verify_api_key
from .config import get_settings
from .cost_guard import CostGuard
from .lifecycle import lifecycle
from .logging_utils import log_event
from .rate_limiter import RateLimiter
from .store import ConversationStore, get_redis_client

SERVICE_NAME = "day12-agent"
SERVICE_VERSION = "1.0.0"


@lru_cache(maxsize=1)
def get_store() -> ConversationStore:
    return ConversationStore(get_redis_client())


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    return RateLimiter(get_redis_client(), get_settings().rate_limit_per_minute)


@lru_cache(maxsize=1)
def get_cost_guard() -> CostGuard:
    return CostGuard(get_redis_client(), get_settings().monthly_budget_usd)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    get_settings()
    lifecycle.shutting_down = False
    lifecycle.install()
    log_event("service_started", service=SERVICE_NAME, version=SERVICE_VERSION)
    try:
        yield
    finally:
        log_event("service_stopped", service=SERVICE_NAME)


app = FastAPI(
    title="Day 12 Production Agent", version=SERVICE_VERSION, lifespan=lifespan
)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@app.exception_handler(RedisError)
async def redis_unavailable(_request: Request, error: RedisError) -> JSONResponse:
    log_event("redis_unavailable", level="error", error_type=type(error).__name__)
    return JSONResponse(status_code=503, content={"detail": "Redis unavailable"})


@app.get("/health")
def health() -> JSONResponse:
    if lifecycle.shutting_down:
        return JSONResponse(status_code=503, content={"status": "shutting_down"})
    return JSONResponse(
        content={"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}
    )


@app.get("/ready")
def ready(store: ConversationStore = Depends(get_store)) -> JSONResponse:
    if lifecycle.shutting_down:
        return JSONResponse(status_code=503, content={"status": "shutting_down"})
    if not store.ping():
        return JSONResponse(
            status_code=503, content={"status": "not ready", "redis": False}
        )
    return JSONResponse(content={"status": "ready", "redis": True})


@app.post("/ask")
def ask(
    payload: AskRequest,
    user_id: str = Depends(verify_api_key),
    store: ConversationStore = Depends(get_store),
    limiter: RateLimiter = Depends(get_rate_limiter),
    guard: CostGuard = Depends(get_cost_guard),
) -> dict[str, Any]:
    if lifecycle.shutting_down:
        raise HTTPException(status_code=503, detail="shutting_down")
    limiter.check(user_id)
    # ponytail: kiểm tra chi phí đã ghi; giữ chỗ chi phí nếu cần trần tiền tuyệt đối.
    guard.check(user_id)
    history = store.get_history(user_id)
    result = ask_llm(payload.question, history)
    store.append(user_id, "user", payload.question)
    store.append(user_id, "assistant", result["answer"])
    guard.record(user_id, result["cost_usd"])
    log_event(
        "ask_completed",
        user_id=user_id,
        tokens_in=result["tokens_in"],
        tokens_out=result["tokens_out"],
        cost_usd=result["cost_usd"],
    )
    return {
        "answer": result["answer"],
        "user_id": user_id,
        "history_length": len(history),
        "cost_usd": result["cost_usd"],
        "tokens": {"in": result["tokens_in"], "out": result["tokens_out"]},
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=get_settings().port)
