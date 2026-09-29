"""Auditable combinatorial purged cross-validation planning for research only.

Upstream API target:
- skfolio v1.4.9
- commit ba8417e7dcda0c79536d93a712a4b19733db0046
- BSD-3-Clause

This module creates development/model-selection folds only. It does not open
Invest's frozen holdout, does not claim forward performance, and never submits
orders.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
from importlib.metadata import version


def _positive_int(value, name: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} 必须是至少 {minimum} 的整数")
    return value


def _dates(values) -> list[str]:
    if not isinstance(values, list) or len(values) < 6:
        raise ValueError("development_dates 至少需要 6 个严格递增观测日")
    result = []
    previous = ""
    for value in values:
        if not isinstance(value, str):
            raise ValueError("development_dates 必须为 YYYY-MM-DD 字符串")
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("development_dates 包含无效日期") from exc
        if parsed.isoformat() != value or value <= previous:
            raise ValueError("development_dates 必须严格递增且使用 YYYY-MM-DD")
        result.append(value)
        previous = value
    return result


def _index_sha(indices: list[int]) -> str:
    canonical = json.dumps(indices, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _load_skfolio_cpcv():
    try:
        from skfolio.model_selection import CombinatorialPurgedCV
    except ImportError as exc:
        raise RuntimeError("缺少可选依赖 skfolio；请安装 optimization-skfolio 额外依赖") from exc
    return CombinatorialPurgedCV, version("skfolio")


def combinatorial_purged_cv_plan(
    development_dates: list[str],
    *,
    n_folds: int = 5,
    n_test_folds: int = 2,
    purged_size: int = 1,
    embargo_size: int = 1,
) -> dict:
    """Build an auditable skfolio CPCV plan without evaluating any strategy.

    The caller must pass development/model-selection dates only. Frozen
    holdout observations must never be included in this input.
    """
    dates = _dates(development_dates)
    n_folds = _positive_int(n_folds, "n_folds", 3)
    n_test_folds = _positive_int(n_test_folds, "n_test_folds", 2)
    if n_test_folds >= n_folds:
        raise ValueError("n_test_folds 必须小于 n_folds")
    purged_size = _positive_int(purged_size, "purged_size", 0)
    embargo_size = _positive_int(embargo_size, "embargo_size", 0)
    if len(dates) < n_folds:
        raise ValueError("观测数不能少于 n_folds")

    CombinatorialPurgedCV, package_version = _load_skfolio_cpcv()
    try:
        cv = CombinatorialPurgedCV(
            n_folds=n_folds,
            n_test_folds=n_test_folds,
            purged_size=purged_size,
            embargo_size=embargo_size,
        )
        raw_splits = list(cv.split([[0.0]] * len(dates)))
    except Exception as exc:
        raise ValueError("skfolio CPCV 无法生成分割计划") from exc

    splits = []
    for split_number, (train_index, test_sets) in enumerate(raw_splits):
        train = [int(index) for index in train_index]
        tests = [[int(index) for index in test_set] for test_set in test_sets]
        test = sorted(index for test_set in tests for index in test_set)
        if len(test) != len(set(test)):
            raise ValueError("CPCV 同一 split 的 test indices 出现重复")
        if set(train) & set(test):
            raise ValueError("CPCV train/test 出现重叠")
        if any(index < 0 or index >= len(dates) for index in train + test):
            raise ValueError("CPCV 返回越界 index")
        splits.append(
            {
                "split": split_number,
                "train_indices": train,
                "test_indices": test,
                "test_blocks": tests,
                "train_sha256": _index_sha(train),
                "test_sha256": _index_sha(test),
                "train_count": len(train),
                "test_count": len(test),
                "train_start": dates[train[0]] if train else None,
                "train_end": dates[train[-1]] if train else None,
                "test_start": dates[test[0]] if test else None,
                "test_end": dates[test[-1]] if test else None,
            }
        )

    plan_identity = {
        "development_start": dates[0],
        "development_end": dates[-1],
        "n_observations": len(dates),
        "n_folds": n_folds,
        "n_test_folds": n_test_folds,
        "purged_size": purged_size,
        "embargo_size": embargo_size,
        "split_hashes": [
            [split["train_sha256"], split["test_sha256"]] for split in splits
        ],
    }
    plan_sha = hashlib.sha256(
        json.dumps(plan_identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    return {
        "schema": "invest-skfolio-cpcv-plan-v1",
        "status": "DEVELOPMENT_MODEL_SELECTION_ONLY",
        "backend": "skfolio.CombinatorialPurgedCV",
        "backend_version": package_version,
        "development_start": dates[0],
        "development_end": dates[-1],
        "n_observations": len(dates),
        "config": {
            "n_folds": n_folds,
            "n_test_folds": n_test_folds,
            "purged_size": purged_size,
            "embargo_size": embargo_size,
        },
        "n_splits": len(splits),
        "plan_sha256": plan_sha,
        "splits": splits,
        "limitations": [
            "只能用于 development/model-selection；不得把 frozen holdout 日期传入此函数。",
            "CombinatorialPurgedCV 可在某些测试块之后使用训练观测，因此不能冒充严格 forward historical simulation。",
            "该计划只降低时序泄漏/过拟合风险，不证明策略有效、可交易或样本外盈利。",
        ],
    }
