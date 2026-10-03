import json
from pathlib import Path

from invest.upstreams import (
    capability_matrix,
    integration_summary,
    list_upstreams,
    load_registry,
    small_capital_allocation_stack,
)


def test_registry_is_large_and_unique():
    registry = load_registry()
    projects = registry["projects"]
    assert len(projects) >= 30
    repos = [p["repo"] for p in projects]
    assert len(repos) == len(set(repos))


def test_registry_has_required_fields_and_stages():
    registry = load_registry()
    valid_stages = set(registry["stages"])
    for project in registry["projects"]:
        assert project["repo"]
        assert project["capabilities"]
        assert project["stage"] in valid_stages
        assert project["license"]
        assert project["target"]


def test_adapter_safe_filter_excludes_unreviewed_and_copyleft():
    safe = list_upstreams(adapter_safe_only=True)
    licenses = {p["license"] for p in safe}
    assert "GPL-3.0" not in licenses
    assert "AGPL-3.0" not in licenses
    assert "NOASSERTION" not in licenses
    assert "MIT" in licenses
    assert "Apache-2.0" in licenses


def test_small_capital_stack_covers_core_pipeline():
    stack = small_capital_allocation_stack()
    assert {
        "market_data",
        "market_rules_and_calendar",
        "allocation",
        "risk_and_performance",
        "factor_and_model_research",
        "independent_backtest",
        "news_and_sentiment_reference",
    } <= set(stack)
    assert "akfamily/akshare" in stack["market_data"]
    assert "PyPortfolio/PyPortfolioOpt" in stack["allocation"]
    assert "microsoft/qlib" in stack["factor_and_model_research"]
    assert "ricequant/rqalpha" in stack["independent_backtest"]


def test_capability_matrix_contains_allocation_and_china_data():
    matrix = capability_matrix()
    assert "portfolio_optimization" in matrix
    assert "china_market_data" in matrix
    assert len(matrix["portfolio_optimization"]) >= 3
    assert len(matrix["china_market_data"]) >= 3


def test_summary_matches_registry():
    registry = load_registry()
    summary = integration_summary()
    assert summary["project_count"] == len(registry["projects"])
    assert sum(summary["stage_counts"].values()) == summary["project_count"]
    assert summary["capability_count"] >= 15


def test_registry_file_is_packaged_source_metadata():
    path = Path(__file__).resolve().parents[1] / "invest" / "upstream_registry.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["project"] == "Jvust1/Invest"
    assert data["license_policy"]["data_rights_separate_from_software_license"] is True
