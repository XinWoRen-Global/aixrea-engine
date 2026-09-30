import pytest

from app.gateway import credits_engine, external_config

# ─── deep_merge ──────────────────────────────────────────────────────


def test_deep_merge_merges_nested_dicts_and_replaces_leaves():
    base = {"vendor": {"models": ["a"], "regions": ["cn"], "limit": 3}, "keep": 1}
    override = {"vendor": {"models": ["b"], "limit": 5}, "extra": {"x": 1}}

    merged = external_config.deep_merge(base, override)

    assert merged == {
        "vendor": {"models": ["b"], "regions": ["cn"], "limit": 5},
        "keep": 1,
        "extra": {"x": 1},
    }
    # inputs untouched
    assert base["vendor"]["models"] == ["a"]
    assert override["vendor"]["limit"] == 5


# ─── merge_routing_table ─────────────────────────────────────────────


def test_merge_routing_table_parses_pairs_and_replaces_chain():
    base = {"m1": [("p1", "v1")], "m2": [("p2", "v2")]}
    override = {"m1": [["p9", "v9"], ["p8", "v8"]], "m3": [["p3", "v3"]]}

    merged = external_config.merge_routing_table(base, override)

    assert merged["m1"] == [("p9", "v9"), ("p8", "v8")]
    assert merged["m2"] == [("p2", "v2")]
    assert merged["m3"] == [("p3", "v3")]


def test_merge_routing_table_ignores_malformed_and_none():
    base = {"m1": [("p1", "v1")]}
    assert external_config.merge_routing_table(base, None) == base
    assert external_config.merge_routing_table(base, {}) == base

    merged = external_config.merge_routing_table(
        base,
        {"m1": "not-a-list", "m2": [["only-one"]], "m3": [["ok", "v"], "junk"]},
    )
    assert merged["m1"] == [("p1", "v1")]  # non-list override ignored
    assert "m2" not in merged  # zero valid hops ignored
    assert merged["m3"] == [("ok", "v")]  # valid hops kept, junk dropped


# ─── load_yaml_overrides ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_gateway_env(monkeypatch):
    for name in ("GATEWAY_PROVIDERS_FILE", "GATEWAY_ROUTING_FILE", "GATEWAY_CREDITS_FILE"):
        monkeypatch.delenv(name, raising=False)


def test_load_yaml_overrides_returns_empty_without_file(tmp_path):
    assert external_config.load_yaml_overrides("GATEWAY_PROVIDERS_FILE", "absent.yaml") == {}


def test_load_yaml_overrides_reads_env_pointed_file(tmp_path, monkeypatch):
    cfg = tmp_path / "custom.yaml"
    cfg.write_text("vendor:\n  regions: [global]\n", encoding="utf-8")
    monkeypatch.setenv("GATEWAY_PROVIDERS_FILE", str(cfg))

    assert external_config.load_yaml_overrides("GATEWAY_PROVIDERS_FILE", "ignored.yaml") == {"vendor": {"regions": ["global"]}}


def test_load_yaml_overrides_resolves_relative_path_against_config_dir(tmp_path, monkeypatch):
    import app.gateway.external_config as ec

    cfg = ec._CONFIG_DIR / "relative-test.yaml"
    cfg.write_text("key: 1\n", encoding="utf-8")
    try:
        monkeypatch.setenv("GATEWAY_PROVIDERS_FILE", "relative-test.yaml")
        assert external_config.load_yaml_overrides("GATEWAY_PROVIDERS_FILE", "other.yaml") == {"key": 1}
    finally:
        cfg.unlink(missing_ok=True)


def test_load_yaml_overrides_invalid_or_non_mapping_returns_empty(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("key: [unclosed\n", encoding="utf-8")
    assert external_config.load_yaml_overrides("GATEWAY_PROVIDERS_FILE", "absent.yaml") == {}

    scalar = tmp_path / "scalar.yaml"
    scalar.write_text("- just\n- a list\n", encoding="utf-8")
    assert external_config.load_yaml_overrides("GATEWAY_PROVIDERS_FILE", "absent.yaml") == {}


# ─── apply_credits_overrides ─────────────────────────────────────────


def _fake_credits_globals():
    return {
        "MUSIC_PRICING": {"analyze": {"credits": 1}, "generate": {"credits": 8}, "compose": {"credits": 1}},
        "SCRIPT_CHARS_PER_CREDIT": 300,
        "UNKNOWN_TABLE": {"x": 1},
        "DRAMA_PIPELINE_PRICING": {
            "text": {"credits": 5},
            "image": {"credits": 25},
            "storyboard": {"credits": 16},
            "video": {"credits": 276},
            "post": {"credits": 3},
        },
        "MUSIC_TOTAL": 10,
        "COMICS_PRICING": {
            "analyze": {"credits": 8},
            "gen_assets": {"credits": 18},
            "gen_pages": {"credits": 8},
            "compose": {"credits": 2},
        },
        "COMICS_TOTAL": 36,
        "INTERACTIVE_PRICING": {
            "analyze": {"credits": 10},
            "assets": {"credits": 12},
            "build": {"credits": 56},
            "compose": {"credits": 2},
        },
        "INTERACTIVE_TOTAL": 80,
    }


def test_apply_credits_overrides_merges_scalars_and_recomputes_totals():
    g = _fake_credits_globals()
    external_config.apply_credits_overrides(
        g,
        {
            "MUSIC_PRICING": {"generate": {"credits": 9}},
            "SCRIPT_CHARS_PER_CREDIT": 400,
            "COMICS_PRICING": {"gen_assets": {"credits": 20}},
            "INTERACTIVE_PRICING": {"build": {"credits": 60}},
        },
    )

    assert g["MUSIC_PRICING"]["generate"]["credits"] == 9
    assert g["MUSIC_PRICING"]["analyze"]["credits"] == 1  # untouched sibling
    assert g["SCRIPT_CHARS_PER_CREDIT"] == 400
    assert g["MUSIC_TOTAL"] == 11
    assert g["COMICS_TOTAL"] == 38
    assert g["INTERACTIVE_TOTAL"] == 84
    assert g["DRAMA_EPISODE_TOTAL"] == 325
    assert g["AGENT_PIPELINE_OVERHEAD"] == 49


def test_apply_credits_overrides_ignores_unknown_and_malformed():
    g = _fake_credits_globals()
    external_config.apply_credits_overrides(
        g,
        {
            "quick_video_credits": None,  # function clobber attempt
            "UNKNOWN_TABLE": {"x": 2},  # not whitelisted
            "SCRIPT_CHARS_PER_CREDIT": "not-a-number",
            "MUSIC_PRICING": "not-a-mapping",
        },
    )

    assert "quick_video_credits" not in g
    assert g["UNKNOWN_TABLE"] == {"x": 1}
    assert g["SCRIPT_CHARS_PER_CREDIT"] == 300
    assert g["MUSIC_PRICING"]["generate"]["credits"] == 8
    assert g["MUSIC_TOTAL"] == 10


def test_apply_credits_overrides_no_overrides_is_noop():
    g = _fake_credits_globals()
    snapshot = dict(g)
    external_config.apply_credits_overrides(g, {})
    assert g == snapshot


# ─── credits_engine 实际模块（无 yaml 时与内置默认一致） ───────────────


def test_credits_engine_defaults_intact_without_yaml():
    assert credits_engine.MUSIC_TOTAL == 10
    assert credits_engine.COMICS_TOTAL == 36
    assert credits_engine.INTERACTIVE_TOTAL == 80
    assert credits_engine.DRAMA_EPISODE_TOTAL == 325
    assert credits_engine.AGENT_PIPELINE_OVERHEAD == 49
    # xinworen-ai 是免费体验模型（rate=0），计 0 积分；付费模型按 MODEL_RESOLUTION_MULTIPLIER 计
    assert credits_engine.quick_video_credits("xinworen-ai", 10) == 0
    assert credits_engine.quick_video_credits("seedance-2-mini", 10) == 60
    assert credits_engine.script_credits(500) == 2
    assert credits_engine.estimate_node_credits("generate_music_track", {}) == 8
