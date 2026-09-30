-- HOH (Harness-of-Harness) evidence tables
-- Design: devops/docs/hoh-orchestrator-design-v1.md
-- Created: 2026-09-15
--
-- Phase 0: skeleton. This migration ships the schema only; the
-- in-memory evidence store is used until the Postgres adapter lands.

-- Per-module registration (mirrors hoh/modules/*.yaml)
CREATE TABLE IF NOT EXISTS hoh_modules (
    name VARCHAR(100) PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL,
    developer_kind VARCHAR(50) NOT NULL DEFAULT 'lead_agent',
    entry TEXT NOT NULL,
    tools_allowlist JSONB NOT NULL DEFAULT '[]'::jsonb,
    qa_blackbox JSONB NOT NULL DEFAULT '[]'::jsonb,
    qa_whitebox JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_ttl_days INT NOT NULL DEFAULT 30,
    cost_budget_per_loop_usd NUMERIC(10,4) NOT NULL DEFAULT 0.50,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Cross-loop evidence store
CREATE TABLE IF NOT EXISTS hoh_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    module VARCHAR(100) NOT NULL,
    iteration INT NOT NULL,
    type VARCHAR(20) NOT NULL, -- verified / gap / regression / reopened
    description TEXT NOT NULL,
    artifact_ref TEXT,
    metric JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_hoh_evidence_module
    ON hoh_evidence (module, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hoh_evidence_type
    ON hoh_evidence (module, type);

-- One HoH loop record (for audit / replay)
CREATE TABLE IF NOT EXISTS hoh_loops (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    module VARCHAR(100) NOT NULL,
    iteration INT NOT NULL,
    dev_doc JSONB NOT NULL,
    artifact_ref TEXT,
    stopped_reason VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Insert the drama module as the first registered module.
INSERT INTO hoh_modules (name, display_name, developer_kind, entry)
VALUES ('drama', '短剧智能体', 'pipeline', 'deerflow.pipeline.executor:PipelineExecutor')
ON CONFLICT (name) DO NOTHING;
