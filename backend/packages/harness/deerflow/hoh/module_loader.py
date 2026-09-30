"""Module yaml loader.

A new AI module (film agent, virtual human, translator, ...) joins HoH
by dropping a yaml file under ``hoh/modules/``. No code change needed.

Schema example::

    name: film_agent
    display_name: 影视智能体
    developer_kind: lead_agent
    entry: deerflow.agents:make_lead_agent
    tools_allowlist: [film_script, film_render]
    qa_blackbox:
      - name: duration_check
        rule: "60 <= artifact.duration <= 180"
    evidence_ttl_days: 30
    cost_budget_per_loop_usd: 0.50
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .types import HoHModuleSpec

DEFAULT_MODULES_DIR = Path(__file__).parent / "modules"


def load_module(path: Path) -> HoHModuleSpec:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return HoHModuleSpec(
        name=raw["name"],
        display_name=raw.get("display_name", raw["name"]),
        developer_kind=raw.get("developer_kind", "lead_agent"),
        entry=raw.get("entry", ""),
        tools_allowlist=list(raw.get("tools_allowlist", [])),
        qa_blackbox=list(raw.get("qa_blackbox", [])),
        qa_whitebox=list(raw.get("qa_whitebox", [])),
        evidence_ttl_days=int(raw.get("evidence_ttl_days", 30)),
        cost_budget_per_loop_usd=float(raw.get("cost_budget_per_loop_usd", 0.50)),
        enabled=bool(raw.get("enabled", True)),
    )


def list_modules(directory: Path = DEFAULT_MODULES_DIR) -> dict[str, HoHModuleSpec]:
    """Return all enabled modules keyed by name."""
    out: dict[str, HoHModuleSpec] = {}
    if not directory.exists():
        return out
    for p in sorted(directory.glob("*.yaml")):
        spec = load_module(p)
        if spec.enabled:
            out[spec.name] = spec
    return out
