"""P 级零成本测试：drama / comics / music / novel 四域共享管线 TEST_MODE 回归。

用户要求（2026-09-04）：对短剧、音乐、漫画、小说智能体做「不扣费、不真实调用」测试。
本文件全程离线：
  - 不触网（不连 InsForge / R2 / 任何 AI provider）；
  - 不真实扣费（ledger 用内存 fake，TEST_MODE 分支断言 hold/commit/release 零调用）；
  - 覆盖四域共享的相位映射、TEST_MODE 零扣费语义、P2 四刀纯函数回归。

被测对象（app/gateway/pipeline_executor.py + 纯函数模块）：
  1. _is_test_mode：env 矩阵 + config 兜底；
  2. PipelineExecutor._run_node_with_ledger：TEST_MODE=1 完全零扣费；
     正常模式 hold→commit / hold→release 契约；
  3. _get_phase_categories：五域 phase→category 映射（drama/comic/music/novel/interactive）；
  4. branch_matrix：矩阵展开、预算闸、duration 显式写入（修 6× 超额扣费回归）；
  5. consistency_check：评分解析 + env 阈值（fail-open 语义）；
  6. video_providers：MiniMax 模型解析 + v2 payload 首尾帧（P2 第四刀）。
"""

import types

import pytest

import app.gateway.branch_matrix as bm
import app.gateway.consistency_check as cc
import app.gateway.credits_engine as ce
import app.gateway.pipeline_executor as pe
import app.gateway.video_providers as vp

# ── fakes ────────────────────────────────────────────────────────────────


class FakeLedger:
    """内存 ledger：只记录调用，绝不真扣。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def hold(self, hold_id: str, **kwargs):
        self.calls.append(("hold", hold_id))
        return {"hold_id": hold_id}

    async def commit(self, hold_id: str, **kwargs):
        self.calls.append(("commit", hold_id))

    async def release(self, hold_id: str, **kwargs):
        self.calls.append(("release", hold_id))


def _mock_executor(ledger):
    """_run_node_with_ledger 只用 self.ledger / self._node_trace，其余全 mock。"""

    async def _noop_trace(*args, **kwargs):
        return None

    return types.SimpleNamespace(ledger=ledger, _node_trace=_noop_trace)


_VIDEO_NODE = {
    "id": "node-video-1",
    "node_type": "generate_segment",
    "status": "pending",
    "config": {"videoModel": "MiniMax-H3-Max", "duration": 5, "resolution": "480P"},
}

_ALBUM = {"id": "album-test-1", "album_type": "interactive"}


# ── 1. _is_test_mode：env 矩阵 + config 兜底 ────────────────────────────


@pytest.mark.parametrize("raw", ["1", "true", "yes", "on", "TRUE", "Yes"])
def test_test_mode_env_truthy(monkeypatch, raw):
    monkeypatch.setenv("TEST_MODE", raw)
    assert pe._is_test_mode() is True


@pytest.mark.parametrize("raw", ["0", "false", "no", "off"])
def test_test_mode_env_falsy(monkeypatch, raw):
    monkeypatch.setenv("TEST_MODE", raw)
    assert pe._is_test_mode() is False


def test_test_mode_unset_falls_back_to_seed_config(monkeypatch):
    # env 未设时读 drama-executor seed config 的 routing.test.enabled（当前=false）
    monkeypatch.delenv("TEST_MODE", raising=False)
    assert pe._is_test_mode() is False


# ── 2. 零扣费语义（四域共享执行入口） ────────────────────────────────────


@pytest.mark.asyncio
async def test_test_mode_zero_billing_skips_ledger_entirely(monkeypatch):
    """TEST_MODE=1：hold/commit/release 零调用，节点照常执行，返回预估成本。"""
    monkeypatch.setenv("TEST_MODE", "1")
    ledger = FakeLedger()
    executed: list[str] = []

    async def handler(node, album, user_id):
        executed.append(node["id"])

    cost = await pe.PipelineExecutor._run_node_with_ledger(_mock_executor(ledger), _VIDEO_NODE, _ALBUM, "user-1", handler)

    assert executed == ["node-video-1"], "TEST_MODE 下节点必须照常执行"
    assert ledger.calls == [], "TEST_MODE 零扣费：ledger 不得有任何调用"
    expected = ce.estimate_node_credits("generate_segment", _VIDEO_NODE["config"])
    assert cost == expected and cost > 0, "返回值=预估成本（供展示），但余额分文未动"


@pytest.mark.asyncio
async def test_normal_mode_hold_commit_contract(monkeypatch):
    """正常模式：hold → handler 成功 → commit。"""
    monkeypatch.delenv("TEST_MODE", raising=False)
    ledger = FakeLedger()

    async def handler(node, album, user_id):
        return None

    await pe.PipelineExecutor._run_node_with_ledger(_mock_executor(ledger), _VIDEO_NODE, _ALBUM, "user-1", handler)

    assert [c[0] for c in ledger.calls] == ["hold", "commit"]
    assert ledger.calls[0][1] == f"album:{_ALBUM['id']}:node:{_VIDEO_NODE['id']}"


@pytest.mark.asyncio
async def test_normal_mode_failure_releases_hold(monkeypatch):
    """正常模式：handler 失败 → release（幂等退回），异常原样上抛。"""
    monkeypatch.delenv("TEST_MODE", raising=False)
    ledger = FakeLedger()

    async def failing_handler(node, album, user_id):
        raise RuntimeError("provider boom")

    with pytest.raises(RuntimeError, match="provider boom"):
        await pe.PipelineExecutor._run_node_with_ledger(_mock_executor(ledger), _VIDEO_NODE, _ALBUM, "user-1", failing_handler)

    assert [c[0] for c in ledger.calls] == ["hold", "release"], "失败必须全额退回"


@pytest.mark.asyncio
async def test_terminal_node_idempotent_skip(monkeypatch):
    """幂等重入保护：终态节点直接跳过，不执行 handler 也不计费。"""
    monkeypatch.delenv("TEST_MODE", raising=False)
    ledger = FakeLedger()
    node = {**_VIDEO_NODE, "status": "completed"}

    async def handler(node, album, user_id):
        raise AssertionError("终态节点不得重复执行")

    cost = await pe.PipelineExecutor._run_node_with_ledger(_mock_executor(ledger), node, _ALBUM, "user-1", handler)
    assert cost == 0 and ledger.calls == []


# ── 3. 四域相位映射 ─────────────────────────────────────────────────────


def test_phase_categories_drama():
    assert pe.PipelineExecutor._get_phase_categories("analyze", "drama") == ["text"]
    assert pe.PipelineExecutor._get_phase_categories("assets", "drama") == ["image"]
    assert pe.PipelineExecutor._get_phase_categories("video", "drama") == ["video"]


def test_phase_categories_comic():
    assert pe.PipelineExecutor._get_phase_categories("pages", "comic") == ["image"]
    assert pe.PipelineExecutor._get_phase_categories("assets", "comic") == ["image"]


def test_phase_categories_music():
    # 音乐 assets → audio（与 drama 同名不同类，映射正确性的关键回归点）
    assert pe.PipelineExecutor._get_phase_categories("assets", "music") == ["audio"]


def test_phase_categories_novel():
    assert pe.PipelineExecutor._get_phase_categories("draft", "novel") == ["text"]
    assert pe.PipelineExecutor._get_phase_categories("polish", "novel") == ["text"]


def test_phase_categories_interactive():
    assert pe.PipelineExecutor._get_phase_categories("build", "interactive") == ["interactive"]
    assert pe.PipelineExecutor._get_phase_categories("video", "interactive") == ["video"]


def test_phase_categories_compose_is_terminal_and_unknown_falls_back():
    assert pe.PipelineExecutor._get_phase_categories("compose", "drama") == []
    # 未知 album_type 兜底走 DRAMA_PHASES 单值
    assert pe.PipelineExecutor._get_phase_categories("video", "unknown-type") == ["video"]
    assert pe.PipelineExecutor._get_phase_categories("nonexistent", "drama") == []


# ── 4. 分支矩阵（interactive）：预算闸 + duration 显式写入 ──────────────


def _album_for_matrix(batch: dict) -> dict:
    return {"id": "album-matrix-1", "album_type": "interactive", "batch_config": batch}


def test_matrix_synthesized_expansion_and_duration_passthrough():
    album = _album_for_matrix({"branchCount": 2, "segmentsPerBranch": 3, "video_model": "MiniMax-H3-Max", "duration": 8})
    m = bm.build_branch_matrix(album, [])
    assert m["source"] == "synthesized"
    assert len(m["segments"]) == 6 and m["branch_count"] == 2
    assert m["video_model"] == "MiniMax-H3-Max"
    assert m["duration"] == 8, "batch 表单 duration 必须透传"


@pytest.mark.parametrize("raw,expect", [(40, 15), (1, 5), (None, 5), ("abc", 5)])
def test_matrix_duration_clamped(raw, expect):
    batch = {"branchCount": 1, "segmentsPerBranch": 1}
    if raw is not None:
        batch["duration"] = raw
    assert bm.build_branch_matrix(_album_for_matrix(batch), [])["duration"] == expect


def test_matrix_default_model_is_h3_max():
    m = bm.build_branch_matrix(_album_for_matrix({}), [])
    assert m["video_model"] == "MiniMax-H3-Max", "互动影游默认模型（用户拍板）"


def test_matrix_budget_gate_cap(monkeypatch):
    monkeypatch.setenv("INTERACTIVE_VIDEO_MATRIX_CAP", "5")
    album = _album_for_matrix({"branchCount": 4, "segmentsPerBranch": 3})  # 12 > 5
    m = bm.build_branch_matrix(album, [])
    assert m["capped"] is True and m["cap"] == 5 and len(m["segments"]) == 5
    # 靠前分支优先：segmentsPerBranch=3 → 截断保留 b0 全部 3 片段 + b1 前 2 片段
    assert [s["branchIndex"] for s in m["segments"]] == [0, 0, 0, 1, 1]


def test_matrix_duration_guards_overbilling_regression():
    """回归：矩阵节点 duration 缺省会按短剧惯例 30s 超额扣费（实际 5-15s）。"""
    est = ce.estimate_node_credits("generate_segment", {"videoModel": "MiniMax-H3-Max", "duration": 30, "resolution": "480P"})
    est_bounded = ce.estimate_node_credits("generate_segment", {"videoModel": "MiniMax-H3-Max", "duration": 15, "resolution": "480P"})
    assert est == 2 * est_bounded, "30s vs 15s 线性：缺省 30s 即 2× 超额（此前为 6×）"
    # 矩阵产出的 duration 永远 ≤15 → 扣费有界
    m = bm.build_branch_matrix(_album_for_matrix({}), [])
    assert m["duration"] <= 15


# ── 5. find_prev_segment_node（尾帧→首帧链式的上游定位） ────────────────


def test_find_prev_segment_same_branch():
    nodes = [
        {"id": "a1", "node_type": "generate_segment", "status": "completed", "output_asset_id": "asset-1", "config": {"branchSegment": True, "branchIndex": 0, "segmentIndex": 0}},
        {"id": "a2", "node_type": "generate_segment", "status": "completed", "output_asset_id": "asset-2", "config": {"branchSegment": True, "branchIndex": 0, "segmentIndex": 1}},
    ]
    prev = bm.find_prev_segment_node(nodes, {"branchIndex": 0, "segmentIndex": 1})
    assert prev is not None and prev["id"] == "a1"


def test_find_prev_segment_requires_completed_asset():
    """未完成 / 无成片 / 无 branchSegment 标记的节点不能作链式锚点。"""
    base = {"branchSegment": True, "branchIndex": 0, "segmentIndex": 0}
    nodes = [
        {"id": "a1", "node_type": "generate_segment", "status": "running", "output_asset_id": "asset-1", "config": base},
        {"id": "a2", "node_type": "generate_segment", "status": "completed", "output_asset_id": None, "config": base},
        {"id": "a3", "node_type": "generate_segment", "status": "completed", "output_asset_id": "asset-3", "config": {**base, "branchSegment": False}},
    ]
    assert bm.find_prev_segment_node(nodes, {"branchIndex": 0, "segmentIndex": 1}) is None


def test_find_prev_segment_cross_branch_is_none():
    nodes = [
        {"id": "b1", "node_type": "generate_segment", "config": {"branchIndex": 1, "segmentIndex": 0}},
    ]
    assert bm.find_prev_segment_node(nodes, {"branchIndex": 0, "segmentIndex": 1}) is None


# ── 6. 一致性校验：解析 + 阈值（fail-open 语义的边界） ──────────────────


@pytest.mark.parametrize(
    "text,expect",
    [
        ("SCORE: 8", 8.0),
        ("score: 7.5", 7.5),
        ("6/10", 6.0),
        ("得分：6 分", 6.0),
        ("评分 9.2", 9.2),
        ("垃圾输出", None),
        ("", None),
        ("SCORE: 11", None),
        ("SCORE: -1", None),
    ],
)
def test_parse_score(text, expect):
    assert cc.parse_score(text) == expect


def test_consistency_threshold_and_regen_env(monkeypatch):
    monkeypatch.delenv("INTERACTIVE_CONSISTENCY_THRESHOLD", raising=False)
    monkeypatch.delenv("INTERACTIVE_CONSISTENCY_MAX_RETRY", raising=False)
    assert cc.threshold() == 6.0 and cc.max_regen() == 1
    monkeypatch.setenv("INTERACTIVE_CONSISTENCY_THRESHOLD", "7")
    monkeypatch.setenv("INTERACTIVE_CONSISTENCY_MAX_RETRY", "9")
    assert cc.threshold() == 7.0 and cc.max_regen() == 3, "max_regen 上限钳制 3"


# ── 7. MiniMax 模型解析 + v2 payload 首尾帧（P2 第四刀） ────────────────


@pytest.mark.parametrize(
    "raw,expect",
    [
        ("MiniMax-H3-Max", "h3-max"),
        ("minimax_h3_max", "h3-max"),
        ("MiniMax-H3", "h3-base"),
        ("seedance-2-mini", None),
        ("wan3.0-video", None),
        (None, None),
    ],
)
def test_resolve_minimax_model(raw, expect):
    assert vp.resolve_minimax_model(raw) == expect


def test_v2_payload_first_last_frame_chain():
    payload = vp.build_minimax_v2_payload("片段 prompt", {"duration": 8, "resolution": "480P"}, first_frame_url="https://r2/prev-last.jpg")
    roles = [c.get("role") for c in payload["content"]]
    assert roles[0] == "text" or payload["content"][0]["type"] == "text", "text 项必须在且非空"
    assert payload["content"][0]["text"] == "片段 prompt"
    assert "first_frame" in roles, "链式注入 first_frame"
    assert "last_frame" not in roles
    frame = next(c for c in payload["content"] if c.get("role") == "first_frame")
    assert frame["image_url"] == ["https://r2/prev-last.jpg"]
    assert payload["duration"] == 8 and payload["resolution"] == "480P"
    assert payload["aigc_watermark"] is True, "中国 AIGC 标识合规默认挂标"


def test_v2_payload_duration_clamp_per_variant():
    assert vp.build_minimax_v2_payload("t", {"duration": 3}, variant="h3-max")["duration"] == 5
    assert vp.build_minimax_v2_payload("t", {"duration": 3}, variant="h3-base")["duration"] == 4
    assert vp.build_minimax_v2_payload("t", {"duration": 99}, variant="h3-max")["duration"] == 15
