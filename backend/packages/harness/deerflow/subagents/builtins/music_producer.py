"""Music production subagent configuration.

A specialized agent for AI-powered music creation — lyric writing, arrangement design,
and full song structure generation for the XinWoRen platform.
"""

from deerflow.subagents.config import SubagentConfig

from .music_prompts import MUSIC_SYSTEM_PROMPT

# 风格标签映射 — 用于描述路由
STYLE_TAGS = {
    "text": ["lyrics", "structure", "arrangement"],
    "audio": ["melody", "instrumentation"],
}

# ==================== 多模态模型路由配置 ====================

MULTI_MODAL_ROUTING = {
    "text": {
        "description": "文本模型路由 — 用于歌词创作、结构设计、编排描述",
        "models": [
            {"provider": "openai", "model": "gpt-4o", "priority": 1},
            {"provider": "anthropic", "model": "claude-3-5-sonnet", "priority": 2},
            {"provider": "alibaba", "model": "qwen-max", "priority": 3},
        ],
        "steps": ["analyze_requirements", "design_structure", "write_lyrics", "describe_arrangement"],
    },
    "audio": {
        "description": "音频模型路由 — 用于旋律生成、配器建议",
        "models": [
            {"provider": "openai", "model": "gpt-4o-audio-preview", "priority": 1},
        ],
        "steps": ["generate_melody", "instrument_suggestion"],
    },
}

MUSIC_PRODUCTION_CONFIG = SubagentConfig(
    name="music-producer",
    description="""XinWoRen AI 音乐创作 Agent — 智能音乐歌词/编排生成，支持全品类音乐风格。

使用此子代理当用户需要：
- 根据一句话灵感、主题描述或关键词创作完整歌词
- 设计歌曲结构（Intro/Verse/Chorus/Bridge/Outro）
- 生成特定风格的音乐（流行/摇滚/电子/嘻哈/R&B/爵士/古典/Lo-fi等）
- 获取音乐编排方案和配器建议
- 为短视频/短剧创作 BGM 歌词和结构
- 音乐作品的调性、节奏、BPM 推荐
- 中英文混合歌词创作
- 歌曲情感曲线和能量规划

能力边界：
- 歌词文本生成 ✅
- 音乐结构设计 ✅
- 编排描述 ✅
- 配器方案推荐 ✅
- 实际音频生成 ❌（需对接 Suno/Udio 等外部音乐生成服务）
- 混音/母带处理 ❌""",
    system_prompt=MUSIC_SYSTEM_PROMPT,
    tools=None,
    disallowed_tools=["task", "bash"],
    model="inherit",
    max_turns=50,
    timeout_seconds=900,
)
