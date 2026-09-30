"""
SkillRegistry — 创作类 Skills 统一注册表

统一管理所有 xinworen_* 创作类工具（skills），提供：
- 注册/查询/枚举接口
- 按类型分类（drama/music/comic/novel/interactive）
- 能力声明（支持的操作、需要的模型、消耗的 credits）
- 动态加载（避免循环导入）

设计原则：
- 注册表是只读的，不修改工具本身
- 工具实现仍在 deerflow/tools/builtins/xinworen_*.py
- 注册表只提供元数据和查询能力
- 新增 skill 只需在注册表中添加一条记录

Phase 4 实施：先建注册表骨架，后续接入 AIGateway 和 pipeline_executor。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger("skill_registry")


class SkillType(StrEnum):
    """Skill 类型。"""

    DRAMA = "drama"  # 短剧
    MUSIC = "music"  # 音乐
    COMIC = "comic"  # 漫画
    NOVEL = "novel"  # 小说
    INTERACTIVE = "interactive"  # 互动影游
    GENERAL = "general"  # 通用工具


class SkillStatus(StrEnum):
    """Skill 状态。"""

    ACTIVE = "active"  # 已启用
    BETA = "beta"  # 测试中
    DEPRECATED = "deprecated"  # 已弃用
    PLANNED = "planned"  # 规划中


@dataclass
class SkillCapability:
    """Skill 能力声明。"""

    name: str  # 能力名称
    description: str = ""  # 能力描述
    input_type: str = "text"  # 输入类型（text/image/audio/video）
    output_type: str = "text"  # 输出类型
    credits_cost: int = 0  # 消耗的 credits（0=免费）
    supported_models: list[str] = field(default_factory=list)  # 支持的模型
    requires_approval: bool = False  # 是否需要人工审核


@dataclass
class SkillInfo:
    """Skill 元数据。"""

    id: str  # 唯一标识
    name: str  # 显示名称
    type: SkillType  # 类型
    status: SkillStatus = SkillStatus.ACTIVE  # 状态
    description: str = ""  # 描述
    module_path: str = ""  # 模块路径（用于动态加载）
    class_name: str = ""  # 类名
    capabilities: list[SkillCapability] = field(default_factory=list)
    version: str = "1.0.0"
    author: str = "xinworen"
    tags: list[str] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.status == SkillStatus.ACTIVE

    @property
    def total_credits_cost(self) -> int:
        return sum(c.credits_cost for c in self.capabilities)


class SkillRegistry:
    """创作类 Skills 统一注册表。

    Usage:
        registry = SkillRegistry()
        registry.register(SkillInfo(id="drama", name="短剧创作", ...))
        skill = registry.get("drama")
        all_skills = registry.list_all()
        drama_skills = registry.list_by_type(SkillType.DRAMA)
    """

    def __init__(self):
        self._skills: dict[str, SkillInfo] = {}
        self._loaded_classes: dict[str, Any] = {}

    def register(self, info: SkillInfo):
        """注册一个 skill。"""
        if info.id in self._skills:
            logger.warning("Skill %s already registered, overwriting", info.id)
        self._skills[info.id] = info
        logger.debug("Registered skill: %s (%s)", info.id, info.name)

    def get(self, skill_id: str) -> SkillInfo | None:
        """获取 skill 元数据。"""
        return self._skills.get(skill_id)

    def list_all(self, include_inactive: bool = False) -> list[SkillInfo]:
        """列出所有 skill。"""
        if include_inactive:
            return list(self._skills.values())
        return [s for s in self._skills.values() if s.is_active]

    def list_by_type(self, skill_type: SkillType, include_inactive: bool = False) -> list[SkillInfo]:
        """按类型列出 skill。"""
        return [s for s in self.list_all(include_inactive) if s.type == skill_type]

    def list_by_tag(self, tag: str) -> list[SkillInfo]:
        """按标签列出 skill。"""
        return [s for s in self.list_all() if tag in s.tags]

    def load_class(self, skill_id: str) -> Any | None:
        """动态加载 skill 类。"""
        if skill_id in self._loaded_classes:
            return self._loaded_classes[skill_id]

        info = self.get(skill_id)
        if not info or not info.module_path or not info.class_name:
            logger.warning("Skill %s has no module/class info", skill_id)
            return None

        try:
            import importlib

            module = importlib.import_module(info.module_path)
            cls = getattr(module, info.class_name, None)
            if cls:
                self._loaded_classes[skill_id] = cls
                return cls
        except Exception as e:
            logger.warning("Failed to load skill class %s: %s", skill_id, e)
        return None

    def get_capabilities(self, skill_id: str) -> list[SkillCapability]:
        """获取 skill 的能力列表。"""
        info = self.get(skill_id)
        return info.capabilities if info else []

    def search(self, query: str) -> list[SkillInfo]:
        """搜索 skill（按名称、描述、标签）。"""
        query = query.lower()
        return [s for s in self.list_all() if query in s.name.lower() or query in s.description.lower() or any(query in t.lower() for t in s.tags)]

    async def load_from_db(self) -> int:
        """从 InsForge DB 动态加载工具市场的工具。

        参考大厂做法（OpenAI Plugins / Coze 插件市场）：
        - 工具元数据存 DB，支持运营后台增删改
        - 代码只存执行逻辑，不硬编码元数据
        - 启动时从 DB 加载，运行时可热更新

        Returns:
            从 DB 加载的工具数量
        """
        try:
            from app.gateway import pipeline_insforge

            # 查询 agent_registrations 表中状态为 active 的工具
            rows = await pipeline_insforge._request(
                "GET",
                "agent_registrations",
                query={
                    "status": "eq.active",
                    "select": "skill_name,display_name,description,credits_per_use,provider_type,category_id,org_id",
                    "limit": "200",
                },
            )

            count = 0
            for row in rows:
                skill_name = row.get("skill_name", "")
                if not skill_name or skill_name in self._skills:
                    continue  # 已存在的内置 skill 不覆盖

                # 推断类型
                category = row.get("category_id", "") or ""
                skill_type = SkillType.GENERAL
                for st in SkillType:
                    if st.value in category.lower() or st.value in skill_name.lower():
                        skill_type = st
                        break

                info = SkillInfo(
                    id=skill_name,
                    name=row.get("display_name") or skill_name,
                    type=skill_type,
                    status=SkillStatus.ACTIVE,
                    description=row.get("description") or "",
                    module_path="app.gateway.creation_pipeline_tools",  # 默认执行模块
                    class_name="",  # DB 工具通过通用执行器调用
                    capabilities=[
                        SkillCapability(
                            name="execute",
                            description="执行工具",
                            credits_cost=row.get("credits_per_use", 0),
                        )
                    ],
                    version="1.0.0",
                    author="xinworen" if not row.get("org_id") else "partner",
                    tags=[category] if category else [],
                )
                self.register(info)
                count += 1

            logger.info("Loaded %d skills from DB", count)
            return count
        except Exception as e:
            logger.warning("load_from_db failed (non-fatal, using builtin only): %s", e)
            return 0

    def reload(self) -> int:
        """重新加载（清空后重新注册内置 + DB）。"""
        self._skills.clear()
        self._loaded_classes.clear()
        _register_builtin_skills(self)
        return len(self._skills)


# 全局单例
_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    """获取全局 skill 注册表（懒初始化，自动注册内置 skills）。"""
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        _register_builtin_skills(_registry)
    return _registry


def _register_builtin_skills(registry: SkillRegistry):
    """注册内置的 xinworen_* 创作类 skills。"""
    builtin_skills = [
        SkillInfo(
            id="drama",
            name="短剧创作",
            type=SkillType.DRAMA,
            description="AI 短剧智能体，支持剧本生成、分镜解析、视频合成",
            module_path="deerflow.tools.builtins.xinworen_drama_executor_tools",
            class_name="XinWoRenDramaExecutorTools",
            capabilities=[
                SkillCapability(name="generate_script", description="生成短剧剧本", credits_cost=10),
                SkillCapability(name="parse_storyboard", description="解析分镜", credits_cost=5),
                SkillCapability(name="compose_video", description="合成视频", credits_cost=50),
            ],
            tags=["drama", "video", "script", "storyboard"],
        ),
        SkillInfo(
            id="music",
            name="音乐创作",
            type=SkillType.MUSIC,
            description="AI 音乐智能体，支持歌词生成、音乐描述、音频合成",
            module_path="deerflow.tools.builtins.xinworen_music_executor_tools",
            class_name="XinWoRenMusicExecutorTools",
            capabilities=[
                SkillCapability(name="generate_lyrics", description="生成歌词", credits_cost=5),
                SkillCapability(name="generate_music_desc", description="生成音乐描述", credits_cost=3),
                SkillCapability(name="compose_audio", description="合成音频", credits_cost=30),
            ],
            tags=["music", "audio", "lyrics"],
        ),
        SkillInfo(
            id="comic",
            name="漫画创作",
            type=SkillType.COMIC,
            description="AI 漫画智能体，支持分镜生成、角色设计、图像合成",
            module_path="deerflow.tools.builtins.xinworen_comics_executor_tools",
            class_name="XinWoRenComicsExecutorTools",
            capabilities=[
                SkillCapability(name="generate_panels", description="生成分镜", credits_cost=15),
                SkillCapability(name="design_character", description="设计角色", credits_cost=10),
                SkillCapability(name="compose_images", description="合成图像", credits_cost=40),
            ],
            tags=["comic", "image", "character", "panel"],
        ),
        SkillInfo(
            id="novel",
            name="小说创作",
            type=SkillType.NOVEL,
            description="AI 小说智能体，支持章节生成、大纲规划、角色设定",
            module_path="deerflow.tools.builtins.xinworen_novel_executor_tools",
            class_name="XinWoRenNovelExecutorTools",
            capabilities=[
                SkillCapability(name="generate_outline", description="生成大纲", credits_cost=5),
                SkillCapability(name="generate_chapter", description="生成章节", credits_cost=10),
                SkillCapability(name="design_character", description="角色设定", credits_cost=5),
            ],
            tags=["novel", "text", "chapter", "outline"],
        ),
        SkillInfo(
            id="interactive",
            name="互动影游",
            type=SkillType.INTERACTIVE,
            description="AI 互动影游智能体，支持分支剧情、选择节点、多结局",
            module_path="deerflow.tools.builtins.xinworen_interactive_executor_tools",
            class_name="XinWoRenInteractiveExecutorTools",
            capabilities=[
                SkillCapability(name="generate_branch", description="生成分支剧情", credits_cost=15),
                SkillCapability(name="design_choice", description="设计选择节点", credits_cost=5),
                SkillCapability(name="generate_ending", description="生成结局", credits_cost=10),
            ],
            tags=["interactive", "game", "branch", "ending"],
        ),
    ]

    for skill in builtin_skills:
        registry.register(skill)

    logger.info("Registered %d builtin skills", len(builtin_skills))
