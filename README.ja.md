# Aixrea Engine — マルチエージェントオーケストレーションフレームワーク

> AI 製品を構築するための本番環境対応エージェントハーネス。
> サブエージェント、メモリ、サンドボックス、拡張可能なスキルをオーケストレーション — LangGraph ベース。

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](./backend/pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Framework: LangGraph](https://img.shields.io/badge/Framework-LangGraph-FF6B6B)](https://langchain-ai.github.io/langgraph/)

[English](../README.md) | [中文](README.zh-CN.md) | **日本語** | [Français](README.fr.md) | [Русский](README.ru.md)

---

## Aixrea Engine とは？

Aixrea Engine は、**サブエージェント**、**メモリ**、**サンドボックス**をオーケストレーションして本番 AI アプリケーションを構築するためのオープンソースの**スーパーエージェントハーネス**です。以下のための柔軟で拡張可能な基盤を提供します：

- 🤖 **マルチエージェントオーケストレーション** — Lead Agent が専門サブエージェントを調整
- 🧠 **永続メモリ** — 短期、長期、サマリーメモリ
- 🛠️ **拡張可能なスキル** — AI ツールを再利用可能なスキルとして構築
- 🔄 **DAG パイプライン** — コンテンツ作成のための決定論的ワークフロー実行
- 🔒 **コンテンツガードレール** — AI 出力のためのプラグ可能なモデレーションフレームワーク
- 💬 **コミュニティ IM** — AI 従業員とのリアルタイムチャット

信頼性が高く回復可能なエージェントワークフローのために **LangGraph** 上に構築されています。

---

## アーキテクチャ

```
┌─────────────────────────────────────────────────┐
│                   Lead Agent                      │
│  (Plan-and-Execute + ReAct ハイブリッド, 15+ ミドルウェア)│
├──────────┬──────────┬───────────┬────────────────┤
│  メモリ   │  スキル  │  サンドボックス│  サブエージェント │
│  (短期/   │  (ツール │  (コード   │  (専門ワーカー)  │
│   長期/    │  マーケット)│  実行)    │                │
│   サマリー) │          │           │                │
├──────────┴──────────┴───────────┴────────────────┤
│              PipelineExecutor (DAG)                │
│     (コンテンツ作成のための決定論的ワークフロー)      │
├────────────────────────────────────────────────────┤
│              AIGateway (モデルルーティング)          │
│     (マルチモデル抽象化, フォールバック, トラッキング)│
└────────────────────────────────────────────────────┘
```

### 3 層制御モデル

| レイヤー | パターン | ユースケース |
|---|---|---|
| **ワークフローグラフ** | DAG（決定論的） | メイン実行トランク、課金、リカバリ |
| **Plan-and-Execute** | タスク分解 | 複雑な多段階タスク |
| **ReAct** | 局所探索 | 未知の環境、ツール発見 |

---

## クイックスタート

### 前提条件

- Python 3.12+
- Node.js 22+（フロントエンド/ツール用）
- Redis（メモリ/キャッシュ用）
- LLM API キー（OpenAI、Anthropic、または互換）

### インストール

```bash
# クローン
git clone https://github.com/XinWoRen-Global/aixrea-engine.git
cd aixrea-engine

# バックエンド依存関係をインストール
cd backend
pip install -e .

# 設定
cp .env.example .env
# .env を編集して LLM API キーを入力

# 実行
uvicorn app.main:app --reload --port 8001
```

### 最小限の例

```python
from aixrea_engine import LeadAgent, SkillRegistry

# 初期化
agent = LeadAgent(
    model="gpt-4o",
    skills=SkillRegistry.default(),
    memory=True,
)

# 実行
result = await agent.run("2026 年のトップ 3 AI フレームワークを調べて")
print(result.summary)
```

詳細は [`examples/`](./examples) を参照してください。

---

## コアモジュール

| モジュール | 説明 | ステータス |
|---|---|---|
| `agents.lead_agent` | 15+ ミドルウェアを持つコア実行エンジン | ✅ 安定 |
| `agents.memory` | 短期/長期/サマリーメモリ | ✅ 安定 |
| `agents.subagents` | サブエージェントオーケストレーション | ✅ 安定 |
| `runtime` | FastAPI サーバー、認証、設定 | ✅ 安定 |
| `skills` | スキル登録と実行フレームワーク | ✅ 安定 |
| `sandbox` | コード実行サンドボックス | ⚠️ プレビュー |
| `guardrails` | コンテンツモデレーションフレームワーク | ⚠️ プレビュー |
| `persistence` | データベース永続化レイヤー | ✅ 安定 |
| `tracing` | OpenTelemetry トレーシング | ✅ 安定 |
| `scheduler` | タスクスケジューリング | ⚠️ プレビュー |

---

## スキルシステム

AI ツールを再利用可能なスキルとして構築：

```python
from aixrea_engine import skill, SkillContext

@skill(name="web_search", description="ウェブ検索")
async def web_search(ctx: SkillContext, query: str) -> str:
    # 実装
    return results

# 登録
registry = SkillRegistry()
registry.register(web_search)
```

### マーケットプレイス収益分配

ツール開発者はプラットフォーム上の**クリエイター**です。スキル収益は既存の **CreatorTier** システムに従います（ドラマ/音楽/漫画クリエイターと同じ）：

| クリエイター階層 | 開発者シェア | プラットフォーム |
|---|---|---|
| Bronze（ブロンズ） | 50% | 50% |
| Silver（シルバー） | 60% | 40% |
| Gold / Platinum（ゴールド/プラチナ） | 70% | 30% |

- **独立したコミッションシステムは不要** — 1 アカウント、1 階層、すべての収益タイプが統合
- **支払い**：月次で Stripe 経由、最低 $100
- **排他性なし**：スキルをどこにでも公開可能
- **スキルコードの所有権は開発者が保持**

アフィリエイト紹介は既存のアフィリエイトプログラムに従います（最大 25%、30 日 cookie）。

詳細は [COMMERCIAL.md](./COMMERCIAL.md) を参照してください。

---

## 商用利用

本プロジェクトは個人、研究、内部利用のために **MIT ライセンス**で提供されています。

商用利用（SaaS、企業導入、再販、または専有製品への組み込み）については、商用ライセンスのためにお問い合わせください。以下を提供しています：

- **スタートアップライセンス**：収益ベース、初期費用なし
- **エンタープライズライセンス**：インスタンス単位、SLA とサポート付き
- **OEM ライセンス**：ホワイトラベル、製品への組み込み

お問い合わせ：`contact@xinworen.com`

---

## コントリビューション

コントリビューションを歓迎します！ガイドラインは [CONTRIBUTING.md](./CONTRIBUTING.md) を参照してください。

**注意**：本プロジェクトは現在**読み取り専用オープンソース**モードです。透明性と学習のためにコードを公開していますが、現在 Pull Request は受け付けていません。バグ報告や機能リクエストは Issue を作成してください。

---

## オープンソース版 vs 商用版

| レイヤー | オープンソース版（本リポジトリ） | 商用プラットフォーム |
|---|---|---|
| エージェントフレームワーク | ✅ | ✅ |
| スキル SDK | ✅ | ✅ |
| パイプライン DAG エグゼキュータ | ✅ | ✅ |
| コンテンツガードレールフレームワーク | ✅ | ✅ |
| 課金 / クレジット台帳 | ❌ | ✅ |
| マーケットプレイス / ストア | ❌ | ✅ |
| コンテンツ配信 | ❌ | ✅ |
| 推奨エンジン | ❌ | ✅ |
| マルチドメインルーティング | ❌ | ✅ |
| 作成ツール（ドラマ/音楽/漫画） | ❌ | ✅ |

オープンソースリポジトリ：[github.com/XinWoRen-Global/aixrea-engine](https://github.com/XinWoRen-Global/aixrea-engine)

---

## ライセンス

[MIT](./LICENSE) — Copyright (c) 2026 **XinWoRen Pte. Ltd. (Singapore)** / Aixrea. All rights reserved.

---

> LangGraph で構築。グローバルクリエイターコミュニティによって駆動。
> [aixrea.com](https://aixrea.com) · [xinworen.com](https://xinworen.com)
> XinWoRen（新我人）— グローバルクリエイターのための AI 作成プラットフォーム
