-- Procrastinate Schema 初始化
-- 基于 PostgreSQL 的任务队列表结构
-- 参考：https://procrastinate.readthedocs.io/

-- 注意：实际 schema 由 `procrastinate schema --apply` 命令生成
-- 此文件用于手动创建或参考表结构

-- 任务表
CREATE TABLE IF NOT EXISTS procrastinate_jobs (
    id BIGSERIAL PRIMARY KEY,
    queue_name VARCHAR(128) NOT NULL DEFAULT 'default',
    task_name VARCHAR(128) NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    lock TEXT,
    args JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'todo',
    scheduled_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    queueing_lock TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    attempted_at TIMESTAMPTZ,
    CONSTRAINT procrastinate_jobs_queue_task_unique UNIQUE (queue_name, task_name, queueing_lock)
);

-- 索引
CREATE INDEX IF NOT EXISTS procrastinate_jobs_queue_status_idx ON procrastinate_jobs (queue_name, status);
CREATE INDEX IF NOT EXISTS procrastinate_jobs_scheduled_at_idx ON procrastinate_jobs (scheduled_at) WHERE scheduled_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS procrastinate_jobs_lock_idx ON procrastinate_jobs (lock) WHERE lock IS NOT NULL;

-- 事件表（用于审计和监控）
CREATE TABLE IF NOT EXISTS procrastinate_events (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES procrastinate_jobs(id) ON DELETE CASCADE,
    type VARCHAR(32) NOT NULL,
    at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS procrastinate_events_job_id_idx ON procrastinate_events (job_id);

-- 周期性任务表
CREATE TABLE IF NOT EXISTS procrastinate_periodic_defers (
    id BIGSERIAL PRIMARY KEY,
    task_name VARCHAR(128) NOT NULL,
    defer_timestamp BIGINT NOT NULL,
    queue_name VARCHAR(128) NOT NULL DEFAULT 'default',
    priority INTEGER NOT NULL DEFAULT 0,
    lock TEXT,
    args JSONB NOT NULL DEFAULT '{}'::jsonb,
    queueing_lock TEXT,
    owner TEXT,
    UNIQUE (task_name, defer_timestamp, queueing_lock)
);

-- 管理视图：队列状态
CREATE OR REPLACE VIEW procrastinate_queue_stats AS
SELECT
    queue_name,
    status,
    COUNT(*) as job_count,
    MIN(created_at) as oldest_job,
    MAX(created_at) as newest_job
FROM procrastinate_jobs
GROUP BY queue_name, status
ORDER BY queue_name, status;

-- 管理视图：失败任务
CREATE OR REPLACE VIEW procrastinate_failed_jobs AS
SELECT
    j.id,
    j.queue_name,
    j.task_name,
    j.args,
    j.attempts,
    j.created_at,
    j.started_at,
    e.details as last_error
FROM procrastinate_jobs j
LEFT JOIN LATERAL (
    SELECT details
    FROM procrastinate_events
    WHERE job_id = j.id AND type = 'job_failed'
    ORDER BY at DESC
    LIMIT 1
) e ON true
WHERE j.status = 'failed'
ORDER BY j.attempted_at DESC NULLS LAST;

-- 注释
COMMENT ON TABLE procrastinate_jobs IS 'Procrastinate 任务队列表';
COMMENT ON TABLE procrastinate_events IS 'Procrastinate 任务事件表（审计日志）';
COMMENT ON TABLE procrastinate_periodic_defers IS 'Procrastinate 周期性任务表';
COMMENT ON VIEW procrastinate_queue_stats IS '队列状态统计视图';
COMMENT ON VIEW procrastinate_failed_jobs IS '失败任务视图（含最后错误信息）';
