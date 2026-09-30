"""Curated open-source upstream ecosystem for Invest.

The registry is metadata and capability routing, not vendored third-party source.
Software-license compatibility and underlying market-data rights are separate gates.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Iterable

_REGISTRY_PATH = Path(__file__).with_name("upstream_registry.json")


def load_registry() -> dict:
    """Load the packaged upstream registry."""
    return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))


def list_upstreams(
    *,
    capability: str | None = None,
    stages: Iterable[str] | None = None,
    adapter_safe_only: bool = False,
) -> list[dict]:
    """Return curated upstreams filtered by capability/stage/license policy."""
    registry = load_registry()
    projects = registry["projects"]
    allowed_stages = set(stages) if stages is not None else None
    safe_licenses = set(registry["license_policy"]["permissive_adapter_allowlist"])

    result: list[dict] = []
    for project in projects:
        if capability is not None and capability not in project["capabilities"]:
            continue
        if allowed_stages is not None and project["stage"] not in allowed_stages:
            continue
        if adapter_safe_only and project["license"] not in safe_licenses:
            continue
        result.append(dict(project))
    return result


def is_import_available(project: dict) -> bool:
    """Check whether an optional Python integration is importable locally."""
    module = project.get("python_import")
    if not module:
        return False
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def capability_matrix() -> dict[str, list[str]]:
    """Map each capability to repositories that can contribute to it."""
    matrix: dict[str, list[str]] = {}
    for project in load_registry()["projects"]:
        for capability in project["capabilities"]:
            matrix.setdefault(capability, []).append(project["repo"])
    for repos in matrix.values():
        repos.sort()
    return dict(sorted(matrix.items()))


def small_capital_allocation_stack() -> dict[str, list[str]]:
    """Preferred upstream stack for the long-term '500 CNY allocation' goal.

    This is a research/integration routing plan, not an investment recommendation.
    """
    return {
        "market_data": [
            "akfamily/akshare",
            "waditu/tushare",
            "mootdx/mootdx",
            "shidenggui/easyquotation",
        ],
        "market_rules_and_calendar": [
            "gerrymanoim/exchange_calendars",
            "rsheftel/pandas_market_calendars",
            "ricequant/rqalpha",
            "fasiondog/hikyuu",
        ],
        "allocation": [
            "PyPortfolio/PyPortfolioOpt",
            "dcajasn/Riskfolio-Lib",
            "skfolio/skfolio",
            "pmorissette/bt",
        ],
        "risk_and_performance": [
            "ranaroussi/quantstats",
            "stefan-jansen/empyrical-reloaded",
            "stefan-jansen/pyfolio-reloaded",
            "pmorissette/ffn",
        ],
        "factor_and_model_research": [
            "microsoft/qlib",
            "stefan-jansen/alphalens-reloaded",
            "AI4Finance-Foundation/FinRL",
            "microsoft/RD-Agent",
        ],
        "independent_backtest": [
            "ricequant/rqalpha",
            "stefan-jansen/zipline-reloaded",
            "fasiondog/hikyuu",
            "QuantConnect/Lean",
        ],
        "news_and_sentiment_reference": [
            "AI4Finance-Foundation/FinGPT",
            "ProsusAI/finBERT",
        ],
    }


def integration_summary() -> dict:
    """Summarize registry size, stages, and adapter-safe coverage."""
    registry = load_registry()
    projects = registry["projects"]
    by_stage: dict[str, int] = {}
    for project in projects:
        by_stage[project["stage"]] = by_stage.get(project["stage"], 0) + 1
    safe_licenses = set(registry["license_policy"]["permissive_adapter_allowlist"])
    return {
        "project_count": len(projects),
        "stage_counts": dict(sorted(by_stage.items())),
        "adapter_safe_count": sum(p["license"] in safe_licenses for p in projects),
        "capability_count": len(capability_matrix()),
        "registry_as_of": registry["as_of"],
    }
