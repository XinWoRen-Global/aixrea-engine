"""
Agent 配置健康检查模块

在 Gateway 启动时检查必需的 agent 配置是否存在，
缺失时记录警告（不阻止启动，避免过度严格）。

用法:
    from app.gateway.agent_config_healthcheck import verify_agent_config_at_startup
    verify_agent_config_at_startup()
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# 必需的 agent 列表（创作类智能体）
REQUIRED_AGENTS = [
    "drama",
    "drama-executor",
    "drama-producer",
    "comics",
    "comics-executor",
    "comic-producer",
    "music",
    "music-executor",
    "music-producer",
    "interactive",
    "interactive-executor",
    "novel-executor",
    "novel-producer",
]


def get_agents_dir() -> Path:
    """获取 agent 配置目录。"""
    deer_flow_home = os.environ.get("DEER_FLOW_HOME", "/app/backend/.deer-flow")
    return Path(deer_flow_home) / "users" / "default" / "agents"


def verify_agent_config_at_startup() -> dict:
    """启动时检查 agent 配置完整性。

    Returns:
        dict: 检查结果，包含 missing, existing, agents_dir
    """
    agents_dir = get_agents_dir()

    missing = []
    existing = []

    if not agents_dir.exists():
        logger.warning(f"[AgentConfig] Agent 配置目录不存在: {agents_dir} （如果使用外部 volume，请确保 volume 已正确挂载）")
        return {
            "missing": REQUIRED_AGENTS,
            "existing": [],
            "agents_dir": str(agents_dir),
            "dir_exists": False,
        }

    for agent in REQUIRED_AGENTS:
        agent_path = agents_dir / agent
        config_path = agent_path / "config.yaml"

        if agent_path.exists() and config_path.exists():
            existing.append(agent)
        else:
            missing.append(agent)
            if not agent_path.exists():
                logger.warning(f"[AgentConfig] 缺失 agent 目录: {agent} ({agent_path})")
            else:
                logger.warning(f"[AgentConfig] 缺失 agent 配置文件: {agent}/config.yaml")

    if missing:
        logger.warning(f"[AgentConfig] 发现 {len(missing)}/{len(REQUIRED_AGENTS)} 个缺失的 agent 配置: {', '.join(missing)}")
        logger.warning("[AgentConfig] 这可能导致相关智能体功能异常。请检查 Docker volume 挂载是否正确，或运行 scripts/verify_agent_config.py --fix 自动修复。")
    else:
        logger.info(f"[AgentConfig] 所有 {len(existing)}/{len(REQUIRED_AGENTS)} 个必需 agent 配置都已存在")

    return {
        "missing": missing,
        "existing": existing,
        "agents_dir": str(agents_dir),
        "dir_exists": True,
    }


def get_agent_config_status() -> dict:
    """获取 agent 配置状态（供健康检查 API 调用）。"""
    result = verify_agent_config_at_startup()
    return {
        "total_required": len(REQUIRED_AGENTS),
        "existing": len(result["existing"]),
        "missing": len(result["missing"]),
        "missing_agents": result["missing"],
        "agents_dir": result["agents_dir"],
        "healthy": len(result["missing"]) == 0,
    }
