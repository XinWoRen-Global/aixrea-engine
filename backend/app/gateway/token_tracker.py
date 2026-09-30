"""
TokenTracker — 统一 token 消耗追踪

轻量级 token 追踪器，不依赖外部 provider（Langfuse/LangSmith），
直接在 AIGateway 中记录每次 LLM 调用的 token 消耗。

设计原则：
- 内存存储 + 可选持久化到 Redis
- 按 run_id / session_id / user_id 聚合
- 提供查询接口供 CreditsEngine 读取
- 异步写入，不阻塞主流程
- 失败时静默降级（不影响正常调用）

Phase 3 实施：先建骨架，后续接入 Redis 持久化和 CreditsEngine。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger("token_tracker")


@dataclass
class TokenUsage:
    """单次调用的 token 消耗记录。"""

    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    run_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    success: bool = True
    error: str | None = None


@dataclass
class TokenAggregate:
    """聚合统计。"""

    total_calls: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    by_model: dict[str, int] = field(default_factory=lambda: defaultdict(int))


class TokenTracker:
    """统一 token 消耗追踪器。

    Usage:
        tracker = TokenTracker()
        tracker.record(TokenUsage(model="qwen-max", total_tokens=100, user_id="u1"))
        agg = tracker.get_aggregate(user_id="u1")
        print(agg.total_tokens)
    """

    def __init__(self, max_records: int = 10000, redis_url: str | None = None):
        """
        Args:
            max_records: 内存中保留的最大记录数（超过后丢弃最旧的）
            redis_url: Redis 连接 URL，None 则仅内存存储
        """
        self._records: list[TokenUsage] = []
        self._max_records = max_records
        self._lock = asyncio.Lock()
        self._redis_client = None
        self._redis_url = redis_url
        # 延迟初始化 Redis（避免导入时连接失败）
        if redis_url:
            try:
                import redis.asyncio as aioredis

                self._redis_client = aioredis.from_url(redis_url, decode_responses=True)
                logger.info("TokenTracker Redis persistence enabled")
            except Exception as e:
                logger.warning("TokenTracker Redis init failed, falling back to memory-only: %s", e)

    @property
    def redis_enabled(self) -> bool:
        return self._redis_client is not None

    def record(self, usage: TokenUsage):
        """记录一次 token 消耗（同步，非阻塞）。"""
        try:
            self._records.append(usage)
            # 超过上限时丢弃最旧的记录（简单实现，后续可用 deque）
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records :]
            # 异步写入 Redis（fire-and-forget）
            if self._redis_client is not None:
                asyncio.create_task(self._write_to_redis(usage))
        except Exception as e:
            logger.debug("TokenTracker.record failed (non-fatal): %s", e)

    async def _write_to_redis(self, usage: TokenUsage):
        """异步写入 Redis（Hash + 有序集合索引）。"""
        if self._redis_client is None:
            return
        try:
            key = f"token_usage:{usage.run_id or int(usage.timestamp)}"
            data = {
                "model": usage.model,
                "prompt_tokens": str(usage.prompt_tokens),
                "completion_tokens": str(usage.completion_tokens),
                "total_tokens": str(usage.total_tokens),
                "latency_ms": str(usage.latency_ms),
                "timestamp": str(usage.timestamp),
                "run_id": usage.run_id or "",
                "session_id": usage.session_id or "",
                "user_id": usage.user_id or "",
                "success": "1" if usage.success else "0",
                "error": usage.error or "",
            }
            await self._redis_client.hset(key, mapping=data)
            await self._redis_client.expire(key, 86400 * 7)  # 7 天过期
            # 索引：按用户
            if usage.user_id:
                await self._redis_client.zadd(
                    f"token_usage:index:user:{usage.user_id}",
                    {key: usage.timestamp},
                )
            # 索引：按会话
            if usage.session_id:
                await self._redis_client.zadd(
                    f"token_usage:index:session:{usage.session_id}",
                    {key: usage.timestamp},
                )
        except Exception as e:
            logger.debug("TokenTracker Redis write failed (non-fatal): %s", e)

    async def record_async(self, usage: TokenUsage):
        """异步记录（带锁）。"""
        async with self._lock:
            self.record(usage)

    def get_aggregate(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        model: str | None = None,
        since: float | None = None,
    ) -> TokenAggregate:
        """获取聚合统计。

        Args:
            user_id: 按用户过滤
            session_id: 按会话过滤
            run_id: 按运行过滤
            model: 按模型过滤
            since: 只统计此时间戳之后的记录

        Returns:
            TokenAggregate 聚合统计
        """
        agg = TokenAggregate()
        for usage in self._records:
            if user_id and usage.user_id != user_id:
                continue
            if session_id and usage.session_id != session_id:
                continue
            if run_id and usage.run_id != run_id:
                continue
            if model and usage.model != model:
                continue
            if since and usage.timestamp < since:
                continue

            agg.total_calls += 1
            agg.total_prompt_tokens += usage.prompt_tokens
            agg.total_completion_tokens += usage.completion_tokens
            agg.total_tokens += usage.total_tokens
            agg.total_latency_ms += usage.latency_ms
            agg.by_model[usage.model] += usage.total_tokens
            if usage.success:
                agg.success_count += 1
            else:
                agg.failure_count += 1
        return agg

    async def get_aggregate_from_redis(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        since: float | None = None,
        limit: int = 1000,
    ) -> TokenAggregate:
        """从 Redis 读取聚合统计（优先于内存，支持历史数据）。

        Args:
            user_id: 按用户过滤
            session_id: 按会话过滤
            since: 只统计此时间戳之后的记录
            limit: 最多读取多少条记录

        Returns:
            TokenAggregate 聚合统计
        """
        agg = TokenAggregate()
        if self._redis_client is None:
            # Redis 不可用时回退到内存
            return self.get_aggregate(user_id=user_id, session_id=session_id, since=since)

        try:
            # 确定索引 key
            if user_id:
                index_key = f"token_usage:index:user:{user_id}"
            elif session_id:
                index_key = f"token_usage:index:session:{session_id}"
            else:
                # 无过滤时无法用索引，回退内存
                return self.get_aggregate(user_id=user_id, session_id=session_id, since=since)

            # 从有序集合获取记录 key
            min_score = since or "-inf"
            keys = await self._redis_client.zrevrangebyscore(index_key, "+inf", min_score, start=0, num=limit)

            for key in keys:
                data = await self._redis_client.hgetall(key)
                if not data:
                    continue
                usage = TokenUsage(
                    model=data.get("model", "unknown"),
                    prompt_tokens=int(data.get("prompt_tokens", 0)),
                    completion_tokens=int(data.get("completion_tokens", 0)),
                    total_tokens=int(data.get("total_tokens", 0)),
                    latency_ms=float(data.get("latency_ms", 0)),
                    timestamp=float(data.get("timestamp", 0)),
                    run_id=data.get("run_id") or None,
                    session_id=data.get("session_id") or None,
                    user_id=data.get("user_id") or None,
                    success=data.get("success", "1") == "1",
                    error=data.get("error") or None,
                )
                agg.total_calls += 1
                agg.total_prompt_tokens += usage.prompt_tokens
                agg.total_completion_tokens += usage.completion_tokens
                agg.total_tokens += usage.total_tokens
                agg.total_latency_ms += usage.latency_ms
                agg.by_model[usage.model] += usage.total_tokens
                if usage.success:
                    agg.success_count += 1
                else:
                    agg.failure_count += 1
        except Exception as e:
            logger.debug("TokenTracker Redis aggregate failed, falling back to memory: %s", e)
            return self.get_aggregate(user_id=user_id, session_id=session_id, since=since)

        return agg

    def get_recent(self, limit: int = 50, **filters) -> list[TokenUsage]:
        """获取最近的记录。"""
        results = []
        for usage in reversed(self._records):
            if all(getattr(usage, k, None) == v for k, v in filters.items() if v):
                results.append(usage)
                if len(results) >= limit:
                    break
        return results

    def estimate_cost(self, agg: TokenAggregate, price_per_1k_tokens: float = 0.01) -> float:
        """估算成本（默认 $0.01/1K tokens，可按模型调整）。"""
        return (agg.total_tokens / 1000) * price_per_1k_tokens

    def clear(self):
        """清空所有记录（用于测试）。"""
        self._records.clear()


# 全局单例
_tracker: TokenTracker | None = None


def init_token_tracker(max_records: int = 10000, redis_url: str | None = None) -> TokenTracker:
    """初始化全局 token 追踪器。

    Args:
        max_records: 内存中保留的最大记录数
        redis_url: Redis 连接 URL（从环境变量 REDIS_URL 读取），None 则仅内存
    """
    global _tracker
    if redis_url is None:
        import os

        redis_url = os.environ.get("REDIS_URL") or os.environ.get("REDIS_CONNECTION_STRING")
    _tracker = TokenTracker(max_records=max_records, redis_url=redis_url)
    logger.info("TokenTracker initialized (max_records=%d, redis=%s)", max_records, "enabled" if redis_url else "disabled")
    return _tracker


def get_token_tracker() -> TokenTracker:
    """获取全局 token 追踪器。"""
    global _tracker
    if _tracker is None:
        _tracker = TokenTracker()
    return _tracker
