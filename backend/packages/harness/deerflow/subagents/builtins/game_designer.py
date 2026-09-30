"""Game designer subagent configuration.

A specialized agent for interactive HTML game generation — visual novels, simulators,
puzzle games, narrative adventures for the XinWoRen platform.
"""

from deerflow.subagents.config import SubagentConfig

from .game_prompts import GAME_SYSTEM_PROMPT

GAME_DESIGN_CONFIG = SubagentConfig(
    name="game-designer",
    description="""XinWoRen AI 互动游戏创作 Agent — 根据文字描述生成单文件 HTML 互动游戏。

使用此子代理当用户需要：
- 根据描述生成互动短剧（分支叙事，玩家选择影响结局）
- 创建模拟器类游戏（重力模拟、生态系统、城市建造等）
- 生成叙事冒险游戏（探索+故事推进）
- 创建益智小游戏（解谜、逻辑、反应力挑战）
- 生成音乐可视化互动体验
- 创建文字冒险游戏（纯文本驱动）
- 生成可在 XinWoRen 互动工坊展示的 HTML 游戏
- 互动内容的原型快速制作

生成规范：
- 单文件 HTML（CSS + JS 内嵌）
- 无外部库依赖
- 响应式设计适配 PC 和移动端
- 硬件加速动画
- 触屏事件支持

    能力边界：
    - HTML 互动游戏生成 ✅
    - 视觉小说/模拟器/小游戏 ✅
    - 交互原型快速制作 ✅
    - 配置/共创模板（CoCreateConfig 数据驱动，零代码）✅
    - 原生编译游戏（Unity/Unreal）❌
    - 多人联网游戏 ❌
    - 3D 复杂渲染 ❌""",
    system_prompt=GAME_SYSTEM_PROMPT,
    tools=None,
    disallowed_tools=["task", "bash"],
    model="inherit",
    max_turns=80,
    timeout_seconds=1200,
)
