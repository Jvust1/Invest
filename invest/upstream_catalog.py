"""Queryable catalog for the 50-project high-star integration batch.

The catalog routes optional components without importing or vendoring them by default.
Each entry carries an upstream license boundary and an import availability probe.
"""
from __future__ import annotations

from .upstreams import is_import_available, load_registry


def list_catalog(*, capability: str | None = None, safe_only: bool = False) -> list[dict]:
    """Return the 2026-09-30 catalog batch, optionally filtered by capability."""
    projects = [dict(project) for project in load_registry()["projects"] if project.get("batch") == "20260930-high-star-50"]
    if capability is not None:
        projects = [p for p in projects if capability in p.get("capabilities", [])]
    if safe_only:
        allow = set(load_registry()["license_policy"]["permissive_adapter_allowlist"])
        projects = [p for p in projects if p.get("license") in allow]
    return projects


def available_catalog(*, capability: str | None = None, safe_only: bool = False) -> list[dict]:
    """Return catalog entries whose declared optional Python module is installed."""
    return [project for project in list_catalog(capability=capability, safe_only=safe_only) if is_import_available(project)]


def catalog_summary() -> dict:
    """Summarize the batch without triggering third-party imports."""
    projects = list_catalog()
    return {
        "batch": "20260930-high-star-50",
        "count": len(projects),
        "license_counts": {name: sum(p["license"] == name for p in projects) for name in sorted({p["license"] for p in projects})},
        "capability_count": len({capability for p in projects for capability in p["capabilities"]}),
        "archived_count": 0,
    }
