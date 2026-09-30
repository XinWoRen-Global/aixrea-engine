-- 用户数据导出表
-- 用于存储用户数据导出任务的状态和结果
-- 创建时间: 2026-09-14

CREATE TABLE IF NOT EXISTS user_data_exports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending/processing/completed/failed
    format VARCHAR(10) NOT NULL DEFAULT 'json', -- json/csv
    scope JSONB NOT NULL DEFAULT '[]', -- 导出范围: ["account", "chat", "content", "orders", "preferences"]
    file_path VARCHAR(500), -- 导出文件存储路径（R2/S3）
    file_size BIGINT, -- 文件大小（字节）
    progress INTEGER DEFAULT 0, -- 0-100
    current_step VARCHAR(100), -- 当前步骤描述
    error_message TEXT, -- 失败时的错误信息
    expires_at TIMESTAMP, -- 过期时间（如7天后自动删除）
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_user_data_exports_user_id ON user_data_exports(user_id);
CREATE INDEX IF NOT EXISTS idx_user_data_exports_status ON user_data_exports(status);
CREATE INDEX IF NOT EXISTS idx_user_data_exports_created_at ON user_data_exports(created_at);

-- 添加注释
COMMENT ON TABLE user_data_exports IS '用户数据导出任务表';
COMMENT ON COLUMN user_data_exports.status IS '任务状态: pending/processing/completed/failed';
COMMENT ON COLUMN user_data_exports.format IS '导出格式: json/csv';
COMMENT ON COLUMN user_data_exports.scope IS '导出范围: ["account", "chat", "content", "orders", "preferences"]';
COMMENT ON COLUMN user_data_exports.progress IS '导出进度: 0-100';
