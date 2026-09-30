"""Gateway credits_engine 计费修复回归测试。

覆盖 2026-08-29 审计修复的两个计费 bug：
1. _estimate_drama_album 中 generate_storyboard 落入 text.node_types 分支，
   被按剧本单价（300字符=1cr）重复计费，而非分镜单价（50字符=1cr）；
2. estimate_node_credits 用 startswith("music_"/"comics_"/"interactive_") 匹配，
   与实际节点名（generate_music_track / generate_comic_page /
   generate_interactive_branch）不匹配，全部落入 5cr 兜底。
"""

import app.gateway.credits_engine as ce

# ── estimate_node_credits：频道节点按子串映射 ──────────────────────────


def test_music_node_maps_to_generate_phase():
    # generate_music_track 含 "generate" → 音乐生成 8cr（修复前落 5cr 兜底）
    assert ce.estimate_node_credits("generate_music_track", {}) == ce.MUSIC_PRICING["generate"]["credits"]


def test_comic_node_uses_comics_fallback():
    # generate_comic_page 不含任何 comics phase key → comics 分支兜底 9cr（修复前 5cr）
    assert ce.estimate_node_credits("generate_comic_page", {}) == 9


def test_interactive_node_uses_interactive_fallback():
    assert ce.estimate_node_credits("generate_interactive_branch", {}) == 20


def test_storyboard_billed_at_storyboard_rate():
    # 500 字符：分镜 500/50=10cr（修复前误按剧本 500/300=2cr）
    assert ce.estimate_node_credits("generate_storyboard", {"script_length": 500}) == 10


def test_script_nodes_still_billed_at_script_rate():
    assert ce.estimate_node_credits("generate_script", {"script_length": 500}) == 2
    assert ce.estimate_node_credits("analyze_script", {"script_length": 300}) == 1


def test_video_node_billed_per_second():
    assert ce.estimate_node_credits("generate_segment", {"resolution": "720p", "duration": 10}) == 60


# ── _estimate_drama_album：storyboard 不再双重计费 ─────────────────────


def test_drama_album_storyboard_not_double_priced():
    nodes = [
        {"id": "n1", "node_type": "generate_script", "config": {"script_length": 300}},
        {"id": "n2", "node_type": "generate_storyboard", "config": {"script_length": 500}},
    ]
    est = ce._estimate_drama_album(nodes, {"resolution": "720p"})
    by_type = {b["node_type"]: b["credits"] for b in est["breakdown"]}
    assert by_type["text"] == 1  # 剧本 300/300
    assert by_type["storyboard"] == 10  # 分镜 500/50（修复前 text=2 且 storyboard 分支不可达）
    assert est["total"] == 11


def test_drama_album_full_breakdown_total():
    nodes = [
        {"id": "s", "node_type": "select_style", "config": {}},
        {"id": "c", "node_type": "generate_character", "config": {}},
        {"id": "v", "node_type": "generate_segment", "config": {"duration": 10, "resolution": "420p"}},
    ]
    est = ce._estimate_drama_album(nodes, {"resolution": "420p"})
    # 2026-09-04 计费口径对齐（与 Quick 单步视频同表）：视频按模型+分辨率差异化，
    # 缺省 seedance-2-mini 420p = 3cr/s × 10s = 30（旧统一定价 5cr/s=50 已废弃）
    # text(最小1) + image(1) + video(30)
    assert est["total"] == 32
