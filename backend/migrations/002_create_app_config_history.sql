-- ============================================
-- app_config_history 配置版本历史表 — 大厂标准做法
-- 记录每次配置修改，支持回滚到历史版本
-- ============================================

-- 1. 创建表
CREATE TABLE IF NOT EXISTS app_config_history (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(255) NOT NULL,           -- 配置键
    old_value JSONB,                              -- 修改前的值
    new_value JSONB,                              -- 修改后的值
    config_type VARCHAR(50) NOT NULL DEFAULT 'string', -- 配置类型
    change_type VARCHAR(20) NOT NULL DEFAULT 'update', -- 操作类型：create/update/delete/rollback
    description TEXT,                             -- 修改说明
    changed_by VARCHAR(100),                      -- 修改人
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- 修改时间
    rollback_to_id INT,                           -- 回滚到的历史记录 ID（仅 rollback 操作）
    metadata JSONB DEFAULT '{}'::jsonb            -- 元数据（IP、User-Agent 等）
);

-- 2. 创建索引
CREATE INDEX IF NOT EXISTS idx_app_config_history_config_key ON app_config_history(config_key);
CREATE INDEX IF NOT EXISTS idx_app_config_history_changed_at ON app_config_history(changed_at);
CREATE INDEX IF NOT EXISTS idx_app_config_history_changed_by ON app_config_history(changed_by);
CREATE INDEX IF NOT EXISTS idx_app_config_history_change_type ON app_config_history(change_type);

-- 3. 创建更新时间触发器（自动更新 changed_at）
CREATE OR REPLACE FUNCTION update_app_config_history_changed_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.changed_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_app_config_history_changed_at ON app_config_history;
CREATE TRIGGER trg_app_config_history_changed_at
    BEFORE UPDATE ON app_config_history
    FOR EACH ROW
    EXECUTE FUNCTION update_app_config_history_changed_at();

-- 4. 验证
SELECT config_key, change_type, changed_by, changed_at
FROM app_config_history
ORDER BY changed_at DESC
LIMIT 10;
