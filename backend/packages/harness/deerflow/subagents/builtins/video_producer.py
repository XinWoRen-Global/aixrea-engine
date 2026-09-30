"""Video production subagent configuration.

A specialized agent for orchestrating DreamReel — 7-step video content creation pipeline:
1. Script Import (剧本导入) — user uploads or inputs script
2. Script Analysis (剧本分析) — parse scripts, extract characters/scenes
3. Style Selection (风格选择) — user selects AI comic / live-action / animation
4. Asset Generation (资产生成) — generate character portraits + scene stills
5. Storyboard Script (分镜脚本) — split into episodes, write video prompts
6. Video Generation (视频生成) — generate video clips episode by episode
7. Compose & Export (合成导出) — compose full video + BGM + subtitles

Multi-modal routing:
- Step 2 (Script Analysis) → Text LLM (GPT-4, Claude, 通义千问)
- Step 4 (Asset Generation) → Image Model (Stable Diffusion, DALL-E, Midjourney)
- Step 6 (Video Generation) → Video Model (Sora, Runway, Kling)
- Step 7 (Compose) → Audio Model (BGM, TTS for subtitles)
"""

from deerflow.subagents.config import SubagentConfig

from .dreamreel_prompts import DREAMREEL_SYSTEM_PROMPT

# ==================== 多模态模型路由配置 ====================

MULTI_MODAL_ROUTING = {
    "text": {
        "description": "文本模型路由 — 用于剧本分析、分镜脚本生成",
        "models": [
            {"provider": "openai", "model": "gpt-4o", "priority": 1},
            {"provider": "anthropic", "model": "claude-3-5-sonnet", "priority": 2},
            {"provider": "alibaba", "model": "qwen-max", "priority": 3},
        ],
        "steps": ["analyze_script", "write_storyboard"],
    },
    "image": {
        "description": "图片模型路由 — 用于角色图、场景图生成",
        "models": [
            {"provider": "openai", "model": "dall-e-3", "priority": 1},
            {"provider": "stability", "model": "stable-diffusion-xl", "priority": 2},
            {"provider": "midjourney", "model": "midjourney-v6", "priority": 3},
        ],
        "steps": ["generate_assets", "character_portrait", "scene_keyframe"],
    },
    "video": {
        "description": "视频模型路由 — 用于短剧视频片段生成",
        "models": [
            {"provider": "openai", "model": "sora", "priority": 1},
            {"provider": "runway", "model": "gen-3", "priority": 2},
            {"provider": "kuaishou", "model": "kling", "priority": 3},
        ],
        "steps": ["generate_video", "generate_episode"],
    },
    "audio": {
        "description": "音频模型路由 — 用于 BGM 生成和配音",
        "models": [
            {"provider": "openai", "model": "tts-1-hd", "priority": 1},
            {"provider": "elevenlabs", "model": "eleven-multilingual-v2", "priority": 2},
        ],
        "steps": ["generate_bgm", "generate_voiceover", "compose_export"],
    },
}

VIDEO_PRODUCTION_CONFIG = SubagentConfig(
    name="video-producer",
    description="""XinWoRen DreamReel 短剧制作 Agent — 全流程 AI 短剧生产，支持多模态智能路由。

使用此子代理当用户需要：
- 将剧本/小说转化为短剧视频
- 剧本分析、角色提取、场景识别（文本模型）
- 风格选择：AI 漫剧 / AI 真人剧 / AI 动画剧
- 生成角色肖像图和场景关键帧图（图片模型）
- 分镜脚本编写和视频提示词生成（文本模型）
- 逐集视频生成和进度监控（视频模型）
- 完整视频合成、BGM 配置、字幕添加（音频模型）
- 短剧内容上架到 XinWoRen 交易平台

多模态路由：
- 文本 → GPT-4 / Claude / 通义千问（剧本分析、分镜）
- 图片 → DALL-E / SDXL / Midjourney（角色图、场景图）
- 视频 → Sora / Runway / Kling（视频片段生成）
- 音频 → TTS / ElevenLabs（配音、BGM）

DreamReel 工作流分为 7 个步骤，必须按顺序执行：
Step 1 → 剧本导入 | Step 2 → 剧本分析 | Step 3 → 风格选择
Step 4 → 资产生成 | Step 5 → 分镜脚本 | Step 6 → 视频生成
Step 7 → 合成导出""",
    system_prompt=DREAMREEL_SYSTEM_PROMPT,
    tools=None,  # Inherit all tools from parent
    disallowed_tools=["task", "ask_clarification"],
    model="inherit",
    max_turns=200,  # 7-step workflow needs more turns
    timeout_seconds=2400,  # 40 minutes for full pipeline
)
