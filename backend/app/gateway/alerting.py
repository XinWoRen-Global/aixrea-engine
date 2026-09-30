"""
告警规则配置模块 — 大厂标准做法
- 配置告警规则（成功率 < 90%、延迟 > 5s、错误率 > 5% 等）
- 定期检查告警规则是否触发
- 触发告警时发送通知（日志、邮件、Webhook、企业微信等）

使用方式：
    from app.gateway.alerting import AlertManager, AlertRule
    alert_manager = AlertManager()
    alert_manager.add_rule(AlertRule(...))
    alert_manager.check_and_alert(metrics)
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class AlertSeverity(StrEnum):
    """告警级别"""

    CRITICAL = "critical"  # 严重（立即处理）
    WARNING = "warning"  # 警告（尽快处理）
    INFO = "info"  # 信息（记录即可）


class AlertStatus(StrEnum):
    """告警状态"""

    PENDING = "pending"  # 待处理
    ACKNOWLEDGED = "ack"  # 已确认
    RESOLVED = "resolved"  # 已解决
    SUPPRESSED = "suppressed"  # 已抑制


@dataclass
class AlertRule:
    """告警规则"""

    name: str  # 规则名称
    description: str  # 规则描述
    severity: AlertSeverity  # 告警级别
    condition: Callable[[dict[str, Any]], bool]  # 触发条件（输入 metrics，返回是否触发）
    cooldown_seconds: int = 300  # 冷却时间（秒），避免重复告警
    enabled: bool = True  # 是否启用
    notification_channels: list[str] = field(default_factory=lambda: ["log"])  # 通知渠道
    last_triggered: float = 0  # 上次触发时间
    trigger_count: int = 0  # 触发次数


@dataclass
class AlertEvent:
    """告警事件"""

    id: str  # 事件 ID
    rule_name: str  # 规则名称
    severity: AlertSeverity  # 告警级别
    message: str  # 告警消息
    metrics: dict[str, Any]  # 触发时的指标
    status: AlertStatus = AlertStatus.PENDING  # 状态
    created_at: float = field(default_factory=time.time)  # 创建时间
    acknowledged_at: float | None = None  # 确认时间
    resolved_at: float | None = None  # 解决时间
    acknowledged_by: str | None = None  # 确认人
    notes: str = ""  # 备注


class AlertManager:
    """告警管理器"""

    def __init__(self):
        self.rules: dict[str, AlertRule] = {}
        self.events: list[AlertEvent] = []
        self._event_counter = 0
        self._notification_handlers: dict[str, Callable[[AlertEvent], None]] = {
            "log": self._notify_log,
        }
        # 注册默认通知渠道
        self._register_default_handlers()

    def _register_default_handlers(self):
        """注册默认通知处理器"""
        # 日志通知（默认）
        self._notification_handlers["log"] = self._notify_log
        # Webhook 通知（预留）
        self._notification_handlers["webhook"] = self._notify_webhook
        # 邮件通知（预留）
        self._notification_handlers["email"] = self._notify_email
        # 企业微信通知（预留）
        self._notification_handlers["wecom"] = self._notify_wecom

    def add_rule(self, rule: AlertRule) -> None:
        """添加告警规则"""
        self.rules[rule.name] = rule
        logger.info(f"Alert rule added: {rule.name} ({rule.severity.value})")

    def remove_rule(self, rule_name: str) -> bool:
        """移除告警规则"""
        if rule_name in self.rules:
            del self.rules[rule_name]
            logger.info(f"Alert rule removed: {rule_name}")
            return True
        return False

    def check_and_alert(self, metrics: dict[str, Any]) -> list[AlertEvent]:
        """检查所有告警规则，触发告警

        Args:
            metrics: 当前指标数据

        Returns:
            本次触发的告警事件列表
        """
        triggered_events = []
        now = time.time()

        for rule_name, rule in self.rules.items():
            if not rule.enabled:
                continue

            # 检查冷却时间
            if now - rule.last_triggered < rule.cooldown_seconds:
                continue

            # 检查触发条件
            try:
                if rule.condition(metrics):
                    # 触发告警
                    rule.last_triggered = now
                    rule.trigger_count += 1

                    event = self._create_alert_event(rule, metrics)
                    self.events.append(event)
                    triggered_events.append(event)

                    # 发送通知
                    self._send_notifications(event, rule)

                    logger.warning(f"Alert triggered: {rule.name} ({rule.severity.value}) - {event.message}")
            except Exception as e:
                logger.error(f"Error checking alert rule {rule_name}: {e}")

        return triggered_events

    def _create_alert_event(self, rule: AlertRule, metrics: dict[str, Any]) -> AlertEvent:
        """创建告警事件"""
        self._event_counter += 1
        event_id = f"alert-{int(time.time())}-{self._event_counter}"

        # 生成告警消息
        message = self._generate_alert_message(rule, metrics)

        return AlertEvent(
            id=event_id,
            rule_name=rule.name,
            severity=rule.severity,
            message=message,
            metrics=metrics,
        )

    def _generate_alert_message(self, rule: AlertRule, metrics: dict[str, Any]) -> str:
        """生成告警消息"""
        # 提取关键指标
        key_metrics = []
        for key in ("success_rate", "error_rate", "avg_latency", "p99_latency", "total_requests", "total_errors"):
            if key in metrics:
                value = metrics[key]
                if isinstance(value, float):
                    value = f"{value:.2f}"
                key_metrics.append(f"{key}={value}")

        metrics_str = ", ".join(key_metrics) if key_metrics else "详见指标数据"
        return f"[{rule.severity.value.upper()}] {rule.name}: {rule.description} | {metrics_str}"

    def _send_notifications(self, event: AlertEvent, rule: AlertRule) -> None:
        """发送通知"""
        for channel in rule.notification_channels:
            handler = self._notification_handlers.get(channel)
            if handler:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Error sending notification to {channel}: {e}")
            else:
                logger.warning(f"Unknown notification channel: {channel}")

    def _notify_log(self, event: AlertEvent) -> None:
        """日志通知"""
        log_func = logger.error if event.severity == AlertSeverity.CRITICAL else logger.warning
        log_func(f"ALERT [{event.severity.value}] {event.rule_name}: {event.message}")

    def _notify_webhook(self, event: AlertEvent) -> None:
        """Webhook 通知（实际发送 HTTP POST 请求）

        支持通用 Webhook 格式，可对接 Slack、飞书、钉钉、企业微信等。
        环境变量: ALERT_WEBHOOK_URL
        """
        import os

        webhook_url = os.getenv("ALERT_WEBHOOK_URL")
        if not webhook_url:
            logger.debug("Webhook URL not configured, skipping webhook notification")
            return

        try:
            import httpx

            payload = {
                "alert_id": event.id,
                "rule_name": event.rule_name,
                "severity": event.severity.value,
                "message": event.message,
                "metrics": event.metrics,
                "created_at": event.created_at,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            # 使用同步客户端发送，设置较短超时避免阻塞
            with httpx.Client(timeout=5.0) as client:
                response = client.post(webhook_url, json=payload)
                if response.status_code >= 400:
                    logger.error(f"Webhook notification failed: status={response.status_code}, body={response.text[:200]}")
                else:
                    logger.info(f"Webhook notification sent successfully to {webhook_url}")
        except Exception as e:
            logger.error(f"Failed to send webhook notification: {e}")

    def _notify_email(self, event: AlertEvent) -> None:
        """邮件通知（预留，需配置 SMTP）

        环境变量: ALERT_SMTP_HOST, ALERT_SMTP_PORT, ALERT_SMTP_USER,
                  ALERT_SMTP_PASSWORD, ALERT_EMAIL_FROM, ALERT_EMAIL_TO
        """
        import os

        smtp_host = os.getenv("ALERT_SMTP_HOST")
        if not smtp_host:
            logger.debug("SMTP not configured, skipping email notification")
            return

        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            smtp_port = int(os.getenv("ALERT_SMTP_PORT", "587"))
            smtp_user = os.getenv("ALERT_SMTP_USER", "")
            smtp_password = os.getenv("ALERT_SMTP_PASSWORD", "")
            email_from = os.getenv("ALERT_EMAIL_FROM", smtp_user)
            email_to = os.getenv("ALERT_EMAIL_TO", "")

            if not email_to:
                logger.warning("ALERT_EMAIL_TO not configured, skipping email notification")
                return

            msg = MIMEMultipart()
            msg["From"] = email_from
            msg["To"] = email_to
            msg["Subject"] = f"[{event.severity.value.upper()}] {event.rule_name}: {event.message[:50]}"

            body = f"""
告警通知
========

规则名称: {event.rule_name}
告警级别: {event.severity.value.upper()}
告警消息: {event.message}
告警时间: {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(event.created_at))}

指标详情:
{json.dumps(event.metrics, indent=2, ensure_ascii=False) if event.metrics else "无"}

---
此邮件由 DeerFlow 告警系统自动发送
"""
            msg.attach(MIMEText(body, "plain", "utf-8"))

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.sendmail(email_from, email_to.split(","), msg.as_string())

            logger.info(f"Email notification sent to {email_to}")
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")

    def _notify_wecom(self, event: AlertEvent) -> None:
        """企业微信通知（实际发送 Webhook 请求）

        企业微信机器人 Webhook 格式。
        环境变量: ALERT_WECOM_WEBHOOK_URL
        """
        import os

        wecom_url = os.getenv("ALERT_WECOM_WEBHOOK_URL")
        if not wecom_url:
            logger.debug("WeCom webhook not configured, skipping wecom notification")
            return

        try:
            import httpx

            # 企业微信 markdown 消息格式
            severity_emoji = {
                "critical": "🔴",
                "warning": "🟡",
                "info": "🔵",
            }.get(event.severity.value, "⚪")

            content = f"""
{severity_emoji} **告警通知**

**规则名称**: {event.rule_name}
**告警级别**: {event.severity.value.upper()}
**告警消息**: {event.message}
**告警时间**: {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(event.created_at))}
"""
            if event.metrics:
                content += "\n**指标详情**:\n"
                for key, value in event.metrics.items():
                    content += f"- {key}: {value}\n"

            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": content.strip(),
                },
            }

            with httpx.Client(timeout=5.0) as client:
                response = client.post(wecom_url, json=payload)
                if response.status_code >= 400:
                    logger.error(f"WeCom notification failed: status={response.status_code}, body={response.text[:200]}")
                else:
                    result = response.json()
                    if result.get("errcode") == 0:
                        logger.info("WeCom notification sent successfully")
                    else:
                        logger.error(f"WeCom notification failed: {result}")
        except Exception as e:
            logger.error(f"Failed to send wecom notification: {e}")

    def get_active_alerts(self) -> list[AlertEvent]:
        """获取活跃告警（待处理 + 已确认）"""
        return [event for event in self.events if event.status in (AlertStatus.PENDING, AlertStatus.ACKNOWLEDGED)]

    def acknowledge_alert(self, alert_id: str, acknowledged_by: str = "system") -> bool:
        """确认告警"""
        for event in self.events:
            if event.id == alert_id:
                event.status = AlertStatus.ACKNOWLEDGED
                event.acknowledged_at = time.time()
                event.acknowledged_by = acknowledged_by
                logger.info(f"Alert {alert_id} acknowledged by {acknowledged_by}")
                return True
        return False

    def resolve_alert(self, alert_id: str, notes: str = "") -> bool:
        """解决告警"""
        for event in self.events:
            if event.id == alert_id:
                event.status = AlertStatus.RESOLVED
                event.resolved_at = time.time()
                event.notes = notes
                logger.info(f"Alert {alert_id} resolved: {notes}")
                return True
        return False

    def get_alert_stats(self) -> dict[str, Any]:
        """获取告警统计"""
        total = len(self.events)
        pending = len([e for e in self.events if e.status == AlertStatus.PENDING])
        acknowledged = len([e for e in self.events if e.status == AlertStatus.ACKNOWLEDGED])
        resolved = len([e for e in self.events if e.status == AlertStatus.RESOLVED])
        by_severity = {severity.value: len([e for e in self.events if e.severity == severity]) for severity in AlertSeverity}
        return {
            "total_alerts": total,
            "pending": pending,
            "acknowledged": acknowledged,
            "resolved": resolved,
            "by_severity": by_severity,
            "active_rules": len([r for r in self.rules.values() if r.enabled]),
            "total_rules": len(self.rules),
        }


# 全局告警管理器实例
_alert_manager: AlertManager | None = None


def get_alert_manager() -> AlertManager:
    """获取全局告警管理器实例"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
        _register_default_alert_rules(_alert_manager)
    return _alert_manager


def _register_default_alert_rules(manager: AlertManager) -> None:
    """注册默认告警规则"""
    # 规则 1: 成功率 < 90%
    manager.add_rule(
        AlertRule(
            name="low_success_rate",
            description="API 成功率低于 90%",
            severity=AlertSeverity.CRITICAL,
            condition=lambda m: m.get("success_rate", 100) < 90,
            cooldown_seconds=300,
            notification_channels=["log"],
        )
    )

    # 规则 2: 错误率 > 5%
    manager.add_rule(
        AlertRule(
            name="high_error_rate",
            description="API 错误率高于 5%",
            severity=AlertSeverity.WARNING,
            condition=lambda m: m.get("error_rate", 0) > 5,
            cooldown_seconds=300,
            notification_channels=["log"],
        )
    )

    # 规则 3: 平均延迟 > 5 秒
    manager.add_rule(
        AlertRule(
            name="high_latency",
            description="API 平均延迟高于 5 秒",
            severity=AlertSeverity.WARNING,
            condition=lambda m: m.get("avg_latency", 0) > 5,
            cooldown_seconds=600,
            notification_channels=["log"],
        )
    )

    # 规则 4: BYOK 密钥成功率 < 80%
    manager.add_rule(
        AlertRule(
            name="byok_low_success_rate",
            description="BYOK 密钥成功率低于 80%",
            severity=AlertSeverity.WARNING,
            condition=lambda m: m.get("byok_success_rate", 100) < 80,
            cooldown_seconds=600,
            notification_channels=["log"],
        )
    )

    logger.info("Default alert rules registered")
