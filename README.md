# Aixrea Engine — Multi-Agent Orchestration Framework

> Production-grade agent harness for building AI-powered products.
> Orchestrate sub-agents, memory, sandboxes, and extensible skills — powered by LangGraph.

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](./backend/pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Framework: LangGraph](https://img.shields.io/badge/Framework-LangGraph-FF6B6B)](https://langchain-ai.github.io/langgraph/)

---

## What is Aixrea Engine?

Aixrea Engine is an open-source **super agent harness** that orchestrates **sub-agents**, **memory**, and **sandboxes** to build production AI applications. It provides a flexible, extensible foundation for:

- 🤖 **Multi-agent orchestration** — Lead Agent coordinates specialized sub-agents
- 🧠 **Persistent memory** — Short-term, long-term, and summary memory
- 🛠️ **Extensible skills** — Build and publish AI tools as reusable skills
- 🔄 **DAG pipelines** — Deterministic workflow execution for content creation
- 🔒 **Content guardrails** — Pluggable moderation framework for AI output
- 💬 **Community IM** — Real-time chat with AI employees

Built on **LangGraph** for reliable, recoverable agent workflows.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Lead Agent                      │
│  (Plan-and-Execute + ReAct hybrid, 15+ middleware)│
├──────────┬──────────┬───────────┬────────────────┤
│  Memory   │  Skills  │  Sandbox  │  Sub-agents    │
│  (short/  │  (tool   │  (code    │  (specialized  │
│   long/    │  market) │   exec)   │   workers)     │
│   summary) │          │           │                │
├──────────┴──────────┴───────────┴────────────────┤
│              PipelineExecutor (DAG)                │
│     (deterministic workflows for content creation)  │
├────────────────────────────────────────────────────┤
│              AIGateway (model routing)              │
│     (multi-model abstraction, fallback, tracking)   │
└────────────────────────────────────────────────────┘
```

### Three-Layer Control Model

| Layer | Pattern | Use Case |
|---|---|---|
| **Workflow Graph** | DAG (deterministic) | Main execution trunk, billing, recovery |
| **Plan-and-Execute** | Task decomposition | Complex multi-step tasks |
| **ReAct** | Local exploration | Unknown environments, tool discovery |

---

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 22+ (for frontend/tooling)
- Redis (for memory/cache)
- An LLM API key (OpenAI, Anthropic, or compatible)

### Installation

```bash
# Clone
git clone https://github.com/aixrea/engine.git
cd engine

# Install backend dependencies
cd backend
pip install -e .

# Configure
cp .env.example .env
# Edit .env with your LLM API keys

# Run
uvicorn app.main:app --reload --port 8001
```

### Minimal Example

```python
from aixrea_engine import LeadAgent, SkillRegistry

# Initialize
agent = LeadAgent(
    model="gpt-4o",
    skills=SkillRegistry.default(),
    memory=True,
)

# Run
result = await agent.run("Research the top 3 AI frameworks in 2026")
print(result.summary)
```

See [`examples/`](./examples) for more.

---

## Core Modules

| Module | Description | Status |
|---|---|---|
| `agents.lead_agent` | Core execution engine with 15+ middleware | ✅ Stable |
| `agents.memory` | Short/long-term/summary memory | ✅ Stable |
| `agents.subagents` | Sub-agent orchestration | ✅ Stable |
| `runtime` | FastAPI server, auth, config | ✅ Stable |
| `skills` | Skill registry and execution framework | ✅ Stable |
| `sandbox` | Code execution sandbox | ⚠️ Preview |
| `guardrails` | Content moderation framework | ⚠️ Preview |
| `persistence` | Database persistence layer | ✅ Stable |
| `tracing` | OpenTelemetry tracing | ✅ Stable |
| `scheduler` | Task scheduling | ⚠️ Preview |

---

## Skills System

Build and publish AI tools as reusable skills:

```python
from aixrea_engine import skill, SkillContext

@skill(name="web_search", description="Search the web")
async def web_search(ctx: SkillContext, query: str) -> str:
    # Your implementation
    return results

# Register
registry = SkillRegistry()
registry.register(web_search)
```

### Marketplace Revenue Share

Tool developers are **creators** on the platform. Skill revenue follows the existing **CreatorTier** system (same as drama/music/comic creators):

| Creator Tier | Developer Share | Platform |
|---|---|---|
| Bronze | 50% | 50% |
| Silver | 60% | 40% |
| Gold / Platinum | 70% | 30% |

- **No separate commission system** — one account, one tier, all revenue types unified
- **Payout**: Monthly via Stripe, $10 minimum
- **No exclusivity**: Publish your skills anywhere
- **You retain ownership** of your skill code

Affiliate referrals follow the existing affiliate program (up to 25%, 30-day cookie).

See [COMMERCIAL.md](./COMMERCIAL.md) for details.

---

## Commercial Use

This project is **MIT licensed** for personal, research, and internal use.

For commercial use (SaaS, enterprise deployment, resale, or embedding in proprietary products), please contact us for a commercial license. We offer:

- **Startup license**: Revenue-based, no upfront cost
- **Enterprise license**: Per-instance, with SLA and support
- **OEM license**: White-label, embed in your product

Contact: `contact@xinworen.com`

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

**Note**: This project is currently in **read-only open source** mode. We release the code for transparency and learning, but we are not accepting pull requests at this time. Please open issues for bug reports and feature requests.

---

## License

[MIT](./LICENSE) — Copyright (c) 2026 **XinWoRen Pte. Ltd. (Singapore)** / Aixrea. All rights reserved.

---

> Built with LangGraph. Powered by the global creator community.
> [aixrea.com](https://aixrea.com) · [xinworen.com](https://xinworen.com)
> XinWoRen (新我人) — AI creation platform for global creators
