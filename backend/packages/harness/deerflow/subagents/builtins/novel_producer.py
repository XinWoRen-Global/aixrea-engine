"""Novel/script production subagent configuration.

A specialized agent for AI-powered writing — novel chapters, short drama scripts,
marketing copy, and full story generation for the XinWoRen platform.
"""

from deerflow.subagents.config import SubagentConfig

from .novel_prompts import NOVEL_SYSTEM_PROMPT

NOVEL_PRODUCTION_CONFIG = SubagentConfig(
    name="novel-producer",
    description="""XinWoRen AI 小说/剧本创作 Agent — 智能文字内容生成，支持长篇/短篇/剧本/文案。

使用此子代理当用户需要：
- 根据一句话创意生成完整小说（长篇/短篇）
- 根据大纲自动生成小说章节内容
- 创作竖屏短剧剧本（含角色对话和场景描述）
- 生成商品描述、推广文案、SEO 文章
- 续写已有小说内容
- 改写/调整文风和语气
- 创作特定风格的故事（都市/古风/科幻/悬疑/甜宠等）
- 生成角色档案和故事大纲

能力边界：
- 文字内容生成 ✅
- 小说/剧本/文案创作 ✅
- 风格改写/续写 ✅
- 内容优化和润色 ✅
- 实际出版排版 ❌
- 版权法律审核 ❌""",
    system_prompt=NOVEL_SYSTEM_PROMPT,
    tools=None,
    disallowed_tools=["task", "bash"],
    model="inherit",
    max_turns=80,
    timeout_seconds=1200,
)
