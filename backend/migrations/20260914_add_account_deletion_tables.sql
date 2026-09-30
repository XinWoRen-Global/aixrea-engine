-- 账户删除请求表和数据删除审计日志表
-- 用于GDPR/CCPA合规的账户删除功能
-- 创建时间: 2026-09-14

-- 账户删除请求表
CREATE TABLE IF NOT EXISTS account_deletion_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending/confirmed/cancelled/completed
    reason TEXT, -- 删除原因
    confirm_token VARCHAR(100), -- 确认邮件中的token
    scheduled_at TIMESTAMP NOT NULL, -- 计划删除时间（当前时间+7天）
    cancelled_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 数据删除审计日志表
CREATE TABLE IF NOT EXISTS data_deletion_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL, -- request_delete/confirm_delete/cancel_delete/complete_delete
    actor VARCHAR(50) NOT NULL, -- user/system/admin
    actor_id UUID, -- 操作者ID（系统操作时为空）
    details JSONB, -- 详细信息（删除原因、删除的数据类型、数据量等）
    ip_address VARCHAR(45), -- 操作者IP地址
    user_agent TEXT, -- 操作者User Agent
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_account_deletion_requests_user_id ON account_deletion_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_account_deletion_requests_status ON account_deletion_requests(status);
CREATE INDEX IF NOT EXISTS idx_account_deletion_requests_scheduled_at ON account_deletion_requests(scheduled_at);

CREATE INDEX IF NOT EXISTS idx_data_deletion_audit_logs_user_id ON data_deletion_audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_data_deletion_audit_logs_action ON data_deletion_audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_data_deletion_audit_logs_created_at ON data_deletion_audit_logs(created_at);

-- 添加注释
COMMENT ON TABLE account_deletion_requests IS '账户删除请求表';
COMMENT ON COLUMN account_deletion_requests.status IS '状态: pending/confirmed/cancelled/completed';
COMMENT ON COLUMN account_deletion_requests.scheduled_at IS '计划删除时间（7天冷静期后）';

COMMENT ON TABLE data_deletion_audit_logs IS '数据删除审计日志表';
COMMENT ON COLUMN data_deletion_audit_logs.action IS '操作类型: request_delete/confirm_delete/cancel_delete/complete_delete';
COMMENT ON COLUMN data_deletion_audit_logs.actor IS '操作者: user/system/admin';
