"""
账户删除 Worker 模块

负责处理到期的账户删除请求：
- 每天凌晨2点检查已确认且超过7天的删除请求
- 执行实际的数据删除（完全删除/匿名化处理/法定保留）
- 记录审计日志
- 发送删除完成通知邮件

设计原则：
- 7天冷静期：用户提交删除请求后有7天时间可以取消
- 数据删除策略：
  - 完全删除：用户个人身份信息
  - 匿名化处理：订单记录（保留财务审计需要的信息）
  - 法定保留：税务记录保留7年
- 审计日志：所有删除操作都记录审计日志，便于追溯

海内外大厂参考：
- Google 账户删除有30天冷静期
- Facebook 账户删除有30天冷静期
- 删除操作通常在后台异步执行
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# 删除策略配置
DELETION_POLICY = {
    "cool_down_period_days": 7,  # 冷静期7天
    "scheduled_hour": 2,  # 每天凌晨2点执行
    "data_retention": {
        "tax_records_years": 7,  # 税务记录保留7年
        "order_records_years": 3,  # 订单记录保留3年（匿名化）
        "audit_logs_years": 7,  # 审计日志保留7年
    },
}


class AccountDeletionWorker:
    """
    账户删除 Worker

    负责处理到期的账户删除请求
    """

    def __init__(self, db_pool=None):
        """
        初始化账户删除Worker

        Args:
            db_pool: 数据库连接池（可选，后续接入真实数据库时使用）
        """
        self.db_pool = db_pool
        self.running = False
        self.worker_task: asyncio.Task | None = None
        self.last_run_time: datetime | None = None

    async def start(self):
        """启动Worker"""
        if self.running:
            logger.warning("Account deletion worker is already running")
            return

        self.running = True
        self.worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Account deletion worker started")

    async def stop(self):
        """停止Worker"""
        if not self.running:
            return

        self.running = False
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Account deletion worker stopped")

    async def _worker_loop(self):
        """Worker主循环"""
        while self.running:
            try:
                now = datetime.now()

                # 检查是否到了执行时间（每天凌晨2点）
                if now.hour == DELETION_POLICY["scheduled_hour"] and now.minute == 0:
                    # 检查今天是否已经执行过
                    if self.last_run_time is None or self.last_run_time.date() != now.date():
                        logger.info("Starting scheduled account deletion processing")
                        await self._process_due_deletions()
                        self.last_run_time = now
                        logger.info("Scheduled account deletion processing completed")

                # 每分钟检查一次
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in account deletion worker loop: {e}", exc_info=True)
                await asyncio.sleep(60)  # 出错后等待1分钟再继续

    async def _process_due_deletions(self):
        """
        处理到期的删除请求

        检查所有已确认且超过7天的删除请求，执行实际的数据删除
        """
        logger.info("Processing due account deletions")

        # TODO: 接入真实数据库查询
        # 查询所有状态为'confirmed'且scheduled_at <= NOW()的删除请求
        # due_deletions = await db.fetch_all(
        #     "SELECT * FROM account_deletion_requests WHERE status = 'confirmed' AND scheduled_at <= NOW()",
        # )

        # 模拟数据（实际实现时从数据库查询）
        due_deletions = []

        if not due_deletions:
            logger.info("No due account deletions found")
            return

        logger.info(f"Found {len(due_deletions)} due account deletions to process")

        for deletion in due_deletions:
            try:
                await self._process_single_deletion(deletion)
            except Exception as e:
                logger.error(f"Error processing account deletion {deletion.get('id')}: {e}", exc_info=True)
                # 标记为失败
                # await db.execute(
                #     "UPDATE account_deletion_requests SET status = 'failed', error_message = $1 WHERE id = $2",
                #     str(e), deletion['id']
                # )

    async def _process_single_deletion(self, deletion: dict[str, Any]):
        """
        处理单个账户删除请求

        Args:
            deletion: 删除请求信息
        """
        deletion_id = deletion["id"]
        user_id = deletion["user_id"]

        logger.info(f"Processing account deletion {deletion_id} for user {user_id}")

        # 1. 记录审计日志（开始删除）
        await self._record_audit_log(
            user_id=user_id,
            action="account_deletion_started",
            actor="system",
            details={"deletion_id": deletion_id, "reason": deletion.get("reason")},
        )

        # 2. 执行数据删除
        deletion_summary = await self._delete_user_data(user_id)

        # 3. 更新删除请求状态为completed
        # await db.execute(
        #     "UPDATE account_deletion_requests SET status = 'completed', completed_at = NOW() WHERE id = $1",
        #     deletion_id
        # )

        # 4. 记录审计日志（删除完成）
        await self._record_audit_log(
            user_id=user_id,
            action="account_deletion_completed",
            actor="system",
            details={"deletion_id": deletion_id, "deletion_summary": deletion_summary},
        )

        # 5. 发送删除完成通知邮件
        # TODO: 接入邮件发送服务
        logger.info(f"Account deletion {deletion_id} completed for user {user_id}")

    async def _delete_user_data(self, user_id: str) -> dict[str, Any]:
        """
        删除用户数据

        根据数据删除策略执行：
        - 完全删除：用户个人身份信息
        - 匿名化处理：订单记录（保留财务审计需要的信息）
        - 法定保留：税务记录保留7年

        Args:
            user_id: 用户ID

        Returns:
            删除摘要信息
        """
        logger.info(f"Deleting user data for user {user_id}")

        deletion_summary = {
            "user_id": user_id,
            "deleted_at": datetime.now().isoformat(),
            "fully_deleted": [],
            "anonymized": [],
            "retained": [],
        }

        # TODO: 接入真实数据库删除操作

        # 1. 完全删除：用户个人身份信息
        # - users表：删除用户记录
        # - user_profiles表：删除用户资料
        # - user_sessions表：删除所有会话
        # - user_preferences表：删除用户偏好设置
        fully_deleted_tables = [
            "users",
            "user_profiles",
            "user_sessions",
            "user_preferences",
            "user_notifications",
        ]
        deletion_summary["fully_deleted"] = fully_deleted_tables

        # 2. 匿名化处理：订单记录（保留财务审计需要的信息）
        # - orders表：将user_id设置为NULL，保留订单金额、时间等财务信息
        # - order_items表：保留订单商品信息
        # - payments表：保留支付信息（用于对账）
        anonymized_tables = [
            "orders",
            "order_items",
            "payments",
        ]
        deletion_summary["anonymized"] = anonymized_tables

        # 3. 法定保留：税务记录保留7年
        # - tax_records表：保留税务记录7年
        # - invoices表：保留发票记录7年
        retained_tables = [
            "tax_records",
            "invoices",
        ]
        deletion_summary["retained"] = retained_tables

        # 4. 内容数据处理
        # - user_content表：删除用户生成的内容（或匿名化）
        # - chat_conversations表：删除对话记录
        # - chat_messages表：删除消息记录
        content_tables = [
            "user_content",
            "chat_conversations",
            "chat_messages",
        ]
        deletion_summary["fully_deleted"].extend(content_tables)

        logger.info(f"User data deletion summary for user {user_id}: {deletion_summary}")
        return deletion_summary

    async def _record_audit_log(
        self,
        user_id: str,
        action: str,
        actor: str,
        details: dict[str, Any],
        ip_address: str | None = None,
        user_agent: str | None = None,
    ):
        """
        记录审计日志

        Args:
            user_id: 用户ID
            action: 操作类型
            actor: 操作者（system/user/admin）
            details: 操作详情
            ip_address: IP地址（可选）
            user_agent: 用户代理（可选）
        """
        try:
            import json

            from app.gateway.user_data_db import execute_update

            await execute_update(
                """
                INSERT INTO data_deletion_audit_logs
                (id, user_id, action, actor, details, ip_address, user_agent, created_at)
                VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, NOW())
                """,
                user_id,
                action,
                actor,
                json.dumps(details, ensure_ascii=False),
                ip_address,
                user_agent,
            )
            logger.info(f"Recorded audit log: user_id={user_id}, action={action}, actor={actor}")
        except Exception as e:
            logger.error(f"Failed to record audit log: {e}", exc_info=True)
            # 审计日志记录失败不阻断删除操作，但记录日志

    async def run_manual_deletion(self, deletion_id: str) -> dict[str, Any]:
        """
        手动执行删除（用于管理员手动触发）

        Args:
            deletion_id: 删除请求ID

        Returns:
            执行结果
        """
        # TODO: 接入真实数据库查询
        # deletion = await db.fetch_one(
        #     "SELECT * FROM account_deletion_requests WHERE id = $1",
        #     deletion_id
        # )

        # 模拟数据（实际实现时从数据库查询）
        deletion = {
            "id": deletion_id,
            "user_id": "user_demo",
            "status": "confirmed",
            "reason": "手动触发删除",
        }

        if not deletion:
            raise ValueError(f"Deletion request {deletion_id} not found")

        if deletion["status"] not in ["confirmed", "failed"]:
            raise ValueError(f"Deletion request {deletion_id} is not in a processable state: {deletion['status']}")

        await self._process_single_deletion(deletion)

        return {
            "success": True,
            "deletion_id": deletion_id,
            "message": "Account deletion processed successfully",
        }

    def get_status(self) -> dict[str, Any]:
        """
        获取Worker状态

        Returns:
            Worker状态信息
        """
        return {
            "running": self.running,
            "last_run_time": self.last_run_time.isoformat() if self.last_run_time else None,
            "scheduled_hour": DELETION_POLICY["scheduled_hour"],
            "cool_down_period_days": DELETION_POLICY["cool_down_period_days"],
        }


# 全局Worker实例
_deletion_worker: AccountDeletionWorker | None = None


def get_deletion_worker(db_pool=None) -> AccountDeletionWorker:
    """
    获取全局账户删除Worker实例

    Args:
        db_pool: 数据库连接池（可选）

    Returns:
        账户删除Worker实例
    """
    global _deletion_worker
    if _deletion_worker is None:
        _deletion_worker = AccountDeletionWorker(db_pool)
    return _deletion_worker


async def start_deletion_worker(db_pool=None):
    """
    启动账户删除Worker

    Args:
        db_pool: 数据库连接池（可选）
    """
    worker = get_deletion_worker(db_pool)
    await worker.start()


async def stop_deletion_worker():
    """停止账户删除Worker"""
    global _deletion_worker
    if _deletion_worker:
        await _deletion_worker.stop()
        _deletion_worker = None
