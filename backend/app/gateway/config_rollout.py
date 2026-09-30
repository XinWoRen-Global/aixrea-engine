"""
配置灰度发布模块 — 大厂标准做法
- 支持按用户 ID 灰度（指定用户使用新配置）
- 支持按百分比灰度（一定比例的用户使用新配置）
- 支持按地域灰度（指定地域的用户使用新配置）
- 支持灰度规则的增删改查
- 支持灰度发布的开始、暂停、回滚

使用方式：
    from app.gateway.config_rollout import ConfigRolloutManager
    rollout_manager = ConfigRolloutManager()
    # 获取用户的配置值（自动判断是否在灰度范围内）
    value = rollout_manager.get_config_value("feature.xxx", user_id="user123", default=False)
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class RolloutStrategy(StrEnum):
    """灰度策略"""

    USER_ID = "user_id"  # 按用户 ID 列表
    PERCENTAGE = "percentage"  # 按百分比
    REGION = "region"  # 按地域
    INTERNAL = "internal"  # 内部用户（员工/测试）


class RolloutStatus(StrEnum):
    """灰度状态"""

    DRAFT = "draft"  # 草稿
    ACTIVE = "active"  # 进行中
    PAUSED = "paused"  # 已暂停
    COMPLETED = "completed"  # 已完成（全量）
    ROLLED_BACK = "rolled_back"  # 已回滚


@dataclass
class RolloutRule:
    """灰度规则"""

    id: str  # 规则 ID
    config_key: str  # 配置键
    strategy: RolloutStrategy  # 灰度策略
    target_value: Any  # 灰度目标值（新配置值）
    default_value: Any  # 默认值（非灰度用户使用）
    # 策略参数
    user_ids: list[str] = field(default_factory=list)  # 用户 ID 列表（USER_ID 策略）
    percentage: float = 0.0  # 百分比（PERCENTAGE 策略，0-100）
    regions: list[str] = field(default_factory=list)  # 地域列表（REGION 策略）
    internal_only: bool = False  # 仅内部用户（INTERNAL 策略）
    # 元数据
    name: str = ""  # 规则名称
    description: str = ""  # 规则描述
    status: RolloutStatus = RolloutStatus.DRAFT  # 状态
    created_by: str = "system"  # 创建人
    created_at: float = field(default_factory=time.time)  # 创建时间
    updated_at: float = field(default_factory=time.time)  # 更新时间
    started_at: float | None = None  # 开始时间
    completed_at: float | None = None  # 完成时间
    rolled_back_at: float | None = None  # 回滚时间


class ConfigRolloutManager:
    """配置灰度发布管理器"""

    def __init__(self):
        self.rules: dict[str, RolloutRule] = {}
        self._rule_counter = 0

    def add_rule(self, rule: RolloutRule) -> str:
        """添加灰度规则

        Returns:
            规则 ID
        """
        if not rule.id:
            self._rule_counter += 1
            rule.id = f"rollout-{int(time.time())}-{self._rule_counter}"

        self.rules[rule.id] = rule
        logger.info(f"Rollout rule added: {rule.id} (config={rule.config_key}, strategy={rule.strategy.value}, status={rule.status.value})")
        return rule.id

    def remove_rule(self, rule_id: str) -> bool:
        """移除灰度规则"""
        if rule_id in self.rules:
            del self.rules[rule_id]
            logger.info(f"Rollout rule removed: {rule_id}")
            return True
        return False

    def get_rule(self, rule_id: str) -> RolloutRule | None:
        """获取灰度规则"""
        return self.rules.get(rule_id)

    def list_rules(self, config_key: str | None = None, status: RolloutStatus | None = None) -> list[RolloutRule]:
        """列出灰度规则

        Args:
            config_key: 按配置键过滤
            status: 按状态过滤
        """
        rules = list(self.rules.values())
        if config_key:
            rules = [r for r in rules if r.config_key == config_key]
        if status:
            rules = [r for r in rules if r.status == status]
        return sorted(rules, key=lambda r: r.created_at, reverse=True)

    def start_rollout(self, rule_id: str) -> bool:
        """开始灰度发布"""
        rule = self.rules.get(rule_id)
        if not rule:
            return False
        rule.status = RolloutStatus.ACTIVE
        rule.started_at = time.time()
        rule.updated_at = time.time()
        logger.info(f"Rollout started: {rule_id}")
        return True

    def pause_rollout(self, rule_id: str) -> bool:
        """暂停灰度发布"""
        rule = self.rules.get(rule_id)
        if not rule:
            return False
        rule.status = RolloutStatus.PAUSED
        rule.updated_at = time.time()
        logger.info(f"Rollout paused: {rule_id}")
        return True

    def complete_rollout(self, rule_id: str) -> bool:
        """完成灰度发布（全量）"""
        rule = self.rules.get(rule_id)
        if not rule:
            return False
        rule.status = RolloutStatus.COMPLETED
        rule.completed_at = time.time()
        rule.updated_at = time.time()
        logger.info(f"Rollout completed: {rule_id}")
        return True

    def rollback_rollout(self, rule_id: str) -> bool:
        """回滚灰度发布"""
        rule = self.rules.get(rule_id)
        if not rule:
            return False
        rule.status = RolloutStatus.ROLLED_BACK
        rule.rolled_back_at = time.time()
        rule.updated_at = time.time()
        logger.info(f"Rollout rolled back: {rule_id}")
        return True

    def _is_user_in_rollout(self, rule: RolloutRule, user_id: str | None = None, region: str | None = None) -> bool:
        """判断用户是否在灰度范围内

        Args:
            rule: 灰度规则
            user_id: 用户 ID
            region: 地域

        Returns:
            是否在灰度范围内
        """
        if rule.status != RolloutStatus.ACTIVE:
            return False

        if rule.strategy == RolloutStrategy.USER_ID:
            return user_id is not None and user_id in rule.user_ids

        elif rule.strategy == RolloutStrategy.PERCENTAGE:
            if user_id is None:
                return False
            # 使用用户 ID 的哈希值来确定是否在百分比范围内
            hash_value = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
            return (hash_value % 10000) / 100.0 < rule.percentage

        elif rule.strategy == RolloutStrategy.REGION:
            return region is not None and region in rule.regions

        elif rule.strategy == RolloutStrategy.INTERNAL:
            # 内部用户判断（可根据实际情况修改）
            if user_id is None:
                return False
            return user_id.startswith("internal_") or user_id.startswith("admin_") or rule.internal_only

        return False

    def get_config_value(
        self,
        config_key: str,
        user_id: str | None = None,
        region: str | None = None,
        default: Any = None,
    ) -> Any:
        """获取配置值（自动判断是否在灰度范围内）

        Args:
            config_key: 配置键
            user_id: 用户 ID
            region: 地域
            default: 默认值（无灰度规则时使用）

        Returns:
            配置值（灰度用户使用 target_value，非灰度用户使用 default_value）
        """
        # 查找该配置键的活跃灰度规则
        active_rules = [r for r in self.rules.values() if r.config_key == config_key and r.status == RolloutStatus.ACTIVE]

        if not active_rules:
            return default

        # 使用第一个活跃规则（可根据实际情况调整优先级）
        rule = active_rules[0]

        if self._is_user_in_rollout(rule, user_id, region):
            logger.debug(f"User in rollout: config={config_key}, user={user_id}, using target_value={rule.target_value}")
            return rule.target_value
        else:
            return rule.default_value

    def get_rollout_stats(self) -> dict[str, Any]:
        """获取灰度发布统计"""
        total = len(self.rules)
        by_status = {status.value: len([r for r in self.rules.values() if r.status == status]) for status in RolloutStatus}
        by_strategy = {strategy.value: len([r for r in self.rules.values() if r.strategy == strategy]) for strategy in RolloutStrategy}
        return {
            "total_rules": total,
            "by_status": by_status,
            "by_strategy": by_strategy,
            "active_rules": by_status.get("active", 0),
        }


# 全局灰度发布管理器实例
_rollout_manager: ConfigRolloutManager | None = None


def get_rollout_manager() -> ConfigRolloutManager:
    """获取全局灰度发布管理器实例"""
    global _rollout_manager
    if _rollout_manager is None:
        _rollout_manager = ConfigRolloutManager()
        logger.info("Config rollout manager initialized")
    return _rollout_manager
