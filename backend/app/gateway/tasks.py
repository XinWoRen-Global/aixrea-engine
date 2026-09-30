"""
后台任务定义 - 基于 Procrastinate 的异步任务

包含：
- 僵尸项目清理（定时任务）
- 队列健康检查（定时任务）
- Checkpointer 数据清理（定时任务）

设计原则：
- 每个任务独立，可单独重试
- 任务参数简单，可序列化
- 任务结果记录到日志和事件表
"""

import logging
from datetime import datetime, timedelta

from .task_queue import QUEUE_CLEANUP, app

logger = logging.getLogger(__name__)


@app.task(queue=QUEUE_CLEANUP, name="cleanup_stale_albums", retry=3)
async def cleanup_stale_albums(
    stale_hours: int = 24,
    dry_run: bool = False,
) -> dict:
    """
    清理僵尸项目（停滞超过指定小时数的项目）

    参数：
        stale_hours: 停滞多少小时算僵尸项目（默认24小时）
        dry_run: 是否只统计不实际清理（默认False）

    返回：
        清理结果统计
    """
    logger.info(f"Starting stale albums cleanup: stale_hours={stale_hours}, dry_run={dry_run}")

    try:
        # 导入数据库连接（延迟导入避免循环依赖）
        from app.gateway.deps import get_db

        async with get_db() as conn:
            # 查询僵尸项目
            cutoff_time = datetime.utcnow() - timedelta(hours=stale_hours)
            result = await conn.fetch(
                """
                SELECT id, title, status, updated_at
                FROM studio_albums
                WHERE status IN ('queued', 'running', 'paused')
                AND updated_at < $1
                ORDER BY updated_at ASC
                """,
                cutoff_time,
            )

            stale_count = len(result)
            logger.info(f"Found {stale_count} stale albums")

            if dry_run:
                return {
                    "stale_count": stale_count,
                    "dry_run": True,
                    "albums": [dict(row) for row in result[:10]],  # 只返回前10个
                }

            # 重置僵尸项目状态为 draft
            cleaned_count = 0
            for row in result:
                await conn.execute(
                    """
                    UPDATE studio_albums
                    SET status = 'draft', updated_at = NOW()
                    WHERE id = $1
                    """,
                    row["id"],
                )
                cleaned_count += 1
                logger.info(f"Reset stale album: {row['id']} ({row['title']})")

            return {
                "stale_count": stale_count,
                "cleaned_count": cleaned_count,
                "dry_run": False,
            }

    except Exception as e:
        logger.error(f"Stale albums cleanup failed: {e}", exc_info=True)
        raise


@app.task(queue=QUEUE_CLEANUP, name="cleanup_checkpointer", retry=1)
async def cleanup_checkpointer(
    retain_per_thread: int = 20,
    dry_run: bool = False,
) -> dict:
    """
    清理 Checkpointer 旧数据

    参数：
        retain_per_thread: 每个 thread 保留多少个最新 checkpoint（默认20）
        dry_run: 是否只统计不实际清理

    返回：
        清理结果统计
    """
    logger.info(f"Starting checkpointer cleanup: retain_per_thread={retain_per_thread}, dry_run={dry_run}")

    try:
        from app.gateway.deps import get_db

        async with get_db() as conn:
            # 统计当前数据量
            total_checkpoints = await conn.fetchval("SELECT COUNT(*) FROM checkpoints")
            total_blobs = await conn.fetchval("SELECT COUNT(*) FROM checkpoint_blobs")
            total_writes = await conn.fetchval("SELECT COUNT(*) FROM checkpoint_writes")

            logger.info(f"Current: checkpoints={total_checkpoints}, blobs={total_blobs}, writes={total_writes}")

            if dry_run:
                return {
                    "total_checkpoints": total_checkpoints,
                    "total_blobs": total_blobs,
                    "total_writes": total_writes,
                    "dry_run": True,
                }

            # 删除每个 thread 超过 retain_per_thread 的旧 checkpoint
            # 使用窗口函数找到需要删除的 checkpoint id
            delete_result = await conn.execute(
                """
                WITH ranked AS (
                    SELECT
                        thread_id,
                        checkpoint_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY thread_id
                            ORDER BY checkpoint_id DESC
                        ) as rn
                    FROM checkpoints
                )
                DELETE FROM checkpoints
                WHERE checkpoint_id IN (
                    SELECT checkpoint_id FROM ranked WHERE rn > $1
                )
                """,
                retain_per_thread,
            )

            deleted_count = int(delete_result.split()[-1]) if delete_result else 0
            logger.info(f"Deleted {deleted_count} old checkpoints")

            return {
                "total_checkpoints_before": total_checkpoints,
                "deleted_checkpoints": deleted_count,
                "dry_run": False,
            }

    except Exception as e:
        logger.error(f"Checkpointer cleanup failed: {e}", exc_info=True)
        raise


@app.task(queue=QUEUE_CLEANUP, name="queue_health_check", retry=0)
async def queue_health_check() -> dict:
    """
    队列健康检查任务

    检查：
    - 队列深度
    - 失败任务数
    - 长时间运行的任务

    返回：
        健康检查结果
    """
    logger.info("Starting queue health check")

    try:
        from app.gateway.deps import get_db

        async with get_db() as conn:
            # 队列状态统计
            queue_stats = await conn.fetch(
                """
                SELECT queue_name, status, COUNT(*) as count
                FROM procrastinate_jobs
                GROUP BY queue_name, status
                ORDER BY queue_name, status
                """
            )

            # 失败任务
            failed_jobs = await conn.fetch(
                """
                SELECT id, queue_name, task_name, attempts, attempted_at
                FROM procrastinate_jobs
                WHERE status = 'failed'
                ORDER BY attempted_at DESC NULLS LAST
                LIMIT 10
                """
            )

            # 长时间运行的任务（超过30分钟）
            long_running = await conn.fetch(
                """
                SELECT id, queue_name, task_name, started_at,
                       EXTRACT(EPOCH FROM (NOW() - started_at)) as duration_seconds
                FROM procrastinate_jobs
                WHERE status = 'doing'
                AND started_at < NOW() - INTERVAL '30 minutes'
                ORDER BY started_at ASC
                """
            )

            result = {
                "queue_stats": [dict(row) for row in queue_stats],
                "failed_jobs_count": len(failed_jobs),
                "failed_jobs": [dict(row) for row in failed_jobs],
                "long_running_count": len(long_running),
                "long_running": [dict(row) for row in long_running],
                "checked_at": datetime.utcnow().isoformat(),
            }

            # 如果有失败任务或长时间运行任务，记录警告
            if len(failed_jobs) > 0:
                logger.warning(f"Found {len(failed_jobs)} failed jobs")
            if len(long_running) > 0:
                logger.warning(f"Found {len(long_running)} long-running jobs")

            return result

    except Exception as e:
        logger.error(f"Queue health check failed: {e}", exc_info=True)
        raise


# 导出任务列表（用于注册和监控）
TASK_REGISTRY = {
    "cleanup_stale_albums": cleanup_stale_albums,
    "cleanup_checkpointer": cleanup_checkpointer,
    "queue_health_check": queue_health_check,
}
