"""
同步适配器（Sync Adapter）
==========================

负责与外部系统（如InsForge agent_registrations表）的交互。

功能：
1. 定义统一的同步适配器接口
2. 实现InsForge适配器（真实PostgreSQL连接）
3. 支持扩展其他外部系统适配器
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from deerflow.capability.registry import (
    CapabilityMetadata,
    CapabilityType,
)

logger = logging.getLogger(__name__)


@dataclass
class ExternalCapability:
    """外部系统的能力表示"""

    # 基本信息
    external_id: str
    name: str
    display_name: str
    description: str
    type: str  # agent, tool, skill, model

    # 分类信息
    category: str | None = None
    tags: list[str] = field(default_factory=list)

    # 状态信息
    status: str = "active"  # active, coming_soon, beta, rejected, suspended
    visibility: str = "public"  # public, internal
    version: str = "1.0.0"

    # 商业信息
    price_type: str = "free"  # free, credits, subscription
    credits_per_use: int = 0
    rating: float = 0.0
    installs: int = 0
    featured: bool = False

    # 扩展信息
    owner_id: str | None = None
    provider_type: str = "platform"  # platform, byok
    output_formats: list[str] = field(default_factory=list)
    estimated_time: int | None = None
    capability: str | None = None
    run_config: dict[str, Any] = field(default_factory=dict)
    icon: str = "Sparkles"
    gradient: str = "from-sky-500 to-cyan-500"

    # 时间戳
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # 原始数据
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_capability_metadata(self) -> CapabilityMetadata:
        """转换为CapabilityMetadata"""
        # 映射类型
        type_mapping = {
            "agent": CapabilityType.AGENT,
            "tool": CapabilityType.TOOL,
            "skill": CapabilityType.SKILL,
            "model": CapabilityType.MODEL,
        }
        cap_type = type_mapping.get(self.type, CapabilityType.TOOL)

        # 推断业务域
        domain = self._infer_domain()

        return CapabilityMetadata(
            name=self.name,
            type=cap_type,
            description=self.description or self.display_name,
            version=self.version,
            domain=domain,
            tags=self.tags,
            categories=[self.category] if self.category else [],
            status=self._map_status(),
            is_builtin=False,
            metadata={
                "external_id": self.external_id,
                "display_name": self.display_name,
                "category": self.category,
                "price_type": self.price_type,
                "credits_per_use": self.credits_per_use,
                "rating": self.rating,
                "installs": self.installs,
                "featured": self.featured,
                "owner_id": self.owner_id,
                "provider_type": self.provider_type,
                "output_formats": self.output_formats,
                "estimated_time": self.estimated_time,
                "capability": self.capability,
                "run_config": self.run_config,
                "icon": self.icon,
                "gradient": self.gradient,
                "source": "external_sync",
            },
        )

    def _infer_domain(self) -> str:
        """推断业务域"""
        name_lower = self.name.lower()
        desc_lower = (self.description or "").lower()
        category_lower = str(self.category or "").lower()

        # 内容创作域
        content_keywords = ["drama", "novel", "comic", "music", "video", "image", "audio", "短剧", "小说", "漫画", "音乐", "视频", "图像", "音频"]
        if any(k in name_lower or k in desc_lower or k in category_lower for k in content_keywords):
            return "content_creation"

        # 商城交易域
        marketplace_keywords = ["payment", "order", "product", "shop", "marketplace", "支付", "订单", "商品", "商城"]
        if any(k in name_lower or k in desc_lower or k in category_lower for k in marketplace_keywords):
            return "marketplace"

        # 数据智能域
        data_keywords = ["data", "analytics", "analysis", "research", "数据", "分析", "研究"]
        if any(k in name_lower or k in desc_lower or k in category_lower for k in data_keywords):
            return "data"

        return "general"

    def _map_status(self) -> str:
        """映射状态"""
        status_mapping = {
            "active": "active",
            "beta": "experimental",
            "coming_soon": "deprecated",
            "rejected": "deprecated",
            "suspended": "deprecated",
        }
        return status_mapping.get(self.status, "active")


class SyncAdapter(ABC):
    """同步适配器抽象基类"""

    @abstractmethod
    def get_all_capabilities(self) -> list[ExternalCapability]:
        """获取所有外部能力"""
        pass

    @abstractmethod
    def get_capability(self, external_id: str) -> ExternalCapability | None:
        """获取单个外部能力"""
        pass

    @abstractmethod
    def create_capability(self, capability: CapabilityMetadata) -> str:
        """创建外部能力，返回外部ID"""
        pass

    @abstractmethod
    def update_capability(self, external_id: str, capability: CapabilityMetadata) -> bool:
        """更新外部能力"""
        pass

    @abstractmethod
    def delete_capability(self, external_id: str) -> bool:
        """删除外部能力"""
        pass

    @abstractmethod
    def get_changed_since(self, timestamp: datetime) -> list[ExternalCapability]:
        """获取指定时间后变更的能力（增量同步）"""
        pass


class InsForgeAdapter(SyncAdapter):
    """
    InsForge同步适配器（真实PostgreSQL连接实现）

    负责与InsForge的agent_registrations表进行同步。

    环境变量：
    - INSFORGE_DATABASE_URL: PostgreSQL连接字符串
    - INSFORGE_API_KEY: InsForge API Key（备用，通过HTTP API）
    """

    def __init__(self, database_url: str | None = None, api_key: str | None = None, base_url: str | None = None, table_name: str = "agent_registrations"):
        self.database_url = database_url or os.environ.get("INSFORGE_DATABASE_URL", "")
        self.api_key = api_key or os.environ.get("INSFORGE_API_KEY", "")
        self.base_url = base_url or os.environ.get("INSFORGE_BASE_URL", "https://api.insforge.dev")
        self.table_name = table_name

        self._conn = None
        self._use_direct_db = bool(self.database_url)

        if self._use_direct_db:
            logger.info("InsForgeAdapter initialized with direct PostgreSQL connection")
        else:
            logger.warning("InsForgeAdapter initialized without DATABASE_URL, using API fallback mode")

    def _get_connection(self):
        """获取数据库连接（延迟初始化）"""
        if not self._use_direct_db:
            raise RuntimeError("INSFORGE_DATABASE_URL not configured")

        if self._conn is None or self._conn.closed:
            import psycopg

            self._conn = psycopg.connect(self.database_url)
            logger.info("Connected to InsForge PostgreSQL database")
        return self._conn

    def _row_to_external_capability(self, row: dict[str, Any]) -> ExternalCapability:
        """将数据库行转换为ExternalCapability"""
        return ExternalCapability(
            external_id=str(row.get("id", "")),
            name=row.get("skill_name", ""),
            display_name=row.get("display_name", row.get("skill_name", "")),
            description=row.get("description") or "",
            type=row.get("type", "tool"),
            category=row.get("category_id"),
            tags=row.get("tags") or [],
            status=row.get("status", "active"),
            visibility=row.get("visibility", "public"),
            version=row.get("version", "1.0.0"),
            price_type=row.get("price_type", "free"),
            credits_per_use=row.get("credits_per_use", 0) or 0,
            rating=float(row.get("rating", 0.0) or 0.0),
            installs=row.get("installs", 0) or 0,
            featured=bool(row.get("featured", False)),
            owner_id=row.get("owner_id"),
            provider_type=row.get("provider_type", "platform"),
            output_formats=row.get("output_formats") or [],
            estimated_time=row.get("estimated_time"),
            capability=row.get("capability"),
            run_config=row.get("run_config") or {},
            icon=row.get("icon", "Sparkles"),
            gradient=row.get("gradient", "from-sky-500 to-cyan-500"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            raw_data=row,
        )

    def get_all_capabilities(self) -> list[ExternalCapability]:
        """获取所有外部能力"""
        if not self._use_direct_db:
            logger.warning("Direct DB not available, returning empty list")
            return []

        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT * FROM {self.table_name}
                    WHERE status = 'active' AND visibility = 'public'
                    ORDER BY created_at DESC
                """)
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                result = [self._row_to_external_capability(dict(zip(columns, row))) for row in rows]
                logger.info("Fetched %d capabilities from InsForge", len(result))
                return result
        except Exception as e:
            logger.error("Failed to fetch all capabilities: %s", e, exc_info=True)
            return []

    def get_capability(self, external_id: str) -> ExternalCapability | None:
        """获取单个外部能力"""
        if not self._use_direct_db:
            return None

        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {self.table_name} WHERE id = %s", (external_id,))
                row = cur.fetchone()
                if row:
                    columns = [desc[0] for desc in cur.description]
                    return self._row_to_external_capability(dict(zip(columns, row)))
                return None
        except Exception as e:
            logger.error("Failed to fetch capability %s: %s", external_id, e, exc_info=True)
            return None

    def create_capability(self, capability: CapabilityMetadata) -> str:
        """创建外部能力，返回外部ID"""
        if not self._use_direct_db:
            logger.warning("Direct DB not available, cannot create capability")
            return ""

        try:
            conn = self._get_connection()
            insert_data = self._to_insforge_data(capability)

            # 构建插入SQL
            columns = ", ".join(insert_data.keys())
            placeholders = ", ".join(["%s"] * len(insert_data))
            values = list(insert_data.values())

            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {self.table_name} ({columns})
                    VALUES ({placeholders})
                    RETURNING id
                """,
                    values,
                )
                result = cur.fetchone()
                conn.commit()
                external_id = str(result[0]) if result else ""
                logger.info("Created capability %s in InsForge (id=%s)", capability.name, external_id)
                return external_id
        except Exception as e:
            logger.error("Failed to create capability %s: %s", capability.name, e, exc_info=True)
            if self._conn:
                self._conn.rollback()
            return ""

    def update_capability(self, external_id: str, capability: CapabilityMetadata) -> bool:
        """更新外部能力"""
        if not self._use_direct_db:
            return False

        try:
            conn = self._get_connection()
            update_data = self._to_insforge_data(capability)
            update_data["updated_at"] = datetime.now()

            # 构建更新SQL
            set_clause = ", ".join([f"{k} = %s" for k in update_data.keys()])
            values = list(update_data.values()) + [external_id]

            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {self.table_name}
                    SET {set_clause}
                    WHERE id = %s
                """,
                    values,
                )
                conn.commit()
                logger.info("Updated capability %s in InsForge", external_id)
                return True
        except Exception as e:
            logger.error("Failed to update capability %s: %s", external_id, e, exc_info=True)
            if self._conn:
                self._conn.rollback()
            return False

    def delete_capability(self, external_id: str) -> bool:
        """删除外部能力（软删除：将status设为suspended）"""
        if not self._use_direct_db:
            return False

        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {self.table_name}
                    SET status = 'suspended', updated_at = %s
                    WHERE id = %s
                """,
                    (datetime.now(), external_id),
                )
                conn.commit()
                logger.info("Soft-deleted capability %s in InsForge", external_id)
                return True
        except Exception as e:
            logger.error("Failed to delete capability %s: %s", external_id, e, exc_info=True)
            if self._conn:
                self._conn.rollback()
            return False

    def get_changed_since(self, timestamp: datetime) -> list[ExternalCapability]:
        """获取指定时间后变更的能力（增量同步）"""
        if not self._use_direct_db:
            return []

        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT * FROM {self.table_name}
                    WHERE updated_at > %s AND visibility = 'public'
                    ORDER BY updated_at DESC
                """,
                    (timestamp,),
                )
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                result = [self._row_to_external_capability(dict(zip(columns, row))) for row in rows]
                logger.info("Fetched %d changed capabilities since %s", len(result), timestamp)
                return result
        except Exception as e:
            logger.error("Failed to fetch changed capabilities: %s", e, exc_info=True)
            return []

    def _to_insforge_data(self, capability: CapabilityMetadata) -> dict[str, Any]:
        """将CapabilityMetadata转换为InsForge表数据格式"""
        # 映射类型
        type_mapping = {
            CapabilityType.AGENT: "agent",
            CapabilityType.TOOL: "tool",
            CapabilityType.SKILL: "skill",
            CapabilityType.MODEL: "model",
        }

        return {
            "skill_name": capability.name,
            "display_name": capability.metadata.get("display_name", capability.name),
            "description": capability.description,
            "category_id": capability.categories[0] if capability.categories else None,
            "icon": capability.metadata.get("icon", "Sparkles"),
            "gradient": capability.metadata.get("gradient", "from-sky-500 to-cyan-500"),
            "price_type": capability.metadata.get("price_type", "free"),
            "credits_per_use": capability.metadata.get("credits_per_use", 0),
            "provider_type": capability.metadata.get("provider_type", "platform"),
            "tags": capability.tags,
            "rating": capability.metadata.get("rating", 0.0),
            "installs": capability.metadata.get("installs", 0),
            "status": capability.status if capability.status != "experimental" else "beta",
            "visibility": "public",
            "version": capability.version,
            "feature_keys": capability.metadata.get("feature_keys", []),
            "run_config": capability.metadata.get("run_config", {}),
            "featured": capability.metadata.get("featured", False),
            "output_formats": capability.metadata.get("output_formats", []),
            "estimated_time": capability.metadata.get("estimated_time"),
            "capability": capability.metadata.get("capability"),
            "type": type_mapping.get(capability.type, "tool"),
        }

    def close(self):
        """关闭数据库连接"""
        if self._conn and not self._conn.closed:
            self._conn.close()
            logger.info("Closed InsForge PostgreSQL connection")
