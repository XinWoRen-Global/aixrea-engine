-- 迁移：为 studio_generation_tasks 表添加缺失的 scheduled_at 列
-- 日期：2026-09-04
-- 原因：generation_queue.py 使用 scheduled_at 进行任务调度（优先级+延迟重试）
--       但表结构中缺少此列，导致 enqueue/claim/retry 全部失败

-- 1. 添加 scheduled_at 列（带默认值，兼容已有数据）
ALTER TABLE studio_generation_tasks
ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- 2. 为已有数据回填 scheduled_at（使用 created_at 或 now()）
UPDATE studio_generation_tasks
SET scheduled_at = COALESCE(created_at, NOW())
WHERE scheduled_at IS NULL;

-- 3. 添加索引：加速 claim_next_ready 的查询（status + scheduled_at + priority）
CREATE INDEX IF NOT EXISTS idx_studio_generation_tasks_scheduled
ON studio_generation_tasks (status, scheduled_at, priority DESC);

-- 4. 验证列已添加
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'studio_generation_tasks'
AND column_name = 'scheduled_at';

-- 5. 验证索引已创建
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'studio_generation_tasks'
AND indexname LIKE '%scheduled%';
