"""
AIGateway — 统一 AI 调用网关适配层

所有 AI 调用通过此层，内部路由到 deerflow 标准接口或 MultiVendorPool。

设计原则：
- LLM/chat: 走 deerflow.models.create_chat_model（标准接口，带 tracing）
- image/video/audio: 走 MultiVendorPool（保留，多模态支持）
- 所有调用自动附加 deerflow tracing 回调
- deerflow 不可用时自动回退到 MultiVendorPool

Phase 2 实施：先建骨架，后续逐步迁移调用点。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger("ai_gateway")

# 延迟导入：deerflow 模块在某些环境可能不可用，导入失败时回退
try:
    from deerflow.models import create_chat_model
    from deerflow.tracing import build_tracing_callbacks

    _DEERFLOW_AVAILABLE = True
except ImportError as e:
    logger.warning("deerflow models/tracing not available, falling back to MultiVendorPool: %s", e)
    _DEERFLOW_AVAILABLE = False
    create_chat_model = None  # type: ignore
    build_tracing_callbacks = None  # type: ignore


class AIGateway:
    """统一 AI 调用网关。

    Usage:
        gateway = AIGateway(pool=multi_vendor_pool)

        # LLM/chat（走 deerflow 标准接口）
        response = await gateway.chat(model="qwen-max", messages=[...])

        # 图像生成（走 MultiVendorPool）
        image = await gateway.generate_image(model="bailian", prompt="...")

        # 视频生成（走 MultiVendorPool）
        video = await gateway.generate_video(model="agnes", prompt="...")
    """

    def __init__(self, pool: Any):
        """
        Args:
            pool: MultiVendorPool 实例，用于图像/视频/音频生成和 LLM 回退
        """
        self._pool = pool
        self._chat_models: dict[str, Any] = {}
        self._deerflow_enabled = _DEERFLOW_AVAILABLE
        # Phase 4: 内容安全护栏（默认 LOG 模式，不阻止输出）
        self._guardrail = None
        try:
            from app.gateway.content_guardrail import get_guardrail

            self._guardrail = get_guardrail()
        except ImportError:
            logger.debug("ContentGuardrail not available")
        # Phase 3: token 追踪器
        self._token_tracker = None
        try:
            from app.gateway.token_tracker import get_token_tracker

            self._token_tracker = get_token_tracker()
        except ImportError:
            logger.debug("TokenTracker not available")

    @property
    def deerflow_available(self) -> bool:
        """deerflow 标准接口是否可用。"""
        return self._deerflow_enabled

    async def chat(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        trace: bool = True,
        **kwargs,
    ) -> str:
        """LLM/chat 调用。

        优先走 deerflow.models.create_chat_model（标准接口，带 tracing），
        失败时回退到 MultiVendorPool。

        Args:
            model: 模型名称（需在 deerflow config 中配置）
            messages: 聊天消息列表
            temperature: 采样温度
            max_tokens: 最大生成 token 数
            session_id: 会话 ID（用于 tracing）
            user_id: 用户 ID（用于 tracing）
            trace: 是否附加 tracing 回调
            **kwargs: 其他传递给模型的参数

        Returns:
            模型生成的文本内容
        """
        # 模型 fallback 链：主模型失败时依次尝试备选模型
        fallback_models = self._get_model_fallbacks(model)
        all_models = [model] + fallback_models

        last_error = None
        for attempt_model in all_models:
            if self._deerflow_enabled:
                try:
                    return await self._chat_via_deerflow(
                        model=attempt_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        session_id=session_id,
                        user_id=user_id,
                        trace=trace,
                        **kwargs,
                    )
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "deerflow chat failed (model=%s), trying next fallback: %s",
                        attempt_model,
                        e,
                    )
                    continue

            # 回退到 MultiVendorPool
            try:
                result = await self._chat_via_pool(
                    model=attempt_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
                return self._apply_guardrail(result)
            except Exception as e:
                last_error = e
                logger.warning(
                    "MultiVendorPool chat failed (model=%s), trying next: %s",
                    attempt_model,
                    e,
                )
                continue

        # 所有模型都失败
        raise RuntimeError(f"All model fallbacks exhausted. Tried: {all_models}. Last error: {last_error}") from last_error

    def _apply_guardrail(self, text: str) -> str:
        """应用内容安全护栏。"""
        if self._guardrail is None:
            return text
        try:
            result = self._guardrail.check(text)
            if result.has_violation and result.action.value == "redact":
                return result.filtered_text
            if result.has_violation and result.action.value == "block":
                return result.filtered_text
        except Exception as e:
            logger.debug("Guardrail check failed (non-fatal): %s", e)
        return text

    # 模型 fallback 链配置：主模型 → 备选模型（同 key 不同模型 / 跨渠道）
    # 大厂做法：同一 provider 内先降级（同 key 不同模型），再跨 provider 切换
    MODEL_FALLBACKS: dict[str, list[str]] = {
        # ── 阿里云百炼（bailian/alibaba）──
        # 同 key 内降级：max → plus → turbo（成本递增降序）
        "qwen-max": ["qwen-plus", "qwen-turbo", "qwen-flash"],
        "qwen-plus": ["qwen-turbo", "qwen-flash", "qwen-max"],
        "qwen-turbo": ["qwen-flash", "qwen-plus", "qwen-max"],
        "qwen-flash": ["qwen-turbo", "qwen-plus"],
        "qwen-long": ["qwen-turbo", "qwen-plus"],
        # qwen 前缀兜底（qwen2.5-*, qwen3-* 等）
        "qwen": ["qwen-turbo", "qwen-plus", "qwen-flash"],
        # ── DeepSeek 官方 ──
        "deepseek-v4-flash": ["deepseek-v3", "deepseek-chat"],
        "deepseek-v3": ["deepseek-v4-flash", "deepseek-chat"],
        "deepseek-chat": ["deepseek-v3", "deepseek-v4-flash"],
        "deepseek": ["deepseek-v3", "deepseek-chat", "deepseek-v4-flash"],
        # ── 硅基流动（siliconflow）──
        # 同 key 内降级：大模型 → 小模型
        "Qwen/Qwen2.5-72B": ["Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-7B"],
        "Qwen/Qwen2.5-7B": ["Qwen/Qwen2.5-7B-Instruct"],
        "Qwen/Qwen": ["Qwen/Qwen2.5-7B-Instruct"],
        # ── OpenRouter（多渠道聚合）──
        "openrouter": ["qwen-turbo", "deepseek-v3", "deepseek-v4-flash"],
        # ── NVIDIA NIM ──
        "nvidia": ["qwen-turbo", "deepseek-v3"],
        # ── 小云雀（seedance）──
        "seedance": ["qwen-turbo", "deepseek-v3"],
        # ── volcengine（火山引擎）──
        "doubao": ["qwen-turbo", "deepseek-v3"],
        # ── Agnes AI ──
        "agnes": ["qwen-turbo", "deepseek-v3"],
        # 默认通用 fallback（所有未匹配的模型）
        "default": ["qwen-turbo", "qwen-plus", "deepseek-v3", "deepseek-v4-flash"],
    }

    def _get_model_fallbacks(self, model: str) -> list[str]:
        """获取模型的备选 fallback 链。
        大厂做法：同一 provider 内先降级（同 key 不同模型），
        再跨 provider 切换，最大化利用率、最小化成本。
        匹配优先级：
        1. 精确匹配（model 名完全一致）
        2. provider 前缀匹配（qwen-* → qwen 链）
        3. 默认 fallback 链
        """
        import os

        # 环境变量覆盖：FALLBACK_<MODEL>=model1,model2,model3
        env_key = f"FALLBACK_{model.upper().replace('-', '_').replace('/', '_')}"
        env_val = os.getenv(env_key)
        if env_val:
            return [m.strip() for m in env_val.split(",") if m.strip()]

        # 精确匹配
        if model in self.MODEL_FALLBACKS:
            return self.MODEL_FALLBACKS[model]

        # provider 前缀匹配
        # 提取 provider 名（模型名第一段，如 "Qwen/Qwen2.5-72B" → "Qwen"）
        provider_prefix = model.split("/")[0].lower() if "/" in model else ""

        # 检查 provider 前缀是否在配置中
        for provider_key in self.MODEL_FALLBACKS:
            if provider_key in ("default",):
                continue
            if provider_prefix and provider_key in provider_prefix:
                return self.MODEL_FALLBACKS[provider_key]
            if model.lower().startswith(provider_key):
                return self.MODEL_FALLBACKS[provider_key]

        # 默认 fallback 链
        return self.MODEL_FALLBACKS["default"]

    async def _chat_via_deerflow(
        self,
        model,
        messages,
        *,
        temperature,
        max_tokens,
        session_id,
        user_id,
        trace,
        **kwargs,
    ) -> str:
        """通过 deerflow 标准接口调用 LLM。"""
        chat_model = self._get_chat_model(model)

        # 构建 tracing 回调
        callbacks = None
        if trace and build_tracing_callbacks is not None:
            try:
                callbacks = build_tracing_callbacks(
                    session_id=session_id,
                    user_id=user_id,
                )
            except Exception as e:
                logger.debug("tracing callbacks not available: %s", e)

        # 构建 model_overrides
        model_overrides = {}
        if temperature is not None:
            model_overrides["temperature"] = temperature
        if max_tokens is not None:
            model_overrides["max_tokens"] = max_tokens

        # LangChain 消息格式转换
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        # SoL-Pi 优化 #3: 上下文压缩（长任务 token 降低 30-40%）
        try:
            from app.gateway.context_compressor import compress_messages, should_compress

            if should_compress(messages):
                messages = compress_messages(messages)
        except Exception as e:
            logger.debug("Context compression skipped (non-fatal): %s", e)

        lc_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))

        start_time = time.time()
        try:
            response = await chat_model.ainvoke(
                lc_messages,
                callbacks=callbacks,
                **kwargs,
            )
            # Phase 3: 记录 token 消耗
            self._record_token_usage(
                model=model,
                response=response,
                latency_ms=(time.time() - start_time) * 1000,
                session_id=session_id,
                user_id=user_id,
                success=True,
            )

            # SoL-Pi 优化 #2: 大输出缓存（多步骤 token 降低 25-35%）
            result_content = response.content if hasattr(response, "content") else str(response)
            try:
                from app.gateway.large_output_cache import cache_large_output, should_cache

                if should_cache(result_content):
                    cache_result = await cache_large_output(
                        content=result_content,
                        namespace=f"chat:{model}",
                        metadata={"session_id": session_id, "user_id": user_id},
                    )
                    if cache_result.get("cached"):
                        logger.debug(
                            "Large output cached: %d tokens, key=%s",
                            cache_result["original_tokens"],
                            cache_result["cache_key"][-8:],
                        )
            except Exception as e:
                logger.debug("Large output cache skipped (non-fatal): %s", e)

            return result_content
        except Exception as e:
            self._record_token_usage(
                model=model,
                response=None,
                latency_ms=(time.time() - start_time) * 1000,
                session_id=session_id,
                user_id=user_id,
                success=False,
                error=str(e),
            )
            raise

    def _record_token_usage(self, *, model, response, latency_ms, session_id, user_id, success, error=None):
        """记录 token 消耗到 TokenTracker。"""
        if self._token_tracker is None:
            return
        try:
            from app.gateway.token_tracker import TokenUsage

            usage = TokenUsage(
                model=model,
                prompt_tokens=getattr(response, "usage_metadata", {}).get("input_tokens", 0) if response else 0,
                completion_tokens=getattr(response, "usage_metadata", {}).get("output_tokens", 0) if response else 0,
                total_tokens=getattr(response, "usage_metadata", {}).get("total_tokens", 0) if response else 0,
                latency_ms=latency_ms,
                session_id=session_id,
                user_id=user_id,
                success=success,
                error=error,
            )
            self._token_tracker.record(usage)
        except Exception as e:
            logger.debug("Token usage recording failed (non-fatal): %s", e)

    async def _chat_via_pool(self, model, messages, **kwargs) -> str:
        """通过 MultiVendorPool 调用 LLM（回退路径）。"""
        # MultiVendorPool 的 chat 接口（根据实际接口调整）
        if hasattr(self._pool, "chat"):
            result = await self._pool.chat(model=model, messages=messages, **kwargs)
            if isinstance(result, dict):
                return result.get("content", str(result))
            return str(result)
        elif hasattr(self._pool, "chat_completions"):
            result = await self._pool.chat_completions(model=model, messages=messages, **kwargs)
            if isinstance(result, dict):
                return result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return str(result)
        else:
            raise NotImplementedError(f"MultiVendorPool does not support chat. Available methods: {[m for m in dir(self._pool) if not m.startswith('_')]}")

    async def chat_completions_stream(
        self,
        model: str,
        payload: dict,
        region: str = "global",
        scenario: str | None = None,
        **kwargs,
    ):
        """流式 chat_completions（SSE 格式）。

        优先走 deerflow create_chat_model().astream()（带 tracing + TokenTracker），
        将 LangChain AIMessageChunk 转换为 OpenAI SSE 格式。
        deerflow 不可用时回退到 MultiVendorPool。
        """
        messages = payload.get("messages", [])
        temperature = payload.get("temperature", 0.7)
        max_tokens = payload.get("max_tokens", 2048)

        # ── 优先走 deerflow astream ──
        if _DEERFLOW_AVAILABLE:
            try:
                chat_model = self._get_chat_model(model)
                callbacks = (
                    build_tracing_callbacks(
                        operation_name=f"ai_gateway.stream.{model}",
                        metadata={"region": region, "scenario": scenario or "default"},
                    )
                    if _DEERFLOW_AVAILABLE
                    else None
                )

                config = {"callbacks": callbacks} if callbacks else {}
                if temperature is not None:
                    config["temperature"] = temperature
                if max_tokens is not None:
                    config["max_tokens"] = max_tokens

                async for chunk in chat_model.astream(messages, config=config):
                    # LangChain AIMessageChunk → OpenAI SSE 格式
                    content = getattr(chunk, "content", "")
                    if content:
                        sse_data = {
                            "choices": [
                                {
                                    "delta": {"content": content},
                                    "index": 0,
                                }
                            ],
                            "model": model,
                        }
                        yield f"data: {json.dumps(sse_data, ensure_ascii=False)}\n\n"

                    # 记录 token 消耗到 TokenTracker
                    usage = getattr(chunk, "usage_metadata", None)
                    if usage:
                        try:
                            from app.gateway.token_tracker import get_token_tracker

                            tracker = get_token_tracker()
                            if tracker:
                                await tracker.record(
                                    model=model,
                                    input_tokens=usage.get("input_tokens", 0),
                                    output_tokens=usage.get("output_tokens", 0),
                                    total_tokens=usage.get("total_tokens", 0),
                                    scenario=scenario or "chat_stream",
                                    region=region,
                                )
                        except Exception as e:
                            logger.debug("TokenTracker record failed (non-fatal): %s", e)

                yield "data: [DONE]\n\n"
                return
            except Exception as e:
                logger.warning("deerflow astream failed, falling back to pool: %s", e)

        # ── 回退：MultiVendorPool（已验证稳定，返回 OpenAI SSE 格式）──
        if hasattr(self._pool, "chat_completions_stream"):
            async for chunk in self._pool.chat_completions_stream(
                model=model,
                payload=payload,
                region=region,
                scenario=scenario,
                **kwargs,
            ):
                yield chunk
        else:
            # 回退：非流式调用模拟流式
            result = await self.chat_completions(
                model=model,
                payload=payload,
                region=region,
                scenario=scenario,
                **kwargs,
            )
            content = ""
            if isinstance(result, dict):
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            yield f"data: {json.dumps({'choices': [{'delta': {'content': content}}]})}\n\n"
            yield "data: [DONE]\n\n"

    def _get_chat_model(self, model: str):
        """获取或创建 chat model 实例（带缓存）。"""
        if model not in self._chat_models:
            self._chat_models[model] = create_chat_model(
                name=model,
                attach_tracing=False,  # tracing 在调用层统一附加，避免重复 span
            )
        return self._chat_models[model]

    async def generate_image(self, model: str, prompt: str, **kwargs):
        """图像生成（走 MultiVendorPool）。

        TODO Phase 3: 附加 deerflow tracing 回调，统一记录 token/成本
        """
        return await self._pool.image_generations(model=model, prompt=prompt, **kwargs)

    async def generate_video(self, model: str, prompt: str, **kwargs):
        """视频生成（走 MultiVendorPool）。

        TODO Phase 3: 附加 deerflow tracing 回调
        """
        return await self._pool.video_generations(model=model, prompt=prompt, **kwargs)

    async def generate_audio(self, model: str, prompt: str, **kwargs):
        """音频生成（走 MultiVendorPool）。

        TODO Phase 3: 附加 deerflow tracing 回调
        """
        if hasattr(self._pool, "audio_generations"):
            return await self._pool.audio_generations(model=model, prompt=prompt, **kwargs)
        raise NotImplementedError("MultiVendorPool does not support audio generation")

    async def chat_completions(
        self,
        model: str,
        payload: dict,
        *,
        region: str | None = None,
        scenario: str | None = None,
        **kwargs,
    ) -> dict:
        """兼容 MultiVendorPool.chat_completions 接口的统一调用。

        优先走 deerflow 标准接口，失败时回退到 MultiVendorPool。
        这是 pipeline_executor 迁移的主要入口。

        Args:
            model: 模型名称
            payload: OpenAI 格式 {"messages": [...]}
            region: 区域（仅回退路径使用，deerflow 路径忽略）
            scenario: 场景（仅回退路径使用，deerflow 路径忽略）
            **kwargs: 其他参数

        Returns:
            OpenAI 格式 {"choices": [{"message": {"content": "..."}}]}
        """
        messages = payload.get("messages", []) if isinstance(payload, dict) else []

        if self._deerflow_enabled:
            try:
                content = await self._chat_via_deerflow(
                    model=model,
                    messages=messages,
                    temperature=kwargs.pop("temperature", None),
                    max_tokens=kwargs.pop("max_tokens", None),
                    session_id=kwargs.pop("session_id", None),
                    user_id=kwargs.pop("user_id", None),
                    trace=kwargs.pop("trace", True),
                    **kwargs,
                )
                return {"choices": [{"message": {"content": self._apply_guardrail(content)}}]}
            except Exception as e:
                logger.warning(
                    "deerflow chat_completions failed (model=%s), falling back to pool: %s",
                    model,
                    e,
                )

        # 回退到 MultiVendorPool（保留 region/scenario 等参数）
        return await self._pool.chat_completions(
            model=model,
            payload=payload,
            region=region,
            scenario=scenario,
            **kwargs,
        )


# 全局单例（在 app lifespan 中初始化）
_gateway: AIGateway | None = None


def init_gateway(pool: Any) -> AIGateway:
    """初始化全局 AIGateway 单例。"""
    global _gateway
    _gateway = AIGateway(pool=pool)
    logger.info("AIGateway initialized (deerflow_available=%s)", _gateway.deerflow_available)
    return _gateway


def get_gateway() -> AIGateway:
    """获取全局 AIGateway 单例。"""
    if _gateway is None:
        raise RuntimeError("AIGateway not initialized. Call init_gateway(pool) first.")
    return _gateway
