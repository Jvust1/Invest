"""Fail-closed continuity gate between provider evidence and evaluation binding.

This module is offline only. It revalidates both governance objects and requires
their provenance and market-data boundary claims to match before holdout
opening can be considered.
"""
from __future__ import annotations

from .evaluation import BOUNDARY_KEYS, validate_evaluation_binding
from .provider_validation import validate_provider_validation_evidence


def validate_opening_pair(binding: dict, provider_evidence: dict) -> dict:
    """Validate exact provider-evidence continuity for one BOUND_UNOPENED binding."""
    provider = validate_provider_validation_evidence(provider_evidence)
    bound = validate_evaluation_binding(binding)

    reference = binding["provider_evidence"]
    identity = provider_evidence["dataset_identity"]
    checks = (
        ("evidence_id", provider["evidence_id"], reference["evidence_id"]),
        (
            "license_evidence_sha256",
            provider["license_evidence_sha256"],
            reference["license_evidence_sha256"],
        ),
        ("raw_sha256", identity["raw_sha256"], reference["raw_sha256"]),
        (
            "normalized_dataset_id",
            identity["normalized_dataset_id"],
            reference["normalized_dataset_id"],
        ),
        ("code_sha", provider_evidence["code_sha"], reference["code_sha"]),
    )
    for name, actual, expected in checks:
        if actual != expected:
            raise ValueError(f"provider evidence {name} 与 binding 引用不一致")

    for key in BOUNDARY_KEYS:
        provider_boundary = provider_evidence["market_data_boundaries"][key]
        binding_boundary = binding["market_data_boundaries"][key]
        if provider_boundary["status"] != binding_boundary["status"]:
            raise ValueError(
                f"market_data_boundaries.{key}.status 与 provider evidence 不一致"
            )
        if provider_boundary.get("evidence_sha256") != binding_boundary.get(
            "evidence_sha256"
        ):
            raise ValueError(
                f"market_data_boundaries.{key}.evidence_sha256 与 provider evidence 不一致"
            )

    can_open = bool(
        provider["can_support_holdout_opening"] and bound["can_open_holdout"]
    )
    return {
        "provider_evidence_id": provider["evidence_id"],
        "binding_id": bound["binding_id"],
        "provider_side_ready": provider["can_support_holdout_opening"],
        "binding_side_ready": bound["can_open_holdout"],
        "provider_pair_verified": True,
        "can_open_holdout": can_open,
        "blocking_boundary_fields": bound["blocking_boundary_fields"],
        "known_blockers": bound["known_blockers"],
    }
