"""互动影游分支矩阵批处理（P2 纵向切片第二刀 · 2026-09-04）。

职责：把互动影游专辑的「剧情分支 × 每分支片段」矩阵批量展开为
generate_segment 视频节点（DB 持久化），交由 execute_phase("video") 的
标准视频链路执行（第一刀已打通 MiniMax 显式模型路由）。

设计要点：
- **树优先 / 合成兜底**：若 generate_interactive_branch 节点携带结构化分支树
  （config.branches / output JSON），按树展开；否则按 album batch_config 的
  branchCount × segmentsPerBranch 合成骨架（后续接对话树后自动升级为树驱动）。
- **幂等**：album 已存在 generate_segment 节点时跳过展开（防重复入队）。
- **预算闸**：矩阵总量硬上限 INTERACTIVE_VIDEO_MATRIX_CAP（默认 24），
  超出截断并告警——分支预生成指数膨胀是本方案 §七 红线，闸在源头。
- **纯函数 + 编排分离**：build_branch_matrix 为纯函数可独立断言；
  expand_interactive_video_matrix 负责落库 + progress_total 校正。

节点/边 schema 与前端 /api/studio/albums/[id]/pipeline 持久化行严格对齐
（id = node_<ts>_<rand> 非 UUID、config JSONB、dependency_type="hard"）。
"""

from __future__ import annotations

import json
import logging
import os
import random
import time

from .pipeline_insforge import insert_pipeline_edges, insert_pipeline_nodes

logger = logging.getLogger("gateway.branch_matrix")

# ── 预算闸：单 album 矩阵片段硬上限（防分支×片段指数膨胀） ──
DEFAULT_MATRIX_CAP = 24


def _matrix_cap() -> int:
    raw = os.environ.get("INTERACTIVE_VIDEO_MATRIX_CAP", "").strip()
    try:
        return max(1, int(raw)) if raw else DEFAULT_MATRIX_CAP
    except ValueError:
        return DEFAULT_MATRIX_CAP


def _coerce_int(val, default: int, lo: int, hi: int) -> int:
    try:
        n = int(val)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _make_id(prefix: str) -> str:
    """与前端 makeId 同构：node_<ms>_<rand>（studio_pipeline_nodes.id 为 text）。"""
    return f"{prefix}_{int(time.time() * 1000)}_{random.randbytes(4).hex()}"


def _safe_json(val) -> dict | list | None:
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, (dict, list)) else None
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _first(obj: dict, *keys, default=None):
    for k in keys:
        v = obj.get(k)
        if v not in (None, ""):
            return v
    return default


def extract_branch_tree(branch_node: dict | None) -> list[dict] | None:
    """从 generate_interactive_branch 节点提取结构化分支树（宽容键名）。

    兼容形态：[{name/title/branchName, description/summary, segments: [str|{description}]}]
    解析不出任何分支返回 None（调用方走合成兜底）。
    """
    if not branch_node:
        return None
    cfg = branch_node.get("config") or {}
    raw = _first(cfg, "branches", "branchTree", "branch_tree", default=None)
    if raw is None:
        raw = _first(_safe_json(branch_node.get("output")) or {}, "branches", "branchTree", default=None)
    tree = _safe_json(raw)
    if not isinstance(tree, list) or not tree:
        return None
    branches: list[dict] = []
    for i, b in enumerate(tree):
        if not isinstance(b, dict):
            # 纯字符串分支 → 单分支单描述
            branches.append({"name": str(b)[:60], "description": str(b)[:300], "segments": []})
            continue
        name = str(_first(b, "name", "title", "branchName", default=f"分支{i + 1}"))[:60]
        desc = str(_first(b, "description", "summary", "plot", default=""))[:400]
        segs_raw = b.get("segments") or b.get("nodes") or []
        segs: list[str] = []
        for s in segs_raw if isinstance(segs_raw, list) else []:
            if isinstance(s, dict):
                sd = str(_first(s, "description", "summary", "text", default="")).strip()
            else:
                sd = str(s).strip()
            if sd:
                segs.append(sd[:400])
        branches.append({"name": name, "description": desc, "segments": segs})
    return branches or None


def build_branch_matrix(album: dict, nodes: list[dict]) -> dict:
    """纯函数：产出分支矩阵定义（不落库）。

    返回 {
      "source": "tree" | "synthesized",
      "video_model": str,
      "branch_count": int,
      "segments_per_branch": int,   # 合成源时的基准值；树源时按分支实际片段数
      "segments": [ {branchIndex, branchName, branchDescription,
                     segmentIndex, segmentCount, segmentDescription} ],
      "capped": bool,
      "cap": int,
    }
    """
    batch = album.get("batch_config") or {}
    cap = _matrix_cap()

    branch_node = next(
        (n for n in nodes if n.get("node_type") == "generate_interactive_branch"),
        None,
    )
    tree = extract_branch_tree(branch_node)

    segments: list[dict] = []
    source = "synthesized"
    base_spb = 3

    if tree:
        source = "tree"
        for bi, b in enumerate(tree):
            descs = b["segments"] or [""]
            for si, sd in enumerate(descs):
                segments.append(
                    {
                        "branchIndex": bi,
                        "branchName": b["name"],
                        "branchDescription": b["description"],
                        "segmentIndex": si,
                        "segmentCount": len(descs),
                        "segmentDescription": sd,
                    }
                )
    else:
        # 合成兜底：branchCount × segmentsPerBranch
        branch_count = _coerce_int(_first(batch, "branchCount", "branch_count"), 3, 1, 8)
        spb = _coerce_int(_first(batch, "segmentsPerBranch", "segments_per_branch"), base_spb, 1, 6)
        genre = str(_first(batch, "genre", default="") or "")
        base_spb = spb
        for bi in range(branch_count):
            name = f"分支{chr(ord('A') + bi % 26)}" if bi < 26 else f"分支{bi + 1}"
            for si in range(spb):
                segments.append(
                    {
                        "branchIndex": bi,
                        "branchName": name,
                        "branchDescription": f"{genre} 题材剧情分支" if genre else "剧情分支",
                        "segmentIndex": si,
                        "segmentCount": spb,
                        "segmentDescription": "",
                    }
                )

    # 预算闸：超出上限截断（保留分支序号连续性，靠前分支优先）
    capped = False
    if len(segments) > cap:
        segments = segments[:cap]
        capped = True

    # 视频模型：batch_config（表单透传）→ 分支节点 config → 互动影游默认（用户拍板 H3 Max）
    video_model = str(_first(batch, "video_model", "videoModel", default="") or "")
    if not video_model and branch_node:
        video_model = str(_first(branch_node.get("config") or {}, "video_model", "videoModel", default="") or "")
    if not video_model:
        video_model = "MiniMax-H3-Max"

    # duration 必须显式写入节点 config：estimate_node_credits 对 generate_segment 的
    # duration 缺省值是 30（短剧分镜惯例），矩阵片段不写就会按 30s 超额扣费
    # （H3 Max 8cr/s × 30 = 240cr，实际 5-15s）。batch 表单透传优先，缺省取 SSOT 下限 5s。
    duration = _first(batch, "duration", "videoDuration", "segmentDuration", default=None)
    try:
        duration = max(5, min(15, int(duration))) if duration is not None else 5
    except (TypeError, ValueError):
        duration = 5

    return {
        "source": source,
        "video_model": video_model,
        "duration": duration,
        "branch_count": len({s["branchIndex"] for s in segments}),
        "segments_per_branch": base_spb,
        "segments": segments,
        "capped": capped,
        "cap": cap,
    }


def _node_rows(album: dict, matrix: dict, branch_node_id: str | None, compose_node_id: str | None) -> tuple[list[dict], list[dict]]:
    """矩阵 → DB 行（schema 与前端 pipeline 持久化严格对齐）。"""
    batch = album.get("batch_config") or {}
    node_rows: list[dict] = []
    edge_rows: list[dict] = []
    total = len(matrix["segments"])
    for s in matrix["segments"]:
        node_id = _make_id("node")
        node_rows.append(
            {
                "id": node_id,
                "album_id": album["id"],
                "node_type": "generate_segment",
                "status": "pending",
                "input_asset_ids": [],
                "output_asset_id": None,
                "config": {
                    "branchSegment": True,
                    "branchIndex": s["branchIndex"],
                    "branchName": s["branchName"],
                    "branchDescription": s["branchDescription"],
                    "segmentIndex": s["segmentIndex"],
                    "segmentCount": s["segmentCount"],
                    "segmentDescription": s["segmentDescription"],
                    "video_model": matrix["video_model"],
                    "videoModel": matrix["video_model"],  # 双写别名：生成侧/计费侧读 camelCase
                    "duration": matrix["duration"],  # 显式时长：计费侧按此估，缺省会误落 30s
                    "aspectRatio": batch.get("aspectRatio"),
                    "resolution": batch.get("resolution"),
                    "phaseLabel": "pipeStepVideo",
                    "sub_items": {"generate_segment": 1},
                    "total_sub_items": total,
                },
                "error_message": None,
                "started_at": None,
                "completed_at": None,
            }
        )
        if branch_node_id:
            edge_rows.append(
                {
                    "id": _make_id("edge"),
                    "album_id": album["id"],
                    "source_node_id": branch_node_id,
                    "target_node_id": node_id,
                    "dependency_type": "hard",
                }
            )
        if compose_node_id:
            edge_rows.append(
                {
                    "id": _make_id("edge"),
                    "album_id": album["id"],
                    "source_node_id": node_id,
                    "target_node_id": compose_node_id,
                    "dependency_type": "hard",
                }
            )
    return node_rows, edge_rows


def find_prev_segment_node(nodes: list[dict], config: dict) -> dict | None:
    """定位同分支的上一片段已完成节点（H3 Max 尾帧→首帧链式锚点，P2 第四刀）。

    纯函数：branchIndex 相同 + segmentIndex = 当前-1 + completed + 有成片资产。
    首片段（segmentIndex=0）无上游 → None（无链，纯 t2v）。
    """
    try:
        seg = int(config.get("segmentIndex", 0))
    except (TypeError, ValueError):
        return None
    if seg <= 0:
        return None
    branch = config.get("branchIndex")
    candidates = [
        n
        for n in nodes
        if n.get("node_type") == "generate_segment"
        and n.get("status") == "completed"
        and (n.get("config") or {}).get("branchSegment")
        and (n.get("config") or {}).get("branchIndex") == branch
        and str((n.get("config") or {}).get("segmentIndex")) == str(seg - 1)
        and n.get("output_asset_id")
    ]
    return max(candidates, key=lambda n: n.get("completed_at") or "", default=None)


async def expand_interactive_video_matrix(album: dict, nodes: list[dict], edges: list[dict]) -> dict:
    """幂等展开：album 已有 generate_segment 节点 → 跳过；否则批量插入矩阵节点+边。"""
    album_id = album["id"]
    existing = [n for n in nodes if n.get("node_type") == "generate_segment"]
    if existing:
        return {
            "expanded": False,
            "reason": "video nodes already exist",
            "existing": len(existing),
        }

    matrix = build_branch_matrix(album, nodes)
    if not matrix["segments"]:
        return {"expanded": False, "reason": "empty matrix"}

    branch_node_id = next((n["id"] for n in nodes if n.get("node_type") == "generate_interactive_branch"), None)
    compose_node_id = next((n["id"] for n in nodes if n.get("node_type") == "compose_album"), None)

    node_rows, edge_rows = _node_rows(album, matrix, branch_node_id, compose_node_id)

    inserted = await insert_pipeline_nodes(node_rows)
    if not inserted:
        # 400/网络失败时 _request 返回 [] —— 明确失败，绝不静默（否则本相位无节点可跑）
        raise RuntimeError(f"branch matrix insert failed for album {album_id} ({len(node_rows)} nodes)")
    if edge_rows:
        await insert_pipeline_edges(edge_rows)

    if matrix["capped"]:
        logger.warning("Branch matrix for album %s capped at %d segments (budget gate)", album_id, matrix["cap"])

    logger.info("Branch matrix expanded for album %s: source=%s branches=%d segments=%d model=%s", album_id, matrix["source"], matrix["branch_count"], len(node_rows), matrix["video_model"])

    return {
        "expanded": True,
        "source": matrix["source"],
        "branch_count": matrix["branch_count"],
        "segments": len(node_rows),
        "video_model": matrix["video_model"],
        "capped": matrix["capped"],
        "node_ids": [r["id"] for r in node_rows],
        "new_node_rows": node_rows,  # execute_phase 直接并入本相位执行，免二次拉取
    }
