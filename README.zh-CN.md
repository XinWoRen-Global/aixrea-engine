# Aixrea Engine — 多智能体编排框架

> 用于构建 AI 产品的生产级智能体运行框架。
> 编排子智能体、记忆、沙箱和可扩展技能 — 基于 LangGraph 构建。

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](./backend/pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Framework: LangGraph](https://img.shields.io/badge/Framework-LangGraph-FF6B6B)](https://langchain-ai.github.io/langgraph/)

[English](../README.md) | **中文** | [日本語](README.ja.md) | [Français](README.fr.md) | [Русский](README.ru.md)

---

## Aixrea Engine 是什么？

Aixrea Engine 是一个开源的**超级智能体运行框架**，通过编排**子智能体**、**记忆**和**沙箱**来构建生产级 AI 应用。它为以下场景提供灵活、可扩展的基础：

- 🤖 **多智能体编排** — Lead Agent 协调专业子智能体
- 🧠 **持久化记忆** — 短期、长期和摘要记忆
- 🛠️ **可扩展技能** — 将 AI 工具构建为可复用的技能
- 🔄 **DAG 流水线** — 用于内容创作的确定性工作流执行
- 🔒 **内容护栏** — 可插拔的 AI 输出审核框架
- 💬 **社区即时通讯** — 与 AI 员工实时聊天

基于 **LangGraph** 构建，实现可靠、可恢复的智能体工作流。

---

## 架构

```
┌─────────────────────────────────────────────────┐
│                   Lead Agent                      │
│  (Plan-and-Execute + ReAct 混合, 15+ 中间件)      │
├──────────┬──────────┬───────────┬────────────────┤
│  记忆     │  技能    │  沙箱      │  子智能体       │
│  (短期/   │  (工具   │  (代码     │  (专业工作者)   │
│   长期/    │  市场)   │   执行)    │                │
│   摘要)    │          │           │                │
├──────────┴──────────┴───────────┴────────────────┤
│              PipelineExecutor (DAG)                │
│     (用于内容创作的确定性工作流)                     │
├────────────────────────────────────────────────────┤
│              AIGateway (模型路由)                   │
│     (多模型抽象, 故障转移, 用量追踪)                 │
└────────────────────────────────────────────────────┘
```

### 三层控制模型

| 层级 | 模式 | 适用场景 |
|---|---|---|
| **工作流图** | DAG（确定性） | 主执行链路、计费、恢复 |
| **Plan-and-Execute** | 任务分解 | 复杂多步骤任务 |
| **ReAct** | 局部探索 | 未知环境、工具发现 |

---

## 快速开始

### 前置要求

- Python 3.12+
- Node.js 22+（用于前端/工具链）
- Redis（用于记忆/缓存）
- LLM API 密钥（OpenAI、Anthropic 或兼容接口）

### 安装

```bash
# 克隆
git clone https://github.com/XinWoRen-Global/aixrea-engine.git
cd aixrea-engine

# 安装后端依赖
cd backend
pip install -e .

# 配置
cp .env.example .env
# 编辑 .env 填入你的 LLM API 密钥

# 运行
uvicorn app.main:app --reload --port 8001
```

### 最小示例

```python
from aixrea_engine import LeadAgent, SkillRegistry

# 初始化
agent = LeadAgent(
    model="gpt-4o",
    skills=SkillRegistry.default(),
    memory=True,
)

# 运行
result = await agent.run("研究 2026 年排名前三的 AI 框架")
print(result.summary)
```

更多示例见 [`examples/`](./examples)。

---

## 核心模块

| 模块 | 说明 | 状态 |
|---|---|---|
| `agents.lead_agent` | 核心执行引擎，含 15+ 中间件 | ✅ 稳定 |
| `agents.memory` | 短期/长期/摘要记忆 | ✅ 稳定 |
| `agents.subagents` | 子智能体编排 | ✅ 稳定 |
| `runtime` | FastAPI 服务、认证、配置 | ✅ 稳定 |
| `skills` | 技能注册与执行框架 | ✅ 稳定 |
| `sandbox` | 代码执行沙箱 | ⚠️ 预览 |
| `guardrails` | 内容审核框架 | ⚠️ 预览 |
| `persistence` | 数据库持久层 | ✅ 稳定 |
| `tracing` | OpenTelemetry 链路追踪 | ✅ 稳定 |
| `scheduler` | 任务调度 | ⚠️ 预览 |

---

## 技能系统

将 AI 工具构建为可复用的技能：

```python
from aixrea_engine import skill, SkillContext

@skill(name="web_search", description="搜索网页")
async def web_search(ctx: SkillContext, query: str) -> str:
    # 你的实现
    return results

# 注册
registry = SkillRegistry()
registry.register(web_search)
```

### 市场分成

工具开发者是平台上的**创作者**。技能收入遵循现有的 **CreatorTier** 体系（与短剧/音乐/漫画创作者相同）：

| 创作者等级 | 开发者分成 | 平台 |
|---|---|---|
| Bronze（青铜） | 50% | 50% |
| Silver（白银） | 60% | 40% |
| Gold / Platinum（金/铂金） | 70% | 30% |

- **无需独立佣金系统** — 一个账户、一个等级，所有收入类型统一
- **结算**：每月通过 Stripe 发放，最低 $100
- **无排他性**：你的技能可以发布到任何地方
- **你保留技能代码的所有权**

推广推荐遵循现有 affiliate 计划（最高 25%，30 天 cookie）。

详见 [COMMERCIAL.md](./COMMERCIAL.md)。

---

## 商业使用

本项目采用 **MIT 协议**，可用于个人、研究和内部用途。

商业使用（SaaS、企业部署、转售或嵌入专有产品）请联系我们获取商业许可。我们提供：

- **初创许可**：按收入分成，无前期费用
- **企业许可**：按实例计费，含 SLA 和技术支持
- **OEM 许可**：白标，嵌入你的产品

联系邮箱：`contact@xinworen.com`

---

## 贡献

欢迎贡献！请参阅 [CONTRIBUTING.md](./CONTRIBUTING.md) 了解指南。

**注意**：本项目目前处于**只读开源**模式。我们发布代码用于透明度和学习，但目前不接受 Pull Request。请通过 Issue 提交 Bug 报告和功能请求。

---

## 开源版本 vs 商业版本

本仓库是**开源框架**——用于构建你自己的 AI 智能体应用，自托管，完全掌控你的数据和基础设施。

**商业平台**（[aixrea.com](https://aixrea.com) / [xinworen.com](https://xinworen.com)）是基于此框架构建的托管 SaaS 服务。它不是本仓库的"源码可见版"——而是一个独立产品，提供托管运维、运营和平台服务。

| | 开源版本（本仓库） | 商业平台 |
|---|---|---|
| **你获得什么** | 框架与 SDK，完整源代码 | 托管 SaaS 平台，无需运维 |
| **部署方式** | 自托管，你的基础设施 | 全托管，全球 CDN，自动扩缩 |
| **智能体运行时** | ✅ 包含 | ✅ 包含（同一引擎） |
| **技能 SDK** | ✅ 包含 | ✅ 包含 |
| **流水线 DAG 执行器** | ✅ 包含 | ✅ 包含 |
| **运维与 SLA** | ❌ 自行运维 | ✅ 99.9% 可用性 SLA，7×24 监控 |
| **托管服务** | ❌ 自行构建 | ✅ 计费、用户管理、内容分发 |
| **技术支持** | 社区 / GitHub Issues | ✅ 优先支持，专属工程师 |
| **适合** | 开发者、初创公司、自托管用户 | 需要开箱即用平台的团队 |

> 开源框架与商业平台使用同一套引擎。我们不保留核心智能体能力——我们卖的是**托管运维与平台服务**，不是功能。

开源仓库：[github.com/XinWoRen-Global/aixrea-engine](https://github.com/XinWoRen-Global/aixrea-engine)

---

## 许可证

[MIT](./LICENSE) — Copyright (c) 2026 **XinWoRen Pte. Ltd. (Singapore)** / Aixrea. 保留所有权利。

---

> 基于 LangGraph 构建。由全球创作者社区驱动。
> [aixrea.com](https://aixrea.com) · [xinworen.com](https://xinworen.com)
> XinWoRen（新我人）— 面向全球创作者的 AI 创作平台
