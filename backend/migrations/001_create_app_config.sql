-- ============================================
-- app_config 配置中心表 — 大厂标准做法
-- 统一管理运行时可配置项，无需重启服务
-- ============================================

-- 1. 创建表
CREATE TABLE IF NOT EXISTS app_config (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(255) NOT NULL UNIQUE,
    config_value JSONB NOT NULL,
    config_type VARCHAR(50) NOT NULL DEFAULT 'string',
    description TEXT,
    category VARCHAR(100) NOT NULL DEFAULT 'general',
    is_public BOOLEAN NOT NULL DEFAULT false,
    is_encrypted BOOLEAN NOT NULL DEFAULT false,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. 创建索引
CREATE INDEX IF NOT EXISTS idx_app_config_category ON app_config(category);
CREATE INDEX IF NOT EXISTS idx_app_config_is_public ON app_config(is_public);
CREATE INDEX IF NOT EXISTS idx_app_config_updated_at ON app_config(updated_at);

-- 3. 插入初始配置
INSERT INTO app_config (config_key, config_value, config_type, description, category, is_public) VALUES
    ('ai.gateway.enabled', 'true'::jsonb, 'boolean', 'AI 网关总开关', 'ai', true),
    ('ai.gateway.timeout_seconds', '30'::jsonb, 'number', 'AI 网关请求超时（秒）', 'ai', true),
    ('ai.gateway.retry_count', '2'::jsonb, 'number', 'AI 网关失败重试次数', 'ai', true),
    ('byok.enabled', 'true'::jsonb, 'boolean', 'BYOK 用户自带密钥功能开关', 'byok', true),
    ('byok.stats_store', '"insforge"'::jsonb, 'string', 'BYOK 统计持久化存储', 'byok', true),
    ('byok.encryption_enabled', 'true'::jsonb, 'boolean', 'BYOK 密钥加密存储开关', 'byok', false),
    ('payment.antom.enabled', 'true'::jsonb, 'boolean', 'Antom 支付开关', 'payment', true),
    ('payment.paypal.enabled', 'true'::jsonb, 'boolean', 'PayPal 支付开关', 'payment', true),
    ('payment.mode', '"phase1"'::jsonb, 'string', '支付模式', 'payment', true),
    ('moderation.enabled', 'true'::jsonb, 'boolean', '内容审核总开关', 'security', true),
    ('moderation.provider', '"llm"'::jsonb, 'string', '内容审核提供商', 'security', true),
    ('moderation.auto_block', 'true'::jsonb, 'boolean', '审核不通过自动拦截', 'security', true),
    ('feature.pwa_enabled', 'true'::jsonb, 'boolean', 'PWA 功能开关', 'feature', true),
    ('feature.i18n_enabled', 'true'::jsonb, 'boolean', '国际化功能开关', 'feature', true),
    ('feature.marketplace_enabled', 'true'::jsonb, 'boolean', '商城功能开关', 'feature', true),
    ('feature.studio_enabled', 'true'::jsonb, 'boolean', 'AI Studio 功能开关', 'feature', true),
    ('feature.drama_enabled', 'true'::jsonb, 'boolean', '短剧创作功能开关', 'feature', true),
    ('general.site_name', '"新我人 XinWoRen"'::jsonb, 'string', '站点名称', 'general', true),
    ('general.site_url', '"https://xinworen.com"'::jsonb, 'string', '站点 URL', 'general', true),
    ('general.default_locale', '"zh"'::jsonb, 'string', '默认语言', 'general', true),
    ('general.support_email', '"support@xinworen.com"'::jsonb, 'string', '客服邮箱', 'general', true)
ON CONFLICT (config_key) DO NOTHING;

-- 4. 创建更新时间触发器
CREATE OR REPLACE FUNCTION update_app_config_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_app_config_updated_at ON app_config;
CREATE TRIGGER trg_app_config_updated_at
    BEFORE UPDATE ON app_config
    FOR EACH ROW
    EXECUTE FUNCTION update_app_config_updated_at();

-- 5. 验证
SELECT config_key, config_type, category, is_public, updated_at
FROM app_config
ORDER BY category, config_key;
