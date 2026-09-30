"""Operator-tunable gateway config loaded from yaml, layered over in-code defaults.

Priority: env-pointed yaml file > ``backend/config/<filename>`` > in-code defaults.
Yaml content is deep-merged over in-code defaults, so operators patch only the
keys they want to change (one vendor, one model's route chain, one price) and
everything else keeps the in-code value. A missing or unparsable file is not an
error — behavior is identical to no externalization at all.
"""

from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge ``override`` onto ``base`` (dicts merge, leaves replace)."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_yaml_overrides(env_var: str, filename: str) -> dict:
    """Load the yaml override mapping for one config domain.

    Resolution order: ``$env_var`` (absolute path, or relative to the config
    dir) first, then ``backend/config/<filename>``. Returns {} when nothing is
    configured, the file is absent, or it fails to parse — callers then keep
    their in-code defaults untouched.
    """
    env_path = os.environ.get(env_var, "").strip()
    if env_path:
        candidate = Path(env_path)
        if not candidate.is_absolute():
            candidate = _CONFIG_DIR / candidate
    else:
        candidate = _CONFIG_DIR / filename

    if not candidate.is_file():
        if env_path:
            logger.warning("Gateway config %s (%s) not found at %s; using in-code defaults", filename, env_var, candidate)
        return {}

    try:
        with open(candidate, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception:
        logger.exception("Failed to parse gateway config %s; using in-code defaults", candidate)
        return {}

    if not isinstance(data, dict):
        logger.warning("Gateway config %s must be a yaml mapping; using in-code defaults", candidate)
        return {}

    logger.info("Loaded gateway config overrides from %s", candidate)
    return data


def merge_routing_table(
    base: dict[str, list[tuple[str, str]]],
    override: Any,
) -> dict[str, list[tuple[str, str]]]:
    """Merge yaml route overrides into a MODEL_ROUTING table.

    Yaml form is ``model: [[provider, vendor_model], ...]``; a listed model
    replaces its whole failover chain (route chains are ordered, so partial
    merging is meaningless). Malformed hops are dropped with a warning.
    """
    merged = dict(base)
    if not isinstance(override, dict):
        if override:
            logger.warning("Routing override must be a mapping of model -> chain; ignored")
        return merged

    for model, chain in override.items():
        if not isinstance(chain, list):
            logger.warning("Routing override for %s must be a list; ignored", model)
            continue
        parsed: list[tuple[str, str]] = []
        for hop in chain:
            if isinstance(hop, (list, tuple)) and len(hop) == 2:
                parsed.append((str(hop[0]), str(hop[1])))
            else:
                logger.warning("Routing override for %s has malformed hop %r; hop dropped", model, hop)
        if parsed:
            merged[str(model)] = parsed
        else:
            logger.warning("Routing override for %s produced no valid hops; ignored", model)
    return merged


def apply_credits_overrides(module_dict: dict[str, Any], overrides: dict) -> None:
    """Apply pricing overrides onto credits_engine module globals.

    Only whitelisted tunable names are accepted, so an operator yaml can never
    clobber functions or unrelated module state. Dict values deep-merge onto
    the current table; scalar values replace. Derived totals
    (DRAMA_EPISODE_TOTAL / AGENT_PIPELINE_OVERHEAD / MUSIC_TOTAL / COMICS_TOTAL
    / INTERACTIVE_TOTAL) are recomputed afterwards so they always agree with
    the effective pricing tables.
    """
    if not overrides:
        return

    table_names = (
        "VIDEO_MODEL_TIERS",
        "RESOLUTION_MAP",
        "ASPECT_RATIO_MAP",
        "DURATION_OPTIONS",
        "DRAMA_PIPELINE_PRICING",
        "MUSIC_PRICING",
        "COMICS_PRICING",
        "INTERACTIVE_PRICING",
        "MODEL_REFERENCE_LIMITS",
        "MODEL_ID_MAP",
        "DRAMA_VIDEO_RATE_PER_SEC",
        "QUICK_MODEL_RATE_PER_SEC",
    )
    scalar_names = (
        "SCRIPT_CHARS_PER_CREDIT",
        "STORYBOARD_CHARS_PER_CREDIT",
        "IMAGE_COST",
    )

    for name in table_names:
        value = overrides.get(name)
        if value is None:
            continue
        current = module_dict.get(name)
        if isinstance(value, dict) and isinstance(current, dict):
            module_dict[name] = deep_merge(current, value)
        elif isinstance(value, dict):
            module_dict[name] = copy.deepcopy(value)
        else:
            logger.warning("Credits override %s must be a mapping; ignored", name)

    for name in scalar_names:
        value = overrides.get(name)
        if value is None:
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            module_dict[name] = value
        else:
            logger.warning("Credits override %s must be a number; ignored", name)

    drama = module_dict.get("DRAMA_PIPELINE_PRICING")
    if isinstance(drama, dict) and all(k in drama for k in ("video",)):
        episode_total = sum(part["credits"] for part in drama.values())
        module_dict["DRAMA_EPISODE_TOTAL"] = episode_total
        module_dict["AGENT_PIPELINE_OVERHEAD"] = episode_total - drama["video"]["credits"]
    for name, table in (
        ("MUSIC_TOTAL", "MUSIC_PRICING"),
        ("COMICS_TOTAL", "COMICS_PRICING"),
        ("INTERACTIVE_TOTAL", "INTERACTIVE_PRICING"),
    ):
        pricing = module_dict.get(table)
        if isinstance(pricing, dict):
            module_dict[name] = sum(part["credits"] for part in pricing.values())
