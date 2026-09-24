"""Offline fail-closed checks for sanitized real-provider validation evidence.

This module never contacts a provider and never accepts credentials. It only
validates a record produced after an authorized local provider attempt, before
that record can support the separate frozen evaluation-binding gate.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import math
import re
from typing import Any

from .data import is_mainboard_symbol

EVIDENCE_STATUS = "PROVIDER_VALIDATION_EVIDENCE"
BOUNDARY_KEYS = (
    "calendar",
    "suspension",
    "corporate_actions",
    "price_limits",
    "risk_warning_history",
    "survivorship_bias",
    "pit_features",
)
BOUNDARY_STATES = {"verified", "unknown", "not_covered"}
INTERFACE_STATES = {"success", "failed"}
_FORBIDDEN_KEY_PARTS = ("token", "secret", "password", "api_key", "apikey", "cookie")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")


def _mapping(value: Any, field: str) -> dict:
    if type(value) is not dict:
        raise ValueError(f"{field} 必须是对象")
    return value


def _only_keys(value: dict, field: str, required: set[str], optional: set[str] | None = None) -> None:
    optional = optional or set()
    missing = required - value.keys()
    extra = value.keys() - required - optional
    if missing:
        raise ValueError(f"{field} 缺少字段：" + ", ".join(sorted(missing)))
    if extra:
        raise ValueError(f"{field} 包含未支持字段：" + ", ".join(sorted(extra)))


def _text(value: Any, field: str, limit: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{field} 必须是非空文本")
    if any(ord(ch) < 32 for ch in value):
        raise ValueError(f"{field} 不能包含控制字符")
    return value.strip()


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} 必须是小写 64 位 SHA-256")
    return value


def _git_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or _GIT_SHA.fullmatch(value) is None:
        raise ValueError(f"{field} 必须是小写 40 位 Git commit SHA")
    return value


def _date(value: Any, field: str) -> date:
    if not isinstance(value, str) or _DAY.fullmatch(value) is None:
        raise ValueError(f"{field} 必须是 YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} 日期不存在") from None


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} 必须是带时区 ISO-8601 时间")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{field} 必须是带时区 ISO-8601 时间") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} 必须包含时区")
    return parsed


def _reject_sensitive_keys(value: Any, path: str = "evidence") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} 的键必须是字符串")
            normalized = key.lower().replace("-", "_")
            if normalized == "credentials_saved":
                if child is not False:
                    raise ValueError("credentials_saved 必须严格为 false")
                continue
            if any(part in normalized for part in _FORBIDDEN_KEY_PARTS):
                raise ValueError(f"{path}.{key} 疑似凭据字段；脱敏证据禁止保存")
            _reject_sensitive_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_keys(child, f"{path}[{index}]")


def _ensure_json_finite(value: Any) -> None:
    def walk(item: Any) -> None:
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("evidence 不能包含 NaN/Infinity")
        if isinstance(item, dict):
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
        elif item is not None and not isinstance(item, (str, int, float, bool)):
            raise ValueError("evidence 只能包含 JSON 数据类型")
    walk(value)
    json.dumps(value, ensure_ascii=False, allow_nan=False)


def _canonical_payload(evidence: dict) -> bytes:
    payload = deepcopy(evidence)
    payload.pop("evidence_id", None)
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def validate_provider_validation_evidence(evidence: dict) -> dict:
    """Validate and fingerprint one sanitized provider-validation record.

    A structurally valid record can describe a failed real attempt. Provider-side
    readiness is true only with real data, all interfaces successful, all seven
    boundaries verified, no blocker, and the frozen holdout still unobserved.
    The separate ``invest.evaluation`` binding gate must still pass afterwards.
    """
    original = _mapping(evidence, "evidence")
    _reject_sensitive_keys(original)
    _ensure_json_finite(original)

    required = {
        "schema_version", "status", "executed_at", "code_sha", "provider", "sample",
        "interfaces", "dataset_identity", "units", "market_data_boundaries",
        "known_blockers", "provider_call_performed", "real_data_used",
        "credentials_saved", "holdout_observed",
    }
    _only_keys(original, "evidence", required, {"evidence_id"})
    if type(original["schema_version"]) is not int or original["schema_version"] != 1:
        raise ValueError("schema_version 必须严格等于 1")
    if original["status"] != EVIDENCE_STATUS:
        raise ValueError(f"status 必须严格等于 {EVIDENCE_STATUS}")
    executed_at = _timestamp(original["executed_at"], "executed_at")
    _git_sha(original["code_sha"], "code_sha")
    if original["provider_call_performed"] is not True:
        raise ValueError("真实供应商验证记录必须明确 provider_call_performed=true")
    if type(original["real_data_used"]) is not bool:
        raise ValueError("real_data_used 必须是布尔值")
    if original["credentials_saved"] is not False:
        raise ValueError("credentials_saved 必须严格为 false")
    if original["holdout_observed"] is not False:
        raise ValueError("供应商验证阶段不得观察 frozen holdout")

    provider = _mapping(original["provider"], "provider")
    _only_keys(provider, "provider", {"name", "source_kind", "license_status", "evidence_summary"})
    _text(provider["name"], "provider.name", 200)
    _text(provider["source_kind"], "provider.source_kind", 100)
    if provider["license_status"] != "authorized":
        raise ValueError("provider.license_status 必须明确为 authorized")
    _text(provider["evidence_summary"], "provider.evidence_summary")

    sample = _mapping(original["sample"], "sample")
    _only_keys(sample, "sample", {"security_code", "start_date", "end_date", "purpose"})
    security_code = _text(sample["security_code"], "sample.security_code", 100)
    if not is_mainboard_symbol(security_code):
        raise ValueError("sample.security_code 必须是当前支持的沪深主板代码格式")
    start = _date(sample["start_date"], "sample.start_date")
    end = _date(sample["end_date"], "sample.end_date")
    if start > end:
        raise ValueError("sample.start_date 不能晚于 sample.end_date")
    if (end - start).days > 365:
        raise ValueError("首轮最小验证样本不得超过 366 个自然日")
    if end > executed_at.date():
        raise ValueError("sample.end_date 不能晚于 executed_at 所在日期")
    _text(sample["purpose"], "sample.purpose")

    interfaces = original["interfaces"]
    if not isinstance(interfaces, list) or not interfaces:
        raise ValueError("interfaces 至少需要一项真实接口尝试记录")
    names: set[str] = set()
    interfaces_all_success = True
    for index, item in enumerate(interfaces):
        field = f"interfaces[{index}]"
        interface = _mapping(item, field)
        _only_keys(interface, field, {"name", "status", "fields", "row_count", "evidence"})
        name = _text(interface["name"], f"{field}.name", 100)
        if name in names:
            raise ValueError("interfaces.name 不能重复")
        names.add(name)
        status = interface["status"]
        if status not in INTERFACE_STATES:
            raise ValueError(f"{field}.status 只能是 success / failed")
        interfaces_all_success = interfaces_all_success and status == "success"
        fields = interface["fields"]
        if not isinstance(fields, list) or any(not isinstance(x, str) or not x.strip() for x in fields):
            raise ValueError(f"{field}.fields 必须是字符串数组")
        normalized_fields = [x.strip() for x in fields]
        if len(normalized_fields) != len(set(normalized_fields)):
            raise ValueError(f"{field}.fields 不能重复")
        if type(interface["row_count"]) is not int or interface["row_count"] < 0:
            raise ValueError(f"{field}.row_count 必须是非负整数")
        if status == "success" and not normalized_fields:
            raise ValueError(f"{field}.status=success 时 fields 不能为空")
        if status == "success" and interface["row_count"] == 0:
            raise ValueError(f"{field}.status=success 时 row_count 必须大于 0")
        _text(interface["evidence"], f"{field}.evidence")

    identity = _mapping(original["dataset_identity"], "dataset_identity")
    _only_keys(identity, "dataset_identity", {"raw_artifact_identity", "raw_sha256", "normalized_dataset_id"})
    _text(identity["raw_artifact_identity"], "dataset_identity.raw_artifact_identity", 500)
    _sha256(identity["raw_sha256"], "dataset_identity.raw_sha256")
    _sha256(identity["normalized_dataset_id"], "dataset_identity.normalized_dataset_id")

    units = _mapping(original["units"], "units")
    _only_keys(units, "units", {"currency", "price_unit", "volume_input_unit", "volume_output_unit", "timezone", "conversion_notes"})
    if units["currency"] != "CNY":
        raise ValueError("Invest v1 真实数据验证 currency 必须为 CNY")
    for key in ("price_unit", "volume_input_unit", "volume_output_unit", "timezone", "conversion_notes"):
        _text(units[key], f"units.{key}", 500)

    boundaries = _mapping(original["market_data_boundaries"], "market_data_boundaries")
    _only_keys(boundaries, "market_data_boundaries", set(BOUNDARY_KEYS))
    boundary_states: dict[str, str] = {}
    all_boundaries_verified = True
    for name in BOUNDARY_KEYS:
        boundary = _mapping(boundaries[name], f"market_data_boundaries.{name}")
        _only_keys(boundary, f"market_data_boundaries.{name}", {"status", "evidence"})
        state = boundary["status"]
        if state not in BOUNDARY_STATES:
            raise ValueError(f"market_data_boundaries.{name}.status 非法")
        boundary_states[name] = state
        all_boundaries_verified = all_boundaries_verified and state == "verified"
        _text(boundary["evidence"], f"market_data_boundaries.{name}.evidence")

    blockers = original["known_blockers"]
    if not isinstance(blockers, list):
        raise ValueError("known_blockers 必须是数组")
    normalized_blockers = [_text(x, f"known_blockers[{i}]", 1000) for i, x in enumerate(blockers)]
    if len(normalized_blockers) != len(set(normalized_blockers)):
        raise ValueError("known_blockers 不能重复")

    computed_id = hashlib.sha256(_canonical_payload(original)).hexdigest()
    supplied_id = original.get("evidence_id")
    if supplied_id is not None and _sha256(supplied_id, "evidence_id") != computed_id:
        raise ValueError("evidence_id 与规范化证据内容不一致")

    can_support = (
        original["real_data_used"] is True
        and interfaces_all_success
        and all_boundaries_verified
        and not normalized_blockers
    )
    return {
        "evidence_id": computed_id,
        "all_boundaries_verified": all_boundaries_verified,
        "boundary_states": boundary_states,
        "interfaces_all_success": interfaces_all_success,
        "known_blockers": tuple(normalized_blockers),
        "can_support_holdout_opening": can_support,
        "note": "provider evidence alone is never sufficient; BOUND_UNOPENED evaluation binding must also pass",
    }
