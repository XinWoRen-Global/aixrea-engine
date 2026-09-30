# Aixrea Engine — Production-Grade Multi-Agent Orchestration Framework for LLM Apps

> The open-source **super agent harness** for building production AI applications. Orchestrate autonomous agents, persistent memory, code sandboxes, and extensible skills — powered by LangGraph. An alternative to LangChain agents, CrewAI, and AutoGPT for production workloads.

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](./backend/pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Framework: LangGraph](https://img.shields.io/badge/Framework-LangGraph-FF6B6B)](https://langchain-ai.github.io/langgraph/)
[![Multi-Agent](https://img.shields.io/badge/Multi--Agent-✓-brightgreen)]()
[![DAG Workflow](https://img.shields.io/badge/DAG-Workflow-blue)]()
[![RAG Ready](https://img.shields.io/badge/RAG-Ready-orange)]()

**English** | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [Français](README.fr.md) | [Русский](README.ru.md)

---

## ⭐ Why Star Aixrea Engine?

If you're building **LLM-powered applications** that need to go beyond demo-grade chatbots, Aixrea Engine gives you:

- **Production reliability** — deterministic DAG execution with checkpoint recovery, not just ReAct loops
- **Multi-agent orchestration** — a Lead Agent coordinates specialized sub-agents with 15+ middleware
- **Real memory** — short-term, long-term, and summary memory with Redis persistence
- **Skill marketplace** — build, publish, and monetize AI tools as reusable skills
- **Billing-ready** — token tracking and credits ledger for SaaS monetization
- **Content guardrails** — pluggable moderation for AI output safety

Built on **LangGraph** for reliable, recoverable agent workflows. Battle-tested in production at [aixrea.com](https://aixrea.com) and [xinworen.com](https://xinworen.com), powering thousands of AI content creation workflows (drama, music, comics, novels, interactive stories).

---

## What is Aixrea Engine?

Aixrea Engine is an open-source **agent runtime and orchestration framework** for building production-grade **autonomous AI agents**, **LLM applications**, and **AI agent workflows**. It provides a flexible, extensible foundation for:

- 🤖 **Multi-agent orchestration** — Lead Agent coordinates specialized sub-agents with 15+ middleware (memory, summary, todo, loop detection, sub-agent limits)
- 🧠 **Persistent memory** — Short-term, long-term, and summary memory with Redis persistence for RAG and context management
- 🛠️ **Extensible skills / tool use** — Build and publish AI tools as reusable skills with function calling and structured output
- 🔄 **DAG pipelines / workflow automation** — Deterministic workflow execution for content creation, data processing, and agentic automation
- 🔒 **Content guardrails / AI safety** — Pluggable moderation framework for AI output compliance
- 💬 **Community IM / AI employees** — Real-time chat with autonomous AI agents
- 📊 **Token tracking & billing** — Built-in TokenTracker with Redis persistence for usage-based pricing
- 🔌 **AIGateway / model routing** — Multi-model abstraction with fallback and provider-agnostic LLM support

Aixrea Engine is designed for teams building **AI SaaS**, **autonomous agents**, **RAG pipelines**, **AI copilots**, **content generation systems**, and **agentic workflows** that need to run reliably in production.

---

## Who is it for?

| Role | Use Case |
|---|---|
| **AI Startup founders** | Build production AI SaaS with billing, multi-tenancy, and skill marketplace |
| **ML/AI Engineers** | Orchestrate multi-agent systems with deterministic DAG + ReAct hybrid control |
| **Backend Developers** | Add AI agent capabilities to existing products via FastAPI gateway |
| **Content Platforms** | Automate content creation pipelines (text, image, audio, video) |
| **Enterprise AI teams** | Deploy internal AI copilots with guardrails, audit trails, and access control |

---

## Comparison with Other Agent Frameworks

| Feature | Aixrea Engine | LangChain Agents | CrewAI | AutoGPT | LangGraph (raw) |
|---|---|---|---|---|---|
| Multi-agent orchestration | ✅ Built-in | ⚠️ Manual | ✅ Built-in | ⚠️ Limited | ❌ Manual |
| Deterministic DAG control | ✅ First-class | ❌ ReAct only | ❌ ReAct only | ❌ ReAct only | ✅ First-class |
| Persistent memory (Redis) | ✅ Built-in | ⚠️ Manual | ⚠️ Limited | ❌ No | ❌ Manual |
| Skill marketplace / monetization | ✅ Built-in | ❌ No | ❌ No | ❌ No | ❌ No |
| Token tracking & billing | ✅ Built-in | ❌ No | ❌ No | ❌ No | ❌ No |
| Content guardrails | ✅ Built-in | ❌ No | ❌ No | ❌ No | ❌ No |
| Code execution sandbox | ✅ Built-in | ⚠️ Manual | ⚠️ Manual | ✅ Built-in | ❌ Manual |
| Production FastAPI server | ✅ Built-in | ❌ No | ❌ No | ❌ No | ❌ No |
| OpenTelemetry tracing | ✅ Built-in | ⚠️ Callback | ❌ No | ❌ No | ❌ Manual |
| Based on LangGraph | ✅ Yes | ❌ No | ❌ No | ❌ No | ✅ N/A |

> **Key difference**: Aixrea Engine combines **LangGraph's deterministic DAG** with **ReAct's flexibility** in a three-layer control model, plus production infrastructure (memory, billing, sandbox, guardrails) that raw LangGraph doesn't provide.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Lead Agent                              │
│  (Plan-and-Execute + ReAct hybrid, 15+ middleware)           │
│  memory │ summary │ todo │ loop-detection │ sub-agent-limits  │
├──────────┬──────────┬───────────┬────────────────────────────┤
│  Memory   │  Skills  │  Sandbox  │  Sub-agents                │
│  (short/  │  (tool   │  (code    │  (specialized workers)     │
│   long/    │  market) │   exec)   │                            │
│   summary) │          │           │                            │
├──────────┴──────────┴───────────┴────────────────────────────┤
│              PipelineExecutor (DAG)                           │
│     (deterministic workflows for content creation)             │
├───────────────────────────────────────────────────────────────┤
│              AIGateway (model routing)                         │
│     (multi-model abstraction, fallback, token tracking)        │
├───────────────────────────────────────────────────────────────┤
│              CreditsLedger / TokenTracker                      │
│     (usage metering, billing, rate limiting)                   │
└───────────────────────────────────────────────────────────────┘
```

### Three-Layer Control Model

| Layer | Pattern | Use Case |
|---|---|---|
| **Workflow Graph** | DAG (deterministic) | Main execution trunk, billing, checkpoint recovery |
| **Plan-and-Execute** | Task decomposition | Complex multi-step tasks, RAG pipelines |
| **ReAct** | Local exploration | Unknown environments, tool discovery, function calling |

---

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 22+ (for frontend/tooling)
- Redis (for memory/cache)
- An LLM API key (OpenAI, Anthropic, or any OpenAI-compatible endpoint)

### Installation

```bash
# Clone
git clone https://github.com/XinWoRen-Global/aixrea-engine.git
cd aixrea-engine

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
result = await agent.run("Research the top 3 AI agent frameworks in 2026 and compare them")
print(result.summary)
```

See [`examples/`](./examples) for more, including multi-agent workflows, RAG pipelines, and skill development.

---

## Core Modules

| Module | Description | Status |
|---|---|---|
| `agents.lead_agent` | Core execution engine with 15+ middleware | ✅ Stable |
| `agents.memory` | Short/long-term/summary memory for RAG | ✅ Stable |
| `agents.subagents` | Sub-agent orchestration for multi-agent systems | ✅ Stable |
| `runtime` | FastAPI server, auth, config, API gateway | ✅ Stable |
| `skills` | Skill registry, tool use, function calling framework | ✅ Stable |
| `sandbox` | Code execution sandbox (E2B / self-hosted) | ⚠️ Preview |
| `guardrails` | Content moderation / AI safety framework | ⚠️ Preview |
| `persistence` | Database persistence layer (Postgres) | ✅ Stable |
| `tracing` | OpenTelemetry distributed tracing | ✅ Stable |
| `scheduler` | Task scheduling / cron for agentic automation | ⚠️ Preview |
| `gateway` | AIGateway multi-model routing with fallback | ✅ Stable |
| `credits` | TokenTracker + CreditsLedger for usage billing | ✅ Stable |

---

## Skills System / Tool Use

Build and publish AI tools as reusable skills with structured function calling:

```python
from aixrea_engine import skill, SkillContext

@skill(name="web_search", description="Search the web for information")
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
- **Payout**: Monthly via Stripe, **$100 minimum**
- **No exclusivity**: Publish your skills anywhere
- **You retain ownership** of your skill code

Affiliate referrals follow the existing affiliate program (up to 25%, 30-day cookie).

See [COMMERCIAL.md](./COMMERCIAL.md) for details.

---

## Open Source vs Commercial

This repository is the **open-source framework** — use it to build your own AI agent applications, self-hosted, with full control over your data and infrastructure.

The **commercial platform** ([aixrea.com](https://aixrea.com) / [xinworen.com](https://xinworen.com)) is a managed SaaS built on top of this framework. It is not a "source-available" version of this repo — it is a separate product with managed hosting, operations, and platform services.

| | Open Source (this repo) | Commercial Platform |
|---|---|---|
| **What you get** | Framework & SDK, full source code | Managed SaaS platform, no DevOps needed |
| **Deployment** | Self-hosted, your infrastructure | Fully managed, global CDN, auto-scaling |
| **Agent runtime** | ✅ Included | ✅ Included (same engine) |
| **Skill SDK** | ✅ Included | ✅ Included |
| **DAG pipeline executor** | ✅ Included | ✅ Included |
| **Operations & SLA** | ❌ You operate it | ✅ 99.9% uptime SLA, 24/7 monitoring |
| **Managed services** | ❌ Build your own | ✅ Billing, user management, content delivery |
| **Support** | Community / GitHub Issues | ✅ Priority support, dedicated engineer |
| **Best for** | Builders, startups, self-hosters | Teams who want a ready-to-use platform |

> The open-source framework is the same engine that powers our commercial platform. We don't hold back core agent capabilities — we sell **managed operations and platform services**, not features.

Open-source repo: [github.com/XinWoRen-Global/aixrea-engine](https://github.com/XinWoRen-Global/aixrea-engine)

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

**Note**: This project is currently in **read-only open source** mode. We release the code for transparency and learning, but we are not accepting pull requests at this time. Please open issues for bug reports and feature requests — we read every one.

---

## Roadmap

- **v2.0** (current) — Core framework stable, 5-language docs, skill SDK
- **v2.1** — Skill marketplace Beta, creator revenue share live
- **v2.2** — More sandbox providers (E2B / self-hosted), enhanced RAG
- **v2.3** — Multi-modal native support (video/audio/image pipelines)
- **v3.0** — Full agentic automation platform with visual workflow builder

---

## License

[MIT](./LICENSE) — Copyright (c) 2026 **XinWoRen Pte. Ltd. (Singapore)** / Aixrea. All rights reserved.

---

> Built with LangGraph. Powered by the global creator community.
> [aixrea.com](https://aixrea.com) · [xinworen.com](https://xinworen.com)
> XinWoRen (新我人) — AI creation platform for global creators
>
> Keywords: AI agent framework, multi-agent orchestration, LLM apps, autonomous agents, agentic AI, LangGraph, LangChain alternative, CrewAI alternative, AutoGPT alternative, RAG, function calling, tool use, DAG workflow, production AI, AI SaaS, FastAPI, Python, open source
