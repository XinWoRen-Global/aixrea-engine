"""统一模型注册表 (Unified Model Registry)

企业级动态模型路由网关 - 阶段二基础能力

核心功能：
1. 统一模型命名空间：{厂商前缀}/{模型家族}-{版本}-{规格}
2. 模型别名映射：兼容现有模型ID，自动映射到统一命名空间
3. 扩展模型配置：Bailian 30+模型，覆盖文本/图像/视频/音频
4. 模型元数据：等级、能力、价格、区域、健康度
5. 降级路径配置：基于场景的自动降级路径

设计原则：
- 与现有MultiVendorPool完全兼容
- 与agent配置中的xwr.models元数据对齐
- 与credits_engine计费体系保持一致
- 零侵入：现有代码无需修改即可使用

文档：devops/docs/enterprise-dynamic-model-routing-gateway-v2-260912.md
"""

import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 1. 模型等级定义
# ═══════════════════════════════════════════════════════════════


class ModelTier(StrEnum):
    """模型等级（五级分级体系）"""

    FLAGSHIP = "flagship"  # 旗舰级：复杂推理、高质量创作
    PREMIUM = "premium"  # 高级：专业创作、精准分析
    STANDARD = "standard"  # 标准：通用任务、日常对话
    BASIC = "basic"  # 基础：简单任务、批量处理
    LIGHT = "light"  # 轻量：边缘计算、实时响应


class ModelModality(StrEnum):
    """模型模态"""

    TEXT = "text"  # 文本生成/理解
    IMAGE = "image"  # 图像生成
    VIDEO = "video"  # 视频生成
    AUDIO = "audio"  # 音频生成/识别
    MULTIMODAL = "multimodal"  # 多模态（图文混合）
    EMBEDDING = "embedding"  # 向量嵌入


class ModelStatus(StrEnum):
    """模型状态"""

    ACTIVE = "active"  # 可用
    DEGRADED = "degraded"  # 降级（性能下降）
    UNAVAILABLE = "unavailable"  # 不可用
    MAINTENANCE = "maintenance"  # 维护中


# ═══════════════════════════════════════════════════════════════
# 2. 模型元数据定义
# ═══════════════════════════════════════════════════════════════


@dataclass
class ModelMetadata:
    """模型元数据"""

    # 基础信息
    model_id: str  # 统一模型ID（bailian/qwen-plus）
    provider: str  # 厂商（bailian/agnes/nvidia/...）
    provider_model_id: str  # 厂商模型ID（qwen-plus）
    display_name: str  # 显示名称

    # 能力标签
    modalities: list[ModelModality]  # 支持的模态
    capabilities: list[str]  # 能力标签（chat/function_calling/vision/...）
    context_window: int = 32768  # 上下文窗口
    max_output_tokens: int = 8192  # 最大输出token

    # 质量分级
    tier: ModelTier = ModelTier.STANDARD  # 模型等级
    quality_score: float = 70.0  # 质量评分（0-100）

    # 成本信息（元/百万token）
    input_price: float = 0.0  # 输入价格
    output_price: float = 0.0  # 输出价格
    currency: str = "CNY"  # 货币单位

    # 性能信息
    avg_latency_ms: float = 2000.0  # 平均延迟
    p95_latency_ms: float = 5000.0  # P95延迟
    throughput_rps: float = 10.0  # 吞吐量（请求/秒）

    # 区域信息
    regions: list[str] = field(default_factory=lambda: ["cn-beijing"])
    preferred_region: str = "cn-beijing"  # 首选区域

    # 状态信息
    status: ModelStatus = ModelStatus.ACTIVE
    health_score: float = 100.0  # 健康度评分（0-100）
    quota_status: str = "unknown"  # 额度状态（sufficient/low/exhausted/unknown）

    # 计费兼容（与credits_engine对齐）
    credits_engine_id: str | None = None  # credits_engine中的模型ID（视频模型必填）

    # 元数据
    description: str = ""
    tags: list[str] = field(default_factory=list)
    release_date: str | None = None


# ═══════════════════════════════════════════════════════════════
# 3. 模型别名映射（兼容现有ID）
# ═══════════════════════════════════════════════════════════════

# 旧模型ID → 统一模型ID
# 所有现有配置中的模型ID都会自动映射，无需修改现有代码
MODEL_ALIASES: dict[str, str] = {
    # ── 文本模型别名 ──
    "deepseek-v4": "bailian1/deepseek-v4-flash",
    "deepseek-v4-flash": "bailian1/deepseek-v4-flash",
    "deepseek-v3": "bailian1/deepseek-v3",
    "deepseek-ai/DeepSeek-V4-Flash": "bailian1/deepseek-v4-flash",
    "deepseek-ai/DeepSeek-V2-Chat": "bailian1/deepseek-v3",
    "qwen-plus": "bailian1/qwen-plus",
    "qwen-turbo": "bailian1/qwen-turbo",
    "qwen-max": "bailian1/qwen-max",
    "qwen3.5-flash": "bailian1/qwen3.5-flash",
    "qwen3.7-flash": "bailian1/qwen3.7-flash",
    "qwen3.7-flash-2026-07-15": "bailian1/qwen3.7-flash",
    "qwen3.8-max": "bailian1/qwen3.8-max",
    "qwen-long": "bailian1/qwen-long",
    "qwen3-30b-a10b-instruct": "bailian1/qwen3-30b",
    "qwen3-8b-a10b-instruct": "bailian1/qwen3-8b",
    "qwen-vl-max": "bailian1/qwen-vl-max",
    "qwen-vl-plus": "bailian1/qwen-vl-plus",
    "qwen-coder-turbo": "bailian1/qwen-coder-turbo",
    "qwen-audio-turbo": "bailian1/qwen-audio-turbo",
    "llama-3.1-8b": "nvidia/llama-3.1-8b",
    "llama-3.1-70b": "groq/llama-3.1-70b",
    "llama-3.3-70b": "groq/llama-3.3-70b",
    "meta/llama-3.1-8b-instruct": "nvidia/llama-3.1-8b",
    "meta/llama-3.1-70b-instruct": "nvidia/llama-3.1-70b",
    "agnes-2.0": "agnes/agnes-2.0",
    "agnes-2.0-flash": "agnes/agnes-2.0-flash",
    "bailian-qwen3-flash": "bailian1/qwen3.7-flash",
    "bailian-qwen-turbo": "bailian1/qwen-turbo",
    "bailian-qwen-plus": "bailian1/qwen-plus",
    "bailian-qwen-max": "bailian1/qwen-max",
    "bailian-qwen3-30b": "bailian1/qwen3-30b",
    "bailian-deepseek-v4-flash": "bailian1/deepseek-v4-flash",
    # ── 图像模型别名 ──
    "image-generator": "agnes/agnes-image-2.1-flash",
    "qwen-image-3.0-pro": "bailian1/qwen-image-3.0-pro",
    "wan2.7-image": "bailian1/wan2.7-image",
    "wanx2.1-t2i-turbo": "bailian1/wanx2.1-t2i-turbo",
    "agnes-image": "agnes/agnes-image-2.1-flash",
    "agnes-image-2.1-flash": "agnes/agnes-image-2.1-flash",
    "Kwai-Kolors/Kolors": "siliconflow/kolors",
    "black-forest-labs/FLUX.1-schnell": "nvidia/flux-schnell",
    # ── 视频模型别名（与credits_engine对齐）──
    "video-generator-t2v": "agnes/agnes-video-v2.0",
    "video-generator-i2v": "agnes/agnes-video-v2.0",
    "seedance-2-mini": "volcengine/seedance-2-mini",
    "seedance-2-5": "agnes/seedance-2-5",
    "Seedance 2 Mini": "volcengine/seedance-2-mini",
    "seedance-2-0-mini": "volcengine/seedance-2-mini",
    "wan3.0-video": "bailian1/wan3.0-video",
    "wan3.0": "bailian1/wan3.0-video",
    "minimax-h3": "bailian1/minimax-h3",
    "MiniMax-H3": "bailian1/minimax-h3",
    "MiniMax/MiniMax-H3": "bailian1/minimax-h3",
    "minimax-h3-max": "bailian1/minimax-h3-max",
    "MiniMax-H3-Max": "bailian1/minimax-h3-max",
    "minimax-h3-250528": "bailian1/minimax-h3",
    "agnes-video": "volcengine/seedance-2-mini",
    "agnes-video-v2.0": "volcengine/seedance-2-mini",
    "Wan-AI/Wan2.2-T2V-A14B": "bailian1/wan2.2-video",
    "Wan-AI/Wan2.2-I2V-A14B": "bailian1/wan2.2-video",
    # ── 音频模型别名 ──
    "speech-generator": "bailian1/minimax-speech-2.8-turbo",
    "speech-recognition": "bailian1/minimax-speech-2.8-turbo",
    "MiniMax/speech-2.8-turbo": "bailian1/minimax-speech-2.8-turbo",
    "FunAudioLLM/SenseVoiceSmall": "siliconflow/sensevoice",
}


def normalize_model_id(model_id: str) -> str:
    """将模型ID规范化为统一命名空间

    Args:
        model_id: 任意格式的模型ID（旧ID或新ID）

    Returns:
        统一命名空间的模型ID（{厂商}/{模型名}）
    """
    if not model_id:
        return model_id

    # 已经是统一格式（包含/），直接返回
    if "/" in model_id and not model_id.startswith(("Qwen/", "meta/", "deepseek-ai/", "Kwai-Kolors/", "black-forest-labs/", "Wan-AI/", "FunAudioLLM/", "MiniMax/")):
        return model_id

    # 查找别名映射
    normalized = MODEL_ALIASES.get(model_id)
    if normalized:
        return normalized

    # 未找到映射，尝试推断厂商
    # 如果是已知厂商的模型ID格式，添加bailian前缀
    known_bailian_prefixes = ("qwen", "deepseek", "llama", "wan", "minimax", "flux", "stable-diffusion", "whisper", "paraformer", "sensevoice")
    model_lower = model_id.lower()
    if any(model_lower.startswith(p) for p in known_bailian_prefixes):
        return f"bailian/{model_id}"

    # 无法推断，原样返回（记录警告）
    logger.debug(f"Model ID not found in aliases, using as-is: {model_id}")
    return model_id


# ═══════════════════════════════════════════════════════════════
# 4. 扩展模型注册表（Bailian 30+模型）
# ═══════════════════════════════════════════════════════════════

MODEL_REGISTRY: dict[str, ModelMetadata] = {
    # ══════ Bailian 文本模型 ══════
    "bailian1/qwen-max": ModelMetadata(
        model_id="bailian1/qwen-max",
        provider="bailian",
        provider_model_id="qwen-max",
        display_name="Qwen Max (阿里云百炼·旗舰级)",
        modalities=[ModelModality.TEXT],
        capabilities=["chat", "function_calling", "structured_output"],
        context_window=32768,
        max_output_tokens=8192,
        tier=ModelTier.FLAGSHIP,
        quality_score=95.0,
        input_price=20.0,
        output_price=60.0,
        avg_latency_ms=3000.0,
        p95_latency_ms=8000.0,
        regions=["cn-beijing", "cn-hangzhou"],
        description="通义千问Max，最高质量，适合复杂推理和高质量创作",
        tags=["high-quality", "complex-reasoning", "structured-output"],
    ),
    "bailian1/qwen-plus": ModelMetadata(
        model_id="bailian1/qwen-plus",
        provider="bailian",
        provider_model_id="qwen-plus",
        display_name="Qwen Plus (阿里云百炼·能力增强型)",
        modalities=[ModelModality.TEXT],
        capabilities=["chat", "function_calling", "structured_output"],
        context_window=32768,
        max_output_tokens=8192,
        tier=ModelTier.PREMIUM,
        quality_score=88.0,
        input_price=4.0,
        output_price=12.0,
        avg_latency_ms=2000.0,
        p95_latency_ms=5000.0,
        regions=["cn-beijing", "cn-hangzhou", "ap-southeast-1"],
        description="通义千问Plus，能力增强型，结构化输出稳定，性价比高 ⭐推荐",
        tags=["recommended", "structured-output", "good-value"],
    ),
    "bailian1/qwen-turbo": ModelMetadata(
        model_id="bailian1/qwen-turbo",
        provider="bailian",
        provider_model_id="qwen-turbo",
        display_name="Qwen Turbo (阿里云百炼·性价比首选)",
        modalities=[ModelModality.TEXT],
        capabilities=["chat", "function_calling"],
        context_window=32768,
        max_output_tokens=8192,
        tier=ModelTier.STANDARD,
        quality_score=80.0,
        input_price=0.5,
        output_price=2.0,
        avg_latency_ms=1200.0,
        p95_latency_ms=3000.0,
        regions=["cn-beijing", "cn-hangzhou", "ap-southeast-1", "us-west-1"],
        description="通义千问Turbo，速度快，成本低，适合高并发场景",
        tags=["fast", "low-cost", "high-concurrency"],
    ),
    "bailian1/qwen3.7-flash": ModelMetadata(
        model_id="bailian1/qwen3.7-flash",
        provider="bailian",
        provider_model_id="qwen3.7-flash-2026-07-15",
        display_name="Qwen3.7 Flash (阿里云百炼·Qwen3系列高效模型)",
        modalities=[ModelModality.TEXT],
        capabilities=["chat", "function_calling", "structured_output"],
        context_window=32768,
        max_output_tokens=8192,
        tier=ModelTier.BASIC,
        quality_score=75.0,
        input_price=0.3,
        output_price=0.6,
        avg_latency_ms=800.0,
        p95_latency_ms=2000.0,
        regions=["cn-beijing", "cn-hangzhou"],
        description="Qwen3系列最新高效模型，速度快，成本极低",
        tags=["ultra-fast", "ultra-low-cost", "qwen3"],
    ),
    "bailian1/qwen3.5-flash": ModelMetadata(
        model_id="bailian1/qwen3.5-flash",
        provider="bailian",
        provider_model_id="qwen3.5-flash",
        display_name="Qwen3.5 Flash (阿里云百炼·文本成本主力)",
        modalities=[ModelModality.TEXT],
        capabilities=["chat", "function_calling"],
        context_window=32768,
        max_output_tokens=8192,
        tier=ModelTier.BASIC,
        quality_score=72.0,
        input_price=0.3,
        output_price=0.6,
        avg_latency_ms=900.0,
        p95_latency_ms=2500.0,
        regions=["cn-beijing", "cn-hangzhou"],
        description="百炼文本成本主力，输出¥2/百万token，冷启动主推",
        tags=["cost-optimized", "batch-processing"],
    ),
    "bailian1/qwen-long": ModelMetadata(
        model_id="bailian1/qwen-long",
        provider="bailian",
        provider_model_id="qwen-long",
        display_name="Qwen Long (Bailian long context free model)",
        modalities=[ModelModality.TEXT],
        capabilities=["chat", "long_context"],
        context_window=1000000,
        max_output_tokens=8192,
        tier=ModelTier.STANDARD,
        quality_score=85.0,
        input_price=0.0,  # free
        output_price=0.0,
        avg_latency_ms=2000.0,
        p95_latency_ms=5000.0,
        regions=["cn-beijing", "cn-hangzhou"],
        description="Qwen Long, long context model, 1M tokens free quota",
        tags=["free", "long-context", "document-processing"],
    ),
    "bailian1/qwen3.8-max": ModelMetadata(
        model_id="bailian1/qwen3.8-max",
        provider="bailian",
        provider_model_id="qwen3.8-max",
        display_name="Qwen3.8 Max (阿里云百炼·Qwen3系列高级模型)",
        modalities=[ModelModality.TEXT],
        capabilities=["chat", "function_calling", "structured_output"],
        context_window=131072,
        max_output_tokens=8192,
        tier=ModelTier.PREMIUM,
        quality_score=90.0,
        input_price=8.0,
        output_price=24.0,
        avg_latency_ms=2500.0,
        p95_latency_ms=6000.0,
        regions=["cn-beijing"],
        description="Qwen3系列高级模型，长文本支持，复杂推理",
        tags=["long-context", "complex-reasoning", "qwen3"],
    ),
    "bailian1/qwen3-30b": ModelMetadata(
        model_id="bailian1/qwen3-30b",
        provider="bailian",
        provider_model_id="qwen3-30b-a10b-instruct",
        display_name="Qwen3 30B (阿里云百炼·Qwen3系列)",
        modalities=[ModelModality.TEXT],
        capabilities=["chat", "function_calling"],
        context_window=32768,
        max_output_tokens=8192,
        tier=ModelTier.STANDARD,
        quality_score=82.0,
        input_price=1.0,
        output_price=3.0,
        avg_latency_ms=1500.0,
        p95_latency_ms=4000.0,
        regions=["cn-beijing"],
        description="Qwen3系列30B参数模型，平衡质量和成本",
        tags=["balanced", "qwen3"],
    ),
    "bailian1/deepseek-v4-flash": ModelMetadata(
        model_id="bailian1/deepseek-v4-flash",
        provider="bailian",
        provider_model_id="deepseek-v4-flash",
        display_name="DeepSeek V4 Flash (阿里云百炼·高性能备选)",
        modalities=[ModelModality.TEXT],
        capabilities=["chat", "function_calling", "thinking"],
        context_window=32768,
        max_output_tokens=8192,
        tier=ModelTier.STANDARD,
        quality_score=85.0,
        input_price=2.0,
        output_price=6.0,
        avg_latency_ms=1800.0,
        p95_latency_ms=4500.0,
        regions=["cn-beijing", "cn-hangzhou"],
        description="DeepSeek V4 Flash，高性能，非高峰时期使用",
        tags=["high-performance", "thinking", "non-peak"],
    ),
    "bailian1/deepseek-v3": ModelMetadata(
        model_id="bailian1/deepseek-v3",
        provider="bailian",
        provider_model_id="deepseek-v3",
        display_name="DeepSeek V3 (阿里云百炼·复杂推理)",
        modalities=[ModelModality.TEXT],
        capabilities=["chat", "function_calling", "thinking"],
        context_window=65536,
        max_output_tokens=8192,
        tier=ModelTier.PREMIUM,
        quality_score=90.0,
        input_price=4.0,
        output_price=16.0,
        avg_latency_ms=2500.0,
        p95_latency_ms=6000.0,
        regions=["cn-beijing"],
        description="DeepSeek V3，复杂推理和代码生成",
        tags=["complex-reasoning", "code", "thinking"],
    ),
    "bailian1/qwen-vl-max": ModelMetadata(
        model_id="bailian1/qwen-vl-max",
        provider="bailian",
        provider_model_id="qwen-vl-max",
        display_name="Qwen VL Max (阿里云百炼·视觉理解旗舰)",
        modalities=[ModelModality.MULTIMODAL],
        capabilities=["chat", "vision", "image_understanding"],
        context_window=32768,
        max_output_tokens=8192,
        tier=ModelTier.PREMIUM,
        quality_score=92.0,
        input_price=6.0,
        output_price=18.0,
        avg_latency_ms=2500.0,
        p95_latency_ms=6000.0,
        regions=["cn-beijing"],
        description="通义千问VL Max，视觉理解和图文分析",
        tags=["vision", "multimodal", "image-understanding"],
    ),
    "bailian1/qwen-vl-plus": ModelMetadata(
        model_id="bailian1/qwen-vl-plus",
        provider="bailian",
        provider_model_id="qwen-vl-plus",
        display_name="Qwen VL Plus (阿里云百炼·通用视觉任务)",
        modalities=[ModelModality.MULTIMODAL],
        capabilities=["chat", "vision", "image_understanding"],
        context_window=32768,
        max_output_tokens=8192,
        tier=ModelTier.STANDARD,
        quality_score=85.0,
        input_price=3.0,
        output_price=9.0,
        avg_latency_ms=1800.0,
        p95_latency_ms=4500.0,
        regions=["cn-beijing"],
        description="通义千问VL Plus，通用视觉任务",
        tags=["vision", "multimodal", "good-value"],
    ),
    "bailian1/qwen-coder-turbo": ModelMetadata(
        model_id="bailian1/qwen-coder-turbo",
        provider="bailian",
        provider_model_id="qwen-coder-turbo",
        display_name="Qwen Coder Turbo (阿里云百炼·代码生成)",
        modalities=[ModelModality.TEXT],
        capabilities=["chat", "code_generation", "function_calling"],
        context_window=65536,
        max_output_tokens=8192,
        tier=ModelTier.STANDARD,
        quality_score=85.0,
        input_price=1.0,
        output_price=3.0,
        avg_latency_ms=1500.0,
        p95_latency_ms=4000.0,
        regions=["cn-beijing"],
        description="通义千问Coder，代码生成和审查",
        tags=["code", "developer"],
    ),
    # ══════ Bailian 图像模型 ══════
    "bailian1/qwen-image-3.0-pro": ModelMetadata(
        model_id="bailian1/qwen-image-3.0-pro",
        provider="bailian",
        provider_model_id="qwen-image-3.0-pro",
        display_name="Qwen Image 3.0 Pro (阿里云百炼·高质量文生图)",
        modalities=[ModelModality.IMAGE],
        capabilities=["text_to_image", "image_to_image"],
        tier=ModelTier.PREMIUM,
        quality_score=90.0,
        input_price=0.0,
        output_price=400.0,  # ¥0.4/张
        avg_latency_ms=5000.0,
        p95_latency_ms=15000.0,
        regions=["cn-beijing", "cn-hangzhou"],
        description="Qwen Image 3.0 Pro，高质量文生图 ⭐推荐",
        tags=["recommended", "high-quality", "text-to-image"],
    ),
    "bailian1/wan2.7-image": ModelMetadata(
        model_id="bailian1/wan2.7-image",
        provider="bailian",
        provider_model_id="wan2.7-image",
        display_name="万相2.7 (阿里云百炼·图像生成)",
        modalities=[ModelModality.IMAGE],
        capabilities=["text_to_image", "image_to_image"],
        tier=ModelTier.STANDARD,
        quality_score=82.0,
        input_price=0.0,
        output_price=200.0,  # ¥0.2/张
        avg_latency_ms=4000.0,
        p95_latency_ms=12000.0,
        regions=["cn-beijing"],
        description="万相2.7图像生成，性价比高",
        tags=["good-value", "text-to-image"],
    ),
    "bailian1/wanx2.1-t2i-turbo": ModelMetadata(
        model_id="bailian1/wanx2.1-t2i-turbo",
        provider="bailian",
        provider_model_id="wanx2.1-t2i-turbo",
        display_name="万相2.1 T2I Turbo (阿里云百炼·快速文生图)",
        modalities=[ModelModality.IMAGE],
        capabilities=["text_to_image"],
        tier=ModelTier.BASIC,
        quality_score=75.0,
        input_price=0.0,
        output_price=100.0,  # ¥0.1/张
        avg_latency_ms=2000.0,
        p95_latency_ms=6000.0,
        regions=["cn-beijing"],
        description="万相2.1 T2I Turbo，快速文生图，成本低",
        tags=["fast", "low-cost", "text-to-image"],
    ),
    # ══════ Bailian 视频模型（与credits_engine对齐）══════
    "bailian1/wan3.0-video": ModelMetadata(
        model_id="bailian1/wan3.0-video",
        provider="bailian",
        provider_model_id="wan3.0-video",
        display_name="万相3.0 (阿里云百炼·视频生成)",
        modalities=[ModelModality.VIDEO],
        capabilities=["text_to_video", "image_to_video", "reference_to_video"],
        tier=ModelTier.STANDARD,
        quality_score=85.0,
        input_price=0.0,
        output_price=0.0,  # 按秒计费，在credits_engine中
        avg_latency_ms=60000.0,
        p95_latency_ms=180000.0,
        regions=["cn-beijing"],
        credits_engine_id="wan3.0-video",
        description="万相3.0视频生成，支持文生/图生/参考生视频，9cr/s",
        tags=["video", "async", "standard-tier"],
    ),
    "bailian1/minimax-h3": ModelMetadata(
        model_id="bailian1/minimax-h3",
        provider="bailian",
        provider_model_id="MiniMax/MiniMax-H3",
        display_name="MiniMax H3 (阿里云百炼·视频生成)",
        modalities=[ModelModality.VIDEO],
        capabilities=["text_to_video", "image_to_video"],
        tier=ModelTier.STANDARD,
        quality_score=82.0,
        input_price=0.0,
        output_price=0.0,
        avg_latency_ms=45000.0,
        p95_latency_ms=120000.0,
        regions=["cn-beijing"],
        credits_engine_id="minimax-h3",
        description="MiniMax H3视频生成，11cr/s，单段上限15s",
        tags=["video", "async", "minimax"],
    ),
    "bailian1/minimax-h3-max": ModelMetadata(
        model_id="bailian1/minimax-h3-max",
        provider="bailian",
        provider_model_id="MiniMax/MiniMax-H3-Max",
        display_name="MiniMax H3 Max (阿里云百炼·视频生成基础档)",
        modalities=[ModelModality.VIDEO],
        capabilities=["text_to_video", "image_to_video"],
        tier=ModelTier.BASIC,
        quality_score=78.0,
        input_price=0.0,
        output_price=0.0,
        avg_latency_ms=30000.0,
        p95_latency_ms=90000.0,
        regions=["cn-beijing"],
        credits_engine_id="minimax-h3-max",
        description="MiniMax H3 Max，8cr/s，480P基础档",
        tags=["video", "async", "low-cost", "minimax"],
    ),
    "bailian1/wan2.2-video": ModelMetadata(
        model_id="bailian1/wan2.2-video",
        provider="bailian",
        provider_model_id="wan2.2-video",
        display_name="万相2.2 (阿里云百炼·短视频生成)",
        modalities=[ModelModality.VIDEO],
        capabilities=["text_to_video", "image_to_video"],
        tier=ModelTier.BASIC,
        quality_score=75.0,
        input_price=0.0,
        output_price=0.0,
        avg_latency_ms=30000.0,
        p95_latency_ms=90000.0,
        regions=["cn-beijing"],
        description="万相2.2短视频生成，≤5s，成本低",
        tags=["video", "async", "short-video", "low-cost"],
    ),
    # ══════ Bailian 音频模型 ══════
    "bailian1/minimax-speech-2.8-turbo": ModelMetadata(
        model_id="bailian1/minimax-speech-2.8-turbo",
        provider="bailian",
        provider_model_id="MiniMax/speech-2.8-turbo",
        display_name="MiniMax Speech 2.8 Turbo (阿里云百炼·语音合成/识别)",
        modalities=[ModelModality.AUDIO],
        capabilities=["text_to_speech", "speech_to_text"],
        tier=ModelTier.STANDARD,
        quality_score=85.0,
        input_price=0.0,
        output_price=0.0,
        avg_latency_ms=2000.0,
        p95_latency_ms=5000.0,
        regions=["cn-beijing"],
        description="MiniMax语音2.8 Turbo，TTS语音合成和ASR语音识别",
        tags=["audio", "tts", "asr", "minimax"],
    ),
    # ══════ Agnes 模型 ══════
    "agnes/agnes-2.0-flash": ModelMetadata(
        model_id="agnes/agnes-2.0-flash",
        provider="agnes",
        provider_model_id="agnes-2.0-flash",
        display_name="Agnes 2.0 Flash (Agnes AI·创作中心首选)",
        modalities=[ModelModality.TEXT],
        capabilities=["chat", "function_calling", "thinking"],
        context_window=32768,
        max_output_tokens=8192,
        tier=ModelTier.STANDARD,
        quality_score=80.0,
        input_price=0.0,  # 免费无限量
        output_price=0.0,
        avg_latency_ms=1500.0,
        p95_latency_ms=4000.0,
        regions=["global"],
        description="Agnes AI创作中心首选，免费无限量",
        tags=["free", "unlimited", "creative"],
    ),
    "volcengine/seedance-2-mini": ModelMetadata(
        model_id="volcengine/seedance-2-mini",
        provider="agnes",
        provider_model_id="seedance-2-mini",
        display_name="Seedance 2 Mini (Agnes AI·快速视频生成)",
        modalities=[ModelModality.VIDEO],
        capabilities=["text_to_video", "image_to_video"],
        tier=ModelTier.STANDARD,
        quality_score=80.0,
        input_price=0.0,
        output_price=0.0,
        avg_latency_ms=30000.0,
        p95_latency_ms=90000.0,
        regions=["global"],
        credits_engine_id="seedance-2-mini",
        description="Seedance 2 Mini，快速视频生成，6cr/s，≤5s ⭐短剧默认",
        tags=["video", "async", "fast", "default"],
    ),
    "agnes/seedance-2-5": ModelMetadata(
        model_id="agnes/seedance-2-5",
        provider="agnes",
        provider_model_id="seedance-2-5",
        display_name="Seedance 2.5 (Agnes AI·高质量视频生成)",
        modalities=[ModelModality.VIDEO],
        capabilities=["text_to_video", "image_to_video", "reference_to_video"],
        tier=ModelTier.FLAGSHIP,
        quality_score=92.0,
        input_price=0.0,
        output_price=0.0,
        avg_latency_ms=60000.0,
        p95_latency_ms=180000.0,
        regions=["global"],
        credits_engine_id="seedance-2-5",
        description="Seedance 2.5，高质量视频生成，26cr/s，≤10s",
        tags=["video", "async", "high-quality", "flagship"],
    ),
    "agnes/agnes-image-2.1-flash": ModelMetadata(
        model_id="agnes/agnes-image-2.1-flash",
        provider="agnes",
        provider_model_id="agnes-image-2.1-flash",
        display_name="Agnes Image 2.1 Flash (Agnes AI·文生图)",
        modalities=[ModelModality.IMAGE],
        capabilities=["text_to_image"],
        tier=ModelTier.STANDARD,
        quality_score=82.0,
        input_price=0.0,
        output_price=0.0,
        avg_latency_ms=4000.0,
        p95_latency_ms=12000.0,
        regions=["global"],
        description="Agnes文生图，免费额度",
        tags=["image", "free-quota"],
    ),
    # ══════ NVIDIA 模型 ══════
    "nvidia/llama-3.1-8b": ModelMetadata(
        model_id="nvidia/llama-3.1-8b",
        provider="nvidia",
        provider_model_id="meta/llama-3.1-8b-instruct",
        display_name="Llama 3.1 8B (NVIDIA·海外兜底)",
        modalities=[ModelModality.TEXT],
        capabilities=["chat"],
        context_window=8192,
        max_output_tokens=4096,
        tier=ModelTier.BASIC,
        quality_score=70.0,
        input_price=0.0,  # 免费1000 req/day
        output_price=0.0,
        avg_latency_ms=1000.0,
        p95_latency_ms=3000.0,
        regions=["us-west-1"],
        description="NVIDIA NIM Llama 3.1 8B，海外兜底，免费1000 req/day",
        tags=["free-quota", "overseas", "fallback"],
    ),
}


# ═══════════════════════════════════════════════════════════════
# 5. 场景化降级路径配置
# ═══════════════════════════════════════════════════════════════

# 基于场景的自动降级路径
# 当首选模型失败（额度不足/故障/限流）时，按顺序尝试下一个模型
DEGRADATION_PATHS: dict[str, list[str]] = {
    # 短剧相关
    # 大厂做法：免费模型优先，付费模型兜底，最大化利用率、最小化成本
    "drama_script_analysis": [
        "agnes/agnes-2.0-flash",  # 免费模型优先（Agnes AI 免费无限量）
        "bailian1/qwen-long",  # 免费长上下文模型（100万token）
        "bailian1/qwen3.7-flash",  # 免费高效模型
        "bailian1/qwen-turbo",  # 性价比模型
        "bailian1/deepseek-v4-flash",  # 高性能备选
        "bailian1/qwen-plus",  # 能力增强模型
        # 多账号备用（不同百炼账号，负载均衡+故障转移）
        "bailian2/qwen-long",  # 备用账号1 长上下文
        "bailian2/qwen3.7-flash",  # 备用账号1 高效模型
        "bailian2/qwen-turbo",  # 备用账号1 性价比
        # 多渠道备用（百炼挂了自动切换）
        "openrouter/deepseek-chat",  # OpenRouter 备用渠道
        "siliconflow/deepseek-chat",  # SiliconFlow 备用渠道
    ],
    "drama_storyboard": [
        "agnes/agnes-2.0-flash",  # 免费模型优先
        "bailian1/qwen3.7-flash",  # 免费高效模型
        "bailian1/qwen-turbo",  # 性价比模型
        "bailian1/qwen-plus",  # 能力增强模型（付费兜底）
    ],
    "drama_video_generation": [
        "volcengine/seedance-2-mini",
        "bailian1/wan3.0-video",
        "bailian1/minimax-h3",
        "bailian1/minimax-h3-max",
    ],
    # 小说相关
    "novel_chapter_writing": [
        "agnes/agnes-2.0-flash",  # 免费模型优先
        "bailian1/qwen-long",  # 免费长上下文模型
        "bailian1/qwen3.7-flash",  # 免费高效模型
        "bailian1/qwen-turbo",  # 性价比模型
        "bailian1/qwen-plus",  # 能力增强模型
        # 多账号备用（不同百炼账号，负载均衡+故障转移）
        "bailian2/qwen-long",  # 备用账号1 长上下文
        "bailian2/qwen3.7-flash",  # 备用账号1 高效模型
        "bailian2/qwen-turbo",  # 备用账号1 性价比
        # 多渠道备用
        "openrouter/deepseek-chat",  # OpenRouter 备用渠道
        "siliconflow/deepseek-chat",  # SiliconFlow 备用渠道
    ],
    # 漫画相关
    "comics_script_analysis": [
        "agnes/agnes-2.0-flash",  # 免费模型优先（Agnes AI 免费无限量）
        "bailian1/qwen-long",  # 免费长上下文模型（100万token）
        "bailian1/qwen3.7-flash",  # 免费高效模型
        "bailian1/qwen-turbo",  # 性价比模型
        "bailian1/deepseek-v4-flash",  # 高性能备选
        "bailian1/qwen-plus",  # 能力增强模型（付费兜底）
        # 多账号备用（不同百炼账号，负载均衡+故障转移）
        "bailian2/qwen-long",  # 备用账号1 长上下文
        "bailian2/qwen3.7-flash",  # 备用账号1 高效模型
        "bailian2/qwen-turbo",  # 备用账号1 性价比
        # 多渠道备用（百炼挂了自动切换）
        "openrouter/deepseek-chat",  # OpenRouter 备用渠道
        "siliconflow/deepseek-chat",  # SiliconFlow 备用渠道
    ],
    "comics_image_generation": [
        "agnes/agnes-image-2.1-flash",  # 免费图像生成模型优先
        "bailian1/qwen-image-3.0-pro",
        "bailian1/wan2.7-image",
    ],
    # 音乐相关
    "music_generation": [
        "bailian1/minimax-speech-2.8-turbo",
        "bailian1/qwen-audio-turbo",
    ],
    "music_lyrics_writing": [
        "agnes/agnes-2.0-flash",  # 免费模型优先
        "bailian1/qwen-long",  # 免费长上下文模型
        "bailian1/qwen3.7-flash",  # 免费高效模型
        "bailian1/qwen-turbo",  # 性价比模型
        "bailian1/deepseek-v4-flash",  # 高性能备选
        "bailian1/qwen-plus",  # 能力增强模型（付费兜底）
        # 多账号备用（不同百炼账号，负载均衡+故障转移）
        "bailian2/qwen-long",  # 备用账号1 长上下文
        "bailian2/qwen3.7-flash",  # 备用账号1 高效模型
        "bailian2/qwen-turbo",  # 备用账号1 性价比
        # 多渠道备用
        "openrouter/deepseek-chat",  # OpenRouter 备用渠道
        "siliconflow/deepseek-chat",  # SiliconFlow 备用渠道
    ],
    # 互动影游
    "interactive_branch_story": [
        "agnes/agnes-2.0-flash",  # 免费模型优先
        "bailian1/qwen-long",  # 免费长上下文模型
        "bailian1/qwen3.7-flash",  # 免费高效模型
        "bailian1/qwen-turbo",  # 性价比模型
        "bailian1/deepseek-v4-flash",  # 高性能备选
        "bailian1/qwen-plus",  # 能力增强模型（付费兜底）
        # 多账号备用（不同百炼账号，负载均衡+故障转移）
        "bailian2/qwen-long",  # 备用账号1 长上下文
        "bailian2/qwen3.7-flash",  # 备用账号1 高效模型
        "bailian2/qwen-turbo",  # 备用账号1 性价比
        # 多渠道备用
        "openrouter/deepseek-chat",  # OpenRouter 备用渠道
        "siliconflow/deepseek-chat",  # SiliconFlow 备用渠道
    ],
    # 多语言翻译
    "multilingual_translation": [
        "agnes/agnes-2.0-flash",  # 免费模型优先
        "bailian1/qwen-long",  # 免费长上下文模型
        "bailian1/qwen3.7-flash",  # 免费高效模型
        "bailian1/qwen-turbo",  # 性价比模型
        "bailian1/qwen-plus",  # 能力增强模型
        # 多账号备用
        "bailian2/qwen-long",  # 备用账号1 长上下文
        "bailian2/qwen3.7-flash",  # 备用账号1 高效模型
        "bailian2/qwen-turbo",  # 备用账号1 性价比
    ],
    # 客服对话
    "customer_support_chat": [
        "bailian1/qwen3.7-flash",
        "bailian1/qwen-turbo",
        "agnes/agnes-2.0-flash",
    ],
    # 通用默认
    "default_text": [
        "bailian1/qwen-turbo",
        "bailian1/qwen3.7-flash",
        "bailian1/qwen-plus",
        "agnes/agnes-2.0-flash",
    ],
}


def get_degradation_path(scenario: str) -> list[str]:
    """获取场景的降级路径

    Args:
        scenario: 场景名称（如 drama_script_analysis）

    Returns:
        按优先级排序的模型ID列表
    """
    return DEGRADATION_PATHS.get(scenario, DEGRADATION_PATHS["default_text"]).copy()


# ═══════════════════════════════════════════════════════════════
# 6. 模型查询接口
# ═══════════════════════════════════════════════════════════════


def get_model_metadata(model_id: str) -> ModelMetadata | None:
    """获取模型元数据

    Args:
        model_id: 模型ID（支持旧ID和统一ID）

    Returns:
        模型元数据，如果不存在返回None
    """
    normalized = normalize_model_id(model_id)
    return MODEL_REGISTRY.get(normalized)


def list_models_by_modality(modality: ModelModality) -> list[ModelMetadata]:
    """按模态列出所有可用模型

    Args:
        modality: 模型模态

    Returns:
        该模态的所有模型元数据列表
    """
    return [m for m in MODEL_REGISTRY.values() if modality in m.modalities and m.status == ModelStatus.ACTIVE]


def list_models_by_tier(tier: ModelTier) -> list[ModelMetadata]:
    """按等级列出所有可用模型"""
    return [m for m in MODEL_REGISTRY.values() if m.tier == tier and m.status == ModelStatus.ACTIVE]


def list_models_by_provider(provider: str) -> list[ModelMetadata]:
    """按厂商列出所有可用模型"""
    return [m for m in MODEL_REGISTRY.values() if m.provider == provider and m.status == ModelStatus.ACTIVE]


def get_model_count() -> dict[str, int]:
    """获取模型统计信息"""
    return {
        "total": len(MODEL_REGISTRY),
        "text": len(list_models_by_modality(ModelModality.TEXT)),
        "image": len(list_models_by_modality(ModelModality.IMAGE)),
        "video": len(list_models_by_modality(ModelModality.VIDEO)),
        "audio": len(list_models_by_modality(ModelModality.AUDIO)),
        "multimodal": len(list_models_by_modality(ModelModality.MULTIMODAL)),
        "bailian": len(list_models_by_provider("bailian")),
        "agnes": len(list_models_by_provider("agnes")),
        "nvidia": len(list_models_by_provider("nvidia")),
    }


# ═══════════════════════════════════════════════════════════════
# 7. 模型健康度与额度状态管理
# ═══════════════════════════════════════════════════════════════

# 调用统计：{model_id: {"success": int, "fail": int, "total_latency_ms": float, "last_call": float}}
_call_stats: dict[str, dict] = {}


def record_model_call(model_id: str, success: bool, latency_ms: float = 0.0, error_type: str | None = None) -> None:
    """记录模型调用结果，用于健康度自动更新

    Args:
        model_id: 统一模型ID（如 bailian/qwen-plus）
        success: 是否成功
        latency_ms: 延迟（毫秒）
        error_type: 错误类型（quota_exhausted/rate_limit/server_error/other）
    """
    normalized = normalize_model_id(model_id)
    now = time.time()

    if normalized not in _call_stats:
        _call_stats[normalized] = {
            "success": 0,
            "fail": 0,
            "total_latency_ms": 0.0,
            "last_call": now,
            "last_error": None,
            "last_error_time": 0,
        }

    stats = _call_stats[normalized]
    if success:
        stats["success"] += 1
        stats["total_latency_ms"] += latency_ms
    else:
        stats["fail"] += 1
        stats["last_error"] = error_type
        stats["last_error_time"] = now

    stats["last_call"] = now

    # 额度耗尽标记：402/insufficient_balance 错误直接标记
    if error_type in ("quota_exhausted", "insufficient_balance", "402"):
        _update_model_quota_status(normalized, "exhausted")
        logger.warning(f"[model-health] {normalized} 额度耗尽，已标记为 exhausted")

    # 定期更新健康度（每10次调用更新一次）
    total_calls = stats["success"] + stats["fail"]
    if total_calls % 10 == 0:
        _update_model_health(normalized)


def _update_model_quota_status(model_id: str, status: str) -> None:
    """更新模型额度状态"""
    model_meta = MODEL_REGISTRY.get(model_id)
    if model_meta:
        old_status = model_meta.quota_status
        model_meta.quota_status = status
        if old_status != status:
            logger.info(f"[model-health] {model_id} 额度状态: {old_status} → {status}")


def _update_model_health(model_id: str) -> None:
    """根据调用统计更新模型健康度评分"""
    model_meta = MODEL_REGISTRY.get(model_id)
    if not model_meta:
        return

    stats = _call_stats.get(model_id)
    if not stats:
        return

    total = stats["success"] + stats["fail"]
    if total == 0:
        return

    # 成功率（权重60%）
    success_rate = stats["success"] / total
    # 平均延迟（权重40%，越低越好）
    avg_latency = stats["total_latency_ms"] / stats["success"] if stats["success"] > 0 else 99999
    latency_score = max(0, 100 - (avg_latency / 100))  # 100ms以内满分，每超100ms扣1分

    health_score = (success_rate * 60) + (latency_score * 0.4)
    model_meta.health_score = round(health_score, 1)

    # 根据健康度更新状态
    if health_score < 30:
        model_meta.status = ModelStatus.DEGRADED
    elif health_score >= 80 and model_meta.status == ModelStatus.DEGRADED:
        model_meta.status = ModelStatus.ACTIVE

    logger.debug(f"[model-health] {model_id}: success_rate={success_rate:.2%}, avg_latency={avg_latency:.0f}ms, health_score={health_score:.1f}")


def reset_model_quota_status(model_id: str) -> None:
    """重置模型额度状态（用于额度充值后恢复）"""
    normalized = normalize_model_id(model_id)
    _update_model_quota_status(normalized, "sufficient")
    # 重置调用统计
    if normalized in _call_stats:
        _call_stats[normalized]["fail"] = 0
        _call_stats[normalized]["last_error"] = None
    logger.info(f"[quota] 已重置模型额度状态: {normalized}")


def reset_provider_quota_status(provider: str) -> int:
    """批量重置指定厂商的所有模型额度状态

    Args:
        provider: 厂商名称（bailian/agnes/nvidia等）

    Returns:
        重置的模型数量
    """
    count = 0
    for model_id, model_meta in MODEL_REGISTRY.items():
        if model_meta.provider == provider:
            _update_model_quota_status(model_id, "sufficient")
            if model_id in _call_stats:
                _call_stats[model_id]["fail"] = 0
                _call_stats[model_id]["last_error"] = None
            count += 1
    logger.info(f"[quota] 已批量重置厂商 {provider} 的 {count} 个模型额度状态")
    return count


def reset_all_quota_status() -> int:
    """重置所有模型额度状态（用于全局额度充值后恢复）

    Returns:
        重置的模型数量
    """
    count = 0
    for model_id in MODEL_REGISTRY:
        _update_model_quota_status(model_id, "sufficient")
        if model_id in _call_stats:
            _call_stats[model_id]["fail"] = 0
            _call_stats[model_id]["last_error"] = None
        count += 1
    logger.info(f"[quota] 已重置全部 {count} 个模型额度状态")
    return count


def get_exhausted_models() -> list[str]:
    """获取所有额度耗尽的模型列表"""
    return [model_id for model_id, model_meta in MODEL_REGISTRY.items() if model_meta.quota_status == "exhausted"]


def get_quota_summary() -> dict:
    """获取额度状态汇总"""
    summary = {"sufficient": 0, "low": 0, "exhausted": 0, "unknown": 0}
    for model_meta in MODEL_REGISTRY.values():
        status = model_meta.quota_status
        if status in summary:
            summary[status] += 1
        else:
            summary["unknown"] += 1
    summary["total"] = len(MODEL_REGISTRY)
    return summary


def get_model_health_report() -> dict:
    """获取所有模型的健康度报告"""
    report = {}
    for model_id, model_meta in MODEL_REGISTRY.items():
        stats = _call_stats.get(model_id, {})
        report[model_id] = {
            "display_name": model_meta.display_name,
            "status": model_meta.status.value,
            "health_score": model_meta.health_score,
            "quota_status": model_meta.quota_status,
            "tier": model_meta.tier.value,
            "success_calls": stats.get("success", 0),
            "fail_calls": stats.get("fail", 0),
            "last_error": stats.get("last_error"),
        }
    return report


# ═══════════════════════════════════════════════════════════════
# 8. 智能路由策略（Smart Routing Strategy）
# ═══════════════════════════════════════════════════════════════


class RoutingStrategy(StrEnum):
    """路由策略类型

    参考海内外大厂做法（OpenAI Router、AWS Bedrock、阿里云百炼网关）：
    - cost_first: 成本优先，选择最便宜的可用模型（适合高并发、批量处理）
    - quality_first: 质量优先，选择质量最高的模型（适合复杂推理、高质量创作）
    - speed_first: 速度优先，选择延迟最低的模型（适合实时对话、交互式应用）
    - balanced: 平衡策略，综合考虑成本、质量、速度（默认策略）
    - custom: 自定义策略，按优先级列表选择
    """

    COST_FIRST = "cost_first"
    QUALITY_FIRST = "quality_first"
    SPEED_FIRST = "speed_first"
    BALANCED = "balanced"
    CUSTOM = "custom"


# 模型使用统计：{model_id: {"input_tokens": int, "output_tokens": int, "calls": int, "total_cost": float}}
_usage_stats: dict[str, dict] = {}


def record_model_usage(model_id: str, input_tokens: int = 0, output_tokens: int = 0) -> None:
    """记录模型使用量（用于额度估算和成本统计）

    Args:
        model_id: 统一模型ID
        input_tokens: 输入token数
        output_tokens: 输出token数
    """
    normalized = normalize_model_id(model_id)
    if normalized not in _usage_stats:
        _usage_stats[normalized] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "calls": 0,
            "total_cost": 0.0,
            "last_used": 0.0,
        }

    stats = _usage_stats[normalized]
    stats["input_tokens"] += input_tokens
    stats["output_tokens"] += output_tokens
    stats["calls"] += 1
    stats["last_used"] = time.time()

    # 估算成本
    model_meta = MODEL_REGISTRY.get(normalized)
    if model_meta:
        cost = input_tokens / 1_000_000 * model_meta.input_price + output_tokens / 1_000_000 * model_meta.output_price
        stats["total_cost"] += cost


def get_usage_stats() -> dict:
    """获取所有模型的使用统计"""
    return dict(_usage_stats)


def get_model_usage(model_id: str) -> dict | None:
    """获取指定模型的使用统计"""
    normalized = normalize_model_id(model_id)
    return _usage_stats.get(normalized)


def select_model_by_strategy(
    modality: ModelModality,
    strategy: RoutingStrategy = RoutingStrategy.BALANCED,
    custom_priority: list[str] | None = None,
) -> ModelMetadata | None:
    """根据路由策略选择最优模型

    参考海内外大厂智能网关做法，综合考虑成本、质量、速度、健康度。

    Args:
        modality: 模型模态（text/image/video/audio）
        strategy: 路由策略
        custom_priority: 自定义优先级列表（仅 strategy=CUSTOM 时使用）

    Returns:
        选中的模型元数据，无可用模型返回None
    """
    # 获取该模态的所有可用模型
    candidates = [m for m in MODEL_REGISTRY.values() if modality in m.modalities and m.status == ModelStatus.ACTIVE and m.quota_status != "exhausted"]

    if not candidates:
        return None

    if strategy == RoutingStrategy.CUSTOM and custom_priority:
        # 自定义策略：按优先级列表选择第一个可用模型
        for model_id in custom_priority:
            normalized = normalize_model_id(model_id)
            for m in candidates:
                if m.model_id == normalized:
                    return m
        return candidates[0]

    if strategy == RoutingStrategy.COST_FIRST:
        # 成本优先：选择总成本最低的模型（输入+输出价格）
        return min(candidates, key=lambda m: m.input_price + m.output_price)

    if strategy == RoutingStrategy.QUALITY_FIRST:
        # 质量优先：选择质量评分最高的模型
        return max(candidates, key=lambda m: m.quality_score)

    if strategy == RoutingStrategy.SPEED_FIRST:
        # 速度优先：选择平均延迟最低的模型
        return min(candidates, key=lambda m: m.avg_latency_ms)

    # BALANCED：平衡策略，综合评分 = 质量40% + 成本30% + 速度30%
    def balanced_score(m: ModelMetadata) -> float:
        # 质量评分（0-100，越高越好）
        quality = m.quality_score
        # 成本评分（价格越低分越高，归一化到0-100）
        max_price = max(c.input_price + c.output_price for c in candidates) or 1
        cost_score = 100 - (m.input_price + m.output_price) / max_price * 100
        # 速度评分（延迟越低分越高，归一化到0-100）
        max_latency = max(c.avg_latency_ms for c in candidates) or 1
        speed_score = 100 - m.avg_latency_ms / max_latency * 100
        # 健康度加成
        health_bonus = m.health_score * 0.1
        return quality * 0.4 + cost_score * 0.3 + speed_score * 0.3 + health_bonus

    return max(candidates, key=balanced_score)


def get_routing_recommendation(modality: ModelModality) -> dict:
    """获取路由推荐（各策略下的最优模型）

    用于管理后台展示和运维决策。
    """
    recommendations = {}
    for strategy in RoutingStrategy:
        if strategy == RoutingStrategy.CUSTOM:
            continue
        model = select_model_by_strategy(modality, strategy)
        if model:
            recommendations[strategy.value] = {
                "model_id": model.model_id,
                "display_name": model.display_name,
                "tier": model.tier.value,
                "quality_score": model.quality_score,
                "input_price": model.input_price,
                "output_price": model.output_price,
                "avg_latency_ms": model.avg_latency_ms,
                "health_score": model.health_score,
            }
    return recommendations


# ═══════════════════════════════════════════════════════════════
# 9. 初始化与健康检查
# ═══════════════════════════════════════════════════════════════


def init_model_registry() -> None:
    """初始化模型注册表（记录统计信息）"""
    stats = get_model_count()
    logger.info(f"Model Registry initialized: {stats['total']} models (text={stats['text']}, image={stats['image']}, video={stats['video']}, audio={stats['audio']}, multimodal={stats['multimodal']})")
    logger.info(f"  Providers: bailian={stats['bailian']}, agnes={stats['agnes']}, nvidia={stats['nvidia']}")
    logger.info(f"  Aliases: {len(MODEL_ALIASES)} mappings")
    logger.info(f"  Degradation paths: {len(DEGRADATION_PATHS)} scenarios")


# 模块加载时自动初始化
init_model_registry()
