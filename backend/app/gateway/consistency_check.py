"""片段一致性评分（P2 第三刀 · 2026-09-04）。

方案 §5.4 落地：生成后由视觉模型逐片段评分（角色外观/场景/光影/分支衔接），
低于阈值的片段触发一次重生成。¥0.5/秒的成本使重试在经济上可承受——
这是 Seedance 时代做不到的（决策文档原文）。

设计红线：
  - **fail-open**：评分任何环节失败（模型不可用/解析失败/超时）返回 None，
    生成链路照常出片——评分是质量增强，不是发布闸门；
  - **预算闸**：重生成次数由调用方钳制（默认每片段最多 1 次重试），
    最坏 2× 单片段成本，叠加矩阵 cap 24 全局有界；
  - 模型经 MultiVendorPool 区域路由（qwen-vl 默认 cn），env 可覆写。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re

logger = logging.getLogger("gateway.consistency_check")

DEFAULT_MODEL = "qwen-vl-max"
DEFAULT_REGION = "cn"
SCORE_TIMEOUT = 90.0


def _model() -> str:
    return (os.environ.get("INTERACTIVE_CONSISTENCY_MODEL") or "").strip() or DEFAULT_MODEL


def _region() -> str:
    return (os.environ.get("INTERACTIVE_CONSISTENCY_REGION") or "").strip() or DEFAULT_REGION


def threshold() -> float:
    """合格分数线（0-10），env INTERACTIVE_CONSISTENCY_THRESHOLD，默认 6。"""
    raw = (os.environ.get("INTERACTIVE_CONSISTENCY_THRESHOLD") or "").strip()
    try:
        v = float(raw) if raw else 6.0
    except ValueError:
        v = 6.0
    return max(0.0, min(10.0, v))


def max_regen() -> int:
    """每片段最大重生成次数，env INTERACTIVE_CONSISTENCY_MAX_RETRY，默认 1。"""
    raw = (os.environ.get("INTERACTIVE_CONSISTENCY_MAX_RETRY") or "").strip()
    try:
        return max(0, min(3, int(raw))) if raw else 1
    except ValueError:
        return 1


def build_scoring_prompt(branch_name: str, segment_desc: str) -> str:
    """评分 prompt：给视觉模型结构化评分维度 + 强制输出格式。"""
    ctx = ""
    if branch_name:
        ctx += f"剧情分支：{branch_name}。"
    if segment_desc:
        ctx += f"片段内容：{segment_desc[:200]}。"
    return (
        "你是互动影游的片段质量审核员。前几张图是角色/场景参考图，后面是本片段视频的"
        "首帧和尾帧截图。请从四个维度各 0-10 分评估：1) 角色外观与参考图一致性；"
        "2) 场景与光影连贯性；3) 画面叙事是否匹配片段内容；4) 整体可用性（无明显崩坏/伪影）。"
        f"{ctx}\n"
        "只输出一行：SCORE: <0-10 的数字>（保留一位小数），不要任何其他文字。"
    )


def parse_score(text: str) -> float | None:
    """从模型输出鲁棒解析 0-10 分。解析不出 / 越界返回 None。

    兼容格式：SCORE: 8 / score: 7.5 / 6/10 / 得分：6 分 / 评分 7.5。
    """
    if not text:
        return None
    m = re.search(r"SCORE\s*[:：]?\s*(-?\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if not m:
        m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:/|分|out of|points?)\s*(?:10)?", text, re.IGNORECASE)
    if not m and re.search(r"score|得分|评分", text, re.IGNORECASE):
        # 上下文兜底：取文本中最后一个 0-10 的数
        nums = re.findall(r"\d+(?:\.\d+)?", text)
        for n in reversed(nums):
            v = float(n)
            if 0.0 <= v <= 10.0:
                return v
        return None
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    if 0.0 <= v <= 10.0:
        return v
    return None


async def score_segment(
    pool,
    frame_urls: list[str],
    reference_urls: list[str],
    branch_name: str = "",
    segment_desc: str = "",
) -> float | None:
    """调视觉模型给片段打分（0-10）。任何失败返回 None（fail-open）。"""
    if pool is None or not frame_urls:
        return None
    content: list[dict] = [{"type": "text", "text": build_scoring_prompt(branch_name, segment_desc)}]
    for u in list(reference_urls)[:3]:
        content.append({"type": "image_url", "image_url": {"url": u}})
    for u in frame_urls:
        content.append({"type": "image_url", "image_url": {"url": u}})
    payload = {"messages": [{"role": "user", "content": content}]}
    try:
        result = await asyncio.wait_for(pool.chat_completions(_model(), payload, region=_region()), SCORE_TIMEOUT)
    except Exception as e:
        logger.warning("consistency scoring failed (fail-open): %s", str(e)[:200])
        return None
    text = ""
    if isinstance(result, dict):
        choices = result.get("choices")
        if isinstance(choices, list) and choices:
            text = (choices[0].get("message", {}) or {}).get("content", "") or ""
        if not text:
            text = result.get("content", "") or ""
    elif isinstance(result, str):
        text = result
    return parse_score(text)
