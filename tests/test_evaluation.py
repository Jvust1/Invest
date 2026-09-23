import copy
import unittest

from invest import evaluation


H64 = "a" * 64
G40 = "b" * 40


def valid_binding():
    return {
        "schema_version": 1,
        "protocol_id": "invest-oos-forward-paper-v1",
        "status": "BOUND_UNOPENED",
        "created_at": "2026-09-23T08:00:00+08:00",
        "dataset": {
            "source": "authorized real-data snapshot",
            "source_kind": "provider-export",
            "license_status": "authorized",
            "retrieved_at": "2026-09-23T07:30:00+08:00",
            "raw_artifact_identity": "local-authorized-snapshot-001",
            "raw_sha256": H64,
            "normalized_dataset_id": "c" * 64,
            "code_sha": G40,
            "currency": "CNY",
            "price_basis": "raw",
            "volume_unit": "shares",
            "timezone": "Asia/Shanghai",
        },
        "universe": {
            "description": "沪深主板候选样本",
            "formation_rule": "按冻结日可见证券身份形成",
            "pit_evidence": "证券池形成记录在首次观察前冻结",
        },
        "candidate": {
            "candidate_id": "ma-v1-fixed",
            "parameters_sha256": "d" * 64,
            "description": "冻结候选参数，不在 holdout 结果后调参",
        },
        "windows": {
            "development": {"start": "2020-01-01", "end": "2022-12-31"},
            "validation": {"start": "2023-01-01", "end": "2023-12-31"},
            "frozen_holdout": {"start": "2024-01-01", "end": "2024-12-31"},
        },
        "historical_market_environments": [
            {
                "name": "2020 recovery",
                "start": "2020-04-01",
                "end": "2020-12-31",
                "evidence": "regime label and dates frozen before holdout observation",
            },
            {
                "name": "2022 stress",
                "start": "2022-01-01",
                "end": "2022-10-31",
                "evidence": "regime label and dates frozen before holdout observation",
            },
            {
                "name": "2023 range-bound",
                "start": "2023-01-01",
                "end": "2023-12-31",
                "evidence": "regime label and dates frozen before holdout observation",
            },
        ],
        "cost_scenarios": [
            {"name": "low", "configuration": {"commission_bps": 1}},
            {"name": "base", "configuration": {"commission_bps": 3}},
            {"name": "high", "configuration": {"commission_bps": 5}},
        ],
        "benchmark": {
            "name": "simple-buy-hold",
            "definition": "同一证券池、同一数据身份和评价区间的简单基准",
        },
        "market_data_boundaries": {
            key: {"status": "verified", "evidence": "source-specific evidence frozen before holdout"}
            for key in evaluation.BOUNDARY_KEYS
        },
        "known_blockers": [],
        "holdout_first_observed_at": None,
    }


class EvaluationBindingTests(unittest.TestCase):
    def test_valid_binding_is_deterministic_and_openable(self):
        binding = valid_binding()
        before = copy.deepcopy(binding)
        first = evaluation.validate_evaluation_binding(binding)
        second = evaluation.validate_evaluation_binding(binding)
        self.assertEqual(binding, before)
        self.assertEqual(first, second)
        self.assertRegex(first["binding_id"], r"^[0-9a-f]{64}$")
        self.assertTrue(first["can_open_holdout"])
        with_id = copy.deepcopy(binding)
        with_id["binding_id"] = first["binding_id"]
        self.assertEqual(evaluation.validate_evaluation_binding(with_id), first)

    def test_unknown_market_boundary_is_explicit_blocker_not_fake_failure(self):
        binding = valid_binding()
        binding["market_data_boundaries"]["corporate_actions"] = {
            "status": "unknown",
            "evidence": "provider path does not prove complete corporate-action coverage",
        }
        result = evaluation.validate_evaluation_binding(binding)
        self.assertFalse(result["can_open_holdout"])
        self.assertEqual(result["blocking_boundary_fields"], ["corporate_actions"])

    def test_known_blocker_prevents_opening(self):
        binding = valid_binding()
        binding["known_blockers"] = ["risk-warning history not yet independently reconciled"]
        result = evaluation.validate_evaluation_binding(binding)
        self.assertFalse(result["can_open_holdout"])
        self.assertEqual(result["known_blockers"], binding["known_blockers"])

    def test_holdout_observation_cannot_be_smuggled_into_preobservation_binding(self):
        binding = valid_binding()
        binding["holdout_first_observed_at"] = "2026-09-23T08:01:00+08:00"
        with self.assertRaisesRegex(ValueError, "必须为 null"):
            evaluation.validate_evaluation_binding(binding)
        binding = valid_binding()
        binding["status"] = "OBSERVED"
        with self.assertRaisesRegex(ValueError, "BOUND_UNOPENED"):
            evaluation.validate_evaluation_binding(binding)

    def test_windows_must_be_strictly_forward_and_nonoverlapping(self):
        binding = valid_binding()
        binding["windows"]["validation"]["start"] = "2022-12-31"
        with self.assertRaisesRegex(ValueError, "不重叠"):
            evaluation.validate_evaluation_binding(binding)
        binding = valid_binding()
        binding["windows"]["development"] = {"start": "2022-01-02", "end": "2022-01-01"}
        with self.assertRaisesRegex(ValueError, "起始日"):
            evaluation.validate_evaluation_binding(binding)

    def test_three_historical_market_environments_are_required_and_bounded(self):
        binding = valid_binding()
        binding["historical_market_environments"] = binding["historical_market_environments"][:2]
        with self.assertRaisesRegex(ValueError, "至少需要 3"):
            evaluation.validate_evaluation_binding(binding)

        binding = valid_binding()
        binding["historical_market_environments"][2]["name"] = "2022 stress"
        with self.assertRaisesRegex(ValueError, "名称不能重复"):
            evaluation.validate_evaluation_binding(binding)

        binding = valid_binding()
        binding["historical_market_environments"][2]["start"] = "2019-01-01"
        with self.assertRaisesRegex(ValueError, "总时间边界"):
            evaluation.validate_evaluation_binding(binding)

        binding = valid_binding()
        binding["historical_market_environments"][2]["start"] = "2023-12-31"
        binding["historical_market_environments"][2]["end"] = "2023-01-01"
        with self.assertRaisesRegex(ValueError, "起始日"):
            evaluation.validate_evaluation_binding(binding)

        binding = valid_binding()
        binding["historical_market_environments"][2]["start"] = "2022-01-01"
        binding["historical_market_environments"][2]["end"] = "2022-10-31"
        with self.assertRaisesRegex(ValueError, "日期区间不能完全重复"):
            evaluation.validate_evaluation_binding(binding)

    def test_at_least_three_unique_cost_scenarios_with_configuration(self):
        binding = valid_binding()
        binding["cost_scenarios"] = binding["cost_scenarios"][:2]
        with self.assertRaisesRegex(ValueError, "至少需要 3"):
            evaluation.validate_evaluation_binding(binding)
        binding = valid_binding()
        binding["cost_scenarios"][2]["name"] = "base"
        with self.assertRaisesRegex(ValueError, "不能重复"):
            evaluation.validate_evaluation_binding(binding)
        binding = valid_binding()
        binding["cost_scenarios"][0]["configuration"] = {}
        with self.assertRaisesRegex(ValueError, "非空"):
            evaluation.validate_evaluation_binding(binding)

    def test_identity_and_code_hashes_are_strict(self):
        for field, value in (
            ("raw_sha256", "A" * 64),
            ("normalized_dataset_id", "x"),
            ("code_sha", "c" * 39),
        ):
            binding = valid_binding()
            binding["dataset"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                evaluation.validate_evaluation_binding(binding)

    def test_license_must_be_explicitly_authorized(self):
        binding = valid_binding()
        binding["dataset"]["license_status"] = "unknown"
        with self.assertRaisesRegex(ValueError, "authorized"):
            evaluation.validate_evaluation_binding(binding)

    def test_credentials_and_secret_like_keys_are_rejected_recursively(self):
        for container, key in (
            ("dataset", "token"),
            ("dataset", "api_key"),
            ("candidate", "secret_note"),
        ):
            binding = valid_binding()
            binding[container][key] = "must-not-be-stored"
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "凭据"):
                evaluation.validate_evaluation_binding(binding)

    def test_unknown_fields_are_rejected(self):
        binding = valid_binding()
        binding["result"] = {"return": 99}
        with self.assertRaisesRegex(ValueError, "未支持字段"):
            evaluation.validate_evaluation_binding(binding)

    def test_binding_id_detects_mutation(self):
        binding = valid_binding()
        result = evaluation.validate_evaluation_binding(binding)
        binding["binding_id"] = result["binding_id"]
        binding["candidate"]["description"] = "mutated after freeze"
        with self.assertRaisesRegex(ValueError, "binding_id"):
            evaluation.validate_evaluation_binding(binding)

    def test_nonfinite_configuration_is_rejected(self):
        binding = valid_binding()
        binding["cost_scenarios"][0]["configuration"]["slippage"] = float("nan")
        with self.assertRaisesRegex(ValueError, "NaN/Infinity"):
            evaluation.validate_evaluation_binding(binding)


if __name__ == "__main__":
    unittest.main()
