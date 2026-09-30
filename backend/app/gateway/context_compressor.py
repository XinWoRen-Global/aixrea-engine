"""
Context Compressor — 上下文压缩策略（参考 SoL-Pi 机制 #3）

长任务（如短剧生成，10+ 步骤）会不断累积 context，token 消耗随步骤线性增长。
压缩规则：
- 已完成的步骤只保留结论，丢弃中间过程
- 关键节点（如用户确认点）保留完整上下文
- 大输出（>500 tokens）只保留摘要和引用 ID

预期收益：长任务 token 消耗降低 30-40%

参考：https://github.com/NVlabs/SoL-Pi
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("context_compressor")

# 压缩阈值
MAX_CONTEXT_TOKENS = 8000  # 超过此值触发压缩
SUMMARY_THRESHOLD = 500  # 单条消息超过此 tokens 视为大输出
KEEP_RECENT_MESSAGES = 6  # 始终保留最近 N 条消息
KEEP_SYSTEM_MESSAGES = True  # 始终保留 system 消息


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中文约 1.5 字/token，英文约 4 字符/token）。"""
    if not text:
        return 0
    # 简化：中文字符数 / 1.5 + 英文单词数
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    other_chars = len(text) - chinese_chars
    return int(chinese_chars / 1.5 + other_chars / 4)


def should_compress(messages: list[dict[str, Any]]) -> bool:
    """判断是否需要压缩上下文。"""
    total_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)
    return total_tokens > MAX_CONTEXT_TOKENS


def summarize_message(content: str, max_length: int = 200) -> str:
    """生成消息摘要（保留关键信息，截断中间过程）。

    简化版：保留开头和结尾，中间用省略号代替。
    后续可用 LLM 生成更精准的摘要。
    """
    if not content:
        return ""
    if estimate_tokens(content) <= SUMMARY_THRESHOLD:
        return content

    # 保留开头 100 字和结尾 100 字
    if len(content) > 200:
        return content[:100] + f"\n...[已压缩，原内容 {estimate_tokens(content)} tokens]...\n" + content[-100:]
    return content


def compress_messages(
    messages: list[dict[str, Any]],
    keep_recent: int = KEEP_RECENT_MESSAGES,
    keep_system: bool = KEEP_SYSTEM_MESSAGES,
) -> list[dict[str, Any]]:
    """压缩消息列表。

    策略：
    1. 始终保留最近 N 条消息
    2. 始终保留 system 消息
    3. 较早的 user/assistant 消息只保留摘要
    4. 大输出（>500 tokens）只保留摘要和引用 ID

    Args:
        messages: 原始消息列表
        keep_recent: 保留最近 N 条
        keep_system: 是否保留 system 消息

    Returns:
        压缩后的消息列表
    """
    if not should_compress(messages):
        return messages

    if len(messages) <= keep_recent:
        return messages

    compressed = []
    recent_start = len(messages) - keep_recent

    for i, msg in enumerate(messages):
        role = msg.get("role", "")

        # 保留最近的消息
        if i >= recent_start:
            compressed.append(msg)
            continue

        # 保留 system 消息
        if keep_system and role == "system":
            compressed.append(msg)
            continue

        # 压缩较早的消息
        content = msg.get("content", "")
        if estimate_tokens(content) > SUMMARY_THRESHOLD:
            summary = summarize_message(content)
            compressed.append(
                {
                    **msg,
                    "content": summary,
                    "_compressed": True,
                    "_original_tokens": estimate_tokens(content),
                }
            )
        else:
            compressed.append(msg)

    original_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)
    compressed_tokens = sum(estimate_tokens(m.get("content", "")) for m in compressed)
    saved = original_tokens - compressed_tokens

    if saved > 0:
        logger.info(
            "Context compressed: %d -> %d tokens (saved %d, %.1f%%)",
            original_tokens,
            compressed_tokens,
            saved,
            saved / original_tokens * 100 if original_tokens else 0,
        )

    return compressed


def get_compression_stats(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """获取压缩统计信息（用于监控和优化）。"""
    original_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)
    compressed = compress_messages(messages)
    compressed_tokens = sum(estimate_tokens(m.get("content", "")) for m in compressed)
    return {
        "original_tokens": original_tokens,
        "compressed_tokens": compressed_tokens,
        "saved_tokens": original_tokens - compressed_tokens,
        "saved_percentage": (original_tokens - compressed_tokens) / original_tokens * 100 if original_tokens else 0,
        "message_count": len(messages),
        "compressed_count": len(compressed),
        "needs_compression": should_compress(messages),
    }
