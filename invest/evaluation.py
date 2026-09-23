"""Fail-closed registration checks for frozen evaluation data bindings.

This module does not fetch market data and never accepts provider credentials.
It validates the provenance and pre-observation contract required before an
authorized real dataset can be opened as a frozen holdout under protocol v1.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import math
import re
from typing import Any

PROTOCOL_ID = "invest-oos-forward-paper-v1"
BINDING_STATUS = "BOUND_UNOPENED"
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
_FORBIDDEN_KEY_PARTS = ("token", "secret", "password", "credential", "api_key", "apikey")
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


def _text(value: Any, field: str, *, limit: int = 1000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(char) < 32 for char in value):
        raise ValueError(f"{field} 必须是非空可打印文本")
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


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} 必须是带时区 ISO-8601 时间")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{field} 必须是带时区 ISO-8601 时间") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} 必须包含时区")
    return value


def _reject_sensitive_keys(value: Any, path: str = "binding") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} 的键必须是字符串")
            lowered = key.lower().replace("-", "_")
            if any(part in lowered for part in _FORBIDDEN_KEY_PARTS):
                raise ValueError(f"{path}.{key} 疑似凭据字段；binding 禁止保存凭据")
            _reject_sensitive_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_keys(child, f"{path}[{index}]")


def _ensure_json_finite(value: Any) -> None:
    def walk(item: Any) -> None:
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("binding 不能包含 NaN/Infinity")
        if isinstance(item, dict):
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
        elif item is not None and not isinstance(item, (str, int, float, bool)):
            raise ValueError("binding 只能包含 JSON 数据类型")
    walk(value)
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError("binding 必须可安全序列化为有限 JSON") from None


def _canonical_payload(binding: dict) -> bytes:
    payload = deepcopy(binding)
    payload.pop("binding_id", None)
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def validate_evaluation_binding(binding: dict) -> dict:
    """Validate and fingerprint a pre-observation protocol-v1 data binding.

    A structurally valid binding may still be ineligible to open the holdout.
    The returned ``can_open_holdout`` is false whenever required market-data
    boundaries are not independently verified or explicit blockers remain.
    This function never changes the input and never contacts a provider.
    """
    original = _mapping(binding, "binding")
    _reject_sensitive_keys(original)
    _ensure_json_finite(original)

    required = {
        "schema_version",
        "protocol_id",
        "status",
        "created_at",
        "dataset",
        "universe",
        "candidate",
        "windows",
        "cost_scenarios",
        "benchmark",
        "market_data_boundaries",
        "known_blockers",
        "holdout_first_observed_at",
    }
    _only_keys(original, "binding", required, {"binding_id"})

    if type(original["schema_version"]) is not int or original["schema_version"] != 1:
        raise ValueError("schema_version 必须严格等于 1")
    if original["protocol_id"] != PROTOCOL_ID:
        raise ValueError("protocol_id 与已冻结的评价协议 v1 不一致")
    if original["status"] != BINDING_STATUS:
        raise ValueError("新 binding 必须处于 BOUND_UNOPENED，不能冒充已观察 holdout")
    _timestamp(original["created_at"], "created_at")
    if original["holdout_first_observed_at"] is not None:
        raise ValueError("预观察 binding 的 holdout_first_observed_at 必须为 null")

    dataset = _mapping(original["dataset"], "dataset")
    _only_keys(
        dataset,
        "dataset",
        {
            "source",
            "source_kind",
            "license_status",
            "retrieved_at",
            "raw_artifact_identity",
            "raw_sha256",
            "normalized_dataset_id",
            "code_sha",
            "currency",
            "price_basis",
            "volume_unit",
            "timezone",
        },
    )
    _text(dataset["source"], "dataset.source", limit=500)
    _text(dataset["source_kind"], "dataset.source_kind", limit=100)
    if dataset["license_status"] != "authorized":
        raise ValueError("dataset.license_status 必须明确为 authorized")
    _timestamp(dataset["retrieved_at"], "dataset.retrieved_at")
    _text(dataset["raw_artifact_identity"], "dataset.raw_artifact_identity", limit=500)
    _sha256(dataset["raw_sha256"], "dataset.raw_sha256")
    _sha256(dataset["normalized_dataset_id"], "dataset.normalized_dataset_id")
    _git_sha(dataset["code_sha"], "dataset.code_sha")
    if dataset["currency"] != "CNY":
        raise ValueError("首个 Invest v1 binding 的 currency 必须为 CNY")
    _text(dataset["price_basis"], "dataset.price_basis", limit=100)
    _text(dataset["volume_unit"], "dataset.volume_unit", limit=100)
    _text(dataset["timezone"], "dataset.timezone", limit=100)

    universe = _mapping(original["universe"], "universe")
    _only_keys(universe, "universe", {"description", "formation_rule", "pit_evidence"})
    _text(universe["description"], "universe.description")
    _text(universe["formation_rule"], "universe.formation_rule")
    _text(universe["pit_evidence"], "universe.pit_evidence")

    candidate = _mapping(original["candidate"], "candidate")
    _only_keys(candidate, "candidate", {"candidate_id", "parameters_sha256", "description"})
    _text(candidate["candidate_id"], "candidate.candidate_id", limit=200)
    _sha256(candidate["parameters_sha256"], "candidate.parameters_sha256")
    _text(candidate["description"], "candidate.description")

    windows = _mapping(original["windows"], "windows")
    _only_keys(windows, "windows", {"development", "validation", "frozen_holdout"})
    parsed_windows: list[tuple[str, date, date]] = []
    for name in ("development", "validation", "frozen_holdout"):
        window = _mapping(windows[name], f"windows.{name}")
        _only_keys(window, f"windows.{name}", {"start", "end"})
        start = _date(window["start"], f"windows.{name}.start")
        end = _date(window["end"], f"windows.{name}.end")
        if start > end:
            raise ValueError(f"windows.{name} 起始日不能晚于结束日")
        parsed_windows.append((name, start, end))
    for previous, current in zip(parsed_windows, parsed_windows[1:]):
        if previous[2] >= current[1]:
            raise ValueError("development / validation / frozen_holdout 必须按时间严格前进且不重叠")

    scenarios = original["cost_scenarios"]
    if not isinstance(scenarios, list) or len(scenarios) < 3:
        raise ValueError("cost_scenarios 至少需要 3 个已命名成本情景")
    scenario_names: set[str] = set()
    for index, scenario_value in enumerate(scenarios):
        scenario = _mapping(scenario_value, f"cost_scenarios[{index}]")
        _only_keys(scenario, f"cost_scenarios[{index}]", {"name", "configuration"})
        name = _text(scenario["name"], f"cost_scenarios[{index}].name", limit=100)
        if name in scenario_names:
            raise ValueError("cost_scenarios 名称不能重复")
        scenario_names.add(name)
        configuration = _mapping(scenario["configuration"], f"cost_scenarios[{index}].configuration")
        if not configuration:
            raise ValueError("每个成本情景必须冻结非空 configuration")

    benchmark = _mapping(original["benchmark"], "benchmark")
    _only_keys(benchmark, "benchmark", {"name", "definition"})
    _text(benchmark["name"], "benchmark.name", limit=200)
    _text(benchmark["definition"], "benchmark.definition")

    boundaries = _mapping(original["market_data_boundaries"], "market_data_boundaries")
    _only_keys(boundaries, "market_data_boundaries", set(BOUNDARY_KEYS))
    automatic_blockers: list[str] = []
    for key in BOUNDARY_KEYS:
        item = _mapping(boundaries[key], f"market_data_boundaries.{key}")
        _only_keys(item, f"market_data_boundaries.{key}", {"status", "evidence"})
        if item["status"] not in BOUNDARY_STATES:
            raise ValueError(f"market_data_boundaries.{key}.status 必须是 verified/unknown/not_covered")
        _text(item["evidence"], f"market_data_boundaries.{key}.evidence")
        if item["status"] != "verified":
            automatic_blockers.append(key)

    known_blockers = original["known_blockers"]
    if not isinstance(known_blockers, list):
        raise ValueError("known_blockers 必须是列表")
    normalized_blockers: list[str] = []
    for index, blocker in enumerate(known_blockers):
        text = _text(blocker, f"known_blockers[{index}]")
        if text in normalized_blockers:
            raise ValueError("known_blockers 不能重复")
        normalized_blockers.append(text)

    binding_id = hashlib.sha256(_canonical_payload(original)).hexdigest()
    supplied_id = original.get("binding_id")
    if supplied_id is not None:
        _sha256(supplied_id, "binding_id")
        if supplied_id != binding_id:
            raise ValueError("binding_id 与 binding 内容不一致")

    return {
        "binding_id": binding_id,
        "can_open_holdout": not automatic_blockers and not normalized_blockers,
        "blocking_boundary_fields": automatic_blockers,
        "known_blockers": normalized_blockers,
    }
