import copy
import unittest

from invest.provider_validation import validate_provider_validation_evidence


SHA256_A = "a" * 64
SHA256_B = "b" * 64
GIT_SHA = "1" * 40


def valid_evidence():
    boundaries = {
        name: {"status": "verified", "evidence": f"verified {name} with PIT source"}
        for name in (
            "calendar",
            "suspension",
            "corporate_actions",
            "price_limits",
            "risk_warning_history",
            "survivorship_bias",
            "pit_features",
        )
    }
    return {
        "schema_version": 1,
        "status": "PROVIDER_VALIDATION_EVIDENCE",
        "executed_at": "2026-09-23T12:00:00+08:00",
        "code_sha": GIT_SHA,
        "provider": {
            "name": "authorized-provider",
            "source_kind": "market-data-api",
            "license_status": "authorized",
            "evidence_summary": "local authorized session; credentials excluded",
        },
        "sample": {
            "security_code": "600000.SH",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "purpose": "minimum boundary-validation sample",
        },
        "interfaces": [
            {
                "name": "daily",
                "status": "success",
                "fields": ["ts_code", "trade_date", "open", "high", "low", "close", "vol"],
                "row_count": 240,
                "evidence": "rows matched request",
            },
            {
                "name": "adj_factor",
                "status": "success",
                "fields": ["ts_code", "trade_date", "adj_factor"],
                "row_count": 240,
                "evidence": "adjustment factors matched request",
            },
            {
                "name": "stk_limit",
                "status": "success",
                "fields": ["ts_code", "trade_date", "up_limit", "down_limit"],
                "row_count": 240,
                "evidence": "daily price limits matched request",
            },
            {
                "name": "trade_cal",
                "status": "success",
                "fields": ["exchange", "cal_date", "is_open"],
                "row_count": 365,
                "evidence": "calendar covers every natural day",
            },
        ],
        "dataset_identity": {
            "raw_artifact_identity": "local-only:provider-export-001",
            "raw_sha256": SHA256_A,
            "normalized_dataset_id": SHA256_B,
        },
        "units": {
            "currency": "CNY",
            "price_unit": "CNY/share",
            "volume_input_unit": "lot",
            "volume_output_unit": "share",
            "timezone": "Asia/Shanghai",
            "conversion_notes": "provider lots converted to shares using documented adapter rule",
        },
        "market_data_boundaries": boundaries,
        "known_blockers": [],
        "provider_call_performed": True,
        "real_data_used": True,
        "credentials_saved": False,
        "holdout_observed": False,
    }


class ProviderValidationEvidenceTests(unittest.TestCase):
    def test_valid_record_is_fingerprinted_and_provider_side_ready(self):
        result = validate_provider_validation_evidence(valid_evidence())
        self.assertEqual(len(result["evidence_id"]), 64)
        self.assertTrue(result["required_core_interfaces_present"])
        self.assertEqual(result["missing_core_interfaces"], ())
        self.assertTrue(result["all_boundaries_verified"])
        self.assertTrue(result["interfaces_all_success"])
        self.assertTrue(result["can_support_holdout_opening"])

    def test_missing_required_core_interface_is_preserved_but_fail_closed(self):
        evidence = valid_evidence()
        evidence["interfaces"] = [
            item for item in evidence["interfaces"] if item["name"] != "adj_factor"
        ]
        result = validate_provider_validation_evidence(evidence)
        self.assertFalse(result["required_core_interfaces_present"])
        self.assertEqual(result["missing_core_interfaces"], ("adj_factor",))
        self.assertFalse(result["can_support_holdout_opening"])

    def test_unknown_boundary_is_allowed_but_fail_closed(self):
        evidence = valid_evidence()
        evidence["market_data_boundaries"]["suspension"]["status"] = "unknown"
        result = validate_provider_validation_evidence(evidence)
        self.assertFalse(result["all_boundaries_verified"])
        self.assertFalse(result["can_support_holdout_opening"])

    def test_explicit_blocker_is_allowed_but_fail_closed(self):
        evidence = valid_evidence()
        evidence["known_blockers"] = ["corporate-action event sample still pending"]
        self.assertFalse(validate_provider_validation_evidence(evidence)["can_support_holdout_opening"])

    def test_failed_real_interface_attempt_is_preserved_but_fail_closed(self):
        evidence = valid_evidence()
        evidence["interfaces"][0] = {
            "name": "daily",
            "status": "failed",
            "fields": [],
            "row_count": 0,
            "evidence": "authorized request returned provider permission error",
        }
        evidence["real_data_used"] = False
        result = validate_provider_validation_evidence(evidence)
        self.assertFalse(result["interfaces_all_success"])
        self.assertFalse(result["can_support_holdout_opening"])

    def test_success_interface_requires_nonempty_fields(self):
        evidence = valid_evidence()
        evidence["interfaces"][0]["fields"] = []
        with self.assertRaises(ValueError):
            validate_provider_validation_evidence(evidence)

    def test_success_interface_requires_positive_row_count(self):
        evidence = valid_evidence()
        evidence["interfaces"][0]["row_count"] = 0
        with self.assertRaises(ValueError):
            validate_provider_validation_evidence(evidence)

    def test_success_core_interfaces_require_adapter_fields(self):
        missing_cases = {
            "daily": "vol",
            "adj_factor": "ts_code",
            "stk_limit": "up_limit",
            "trade_cal": "exchange",
        }
        for interface_name, missing_field in missing_cases.items():
            with self.subTest(interface=interface_name, missing_field=missing_field):
                evidence = valid_evidence()
                interface = next(
                    item for item in evidence["interfaces"] if item["name"] == interface_name
                )
                interface["fields"] = [
                    field for field in interface["fields"] if field != missing_field
                ]
                with self.assertRaises(ValueError):
                    validate_provider_validation_evidence(evidence)

    def test_units_must_match_current_adapter_contract(self):
        invalid_units = {
            "currency": "USD",
            "price_unit": "CNY/lot",
            "volume_input_unit": "share",
            "volume_output_unit": "lot",
            "timezone": "UTC",
        }
        for field, invalid_value in invalid_units.items():
            with self.subTest(field=field, invalid_value=invalid_value):
                evidence = valid_evidence()
                evidence["units"][field] = invalid_value
                with self.assertRaises(ValueError):
                    validate_provider_validation_evidence(evidence)

    def test_provider_call_must_have_actually_been_attempted(self):
        evidence = valid_evidence()
        evidence["provider_call_performed"] = False
        with self.assertRaises(ValueError):
            validate_provider_validation_evidence(evidence)

    def test_license_must_be_authorized(self):
        evidence = valid_evidence()
        evidence["provider"]["license_status"] = "unknown"
        with self.assertRaises(ValueError):
            validate_provider_validation_evidence(evidence)

    def test_holdout_must_still_be_unobserved(self):
        evidence = valid_evidence()
        evidence["holdout_observed"] = True
        with self.assertRaises(ValueError):
            validate_provider_validation_evidence(evidence)

    def test_credentials_must_not_be_saved(self):
        evidence = valid_evidence()
        evidence["credentials_saved"] = True
        with self.assertRaises(ValueError):
            validate_provider_validation_evidence(evidence)

    def test_nested_sensitive_key_is_rejected(self):
        evidence = valid_evidence()
        evidence["provider"]["api_key_hint"] = "never-store-this"
        with self.assertRaises(ValueError):
            validate_provider_validation_evidence(evidence)

    def test_duplicate_interface_name_is_rejected(self):
        evidence = valid_evidence()
        evidence["interfaces"].append(copy.deepcopy(evidence["interfaces"][0]))
        with self.assertRaises(ValueError):
            validate_provider_validation_evidence(evidence)

    def test_sample_longer_than_366_natural_days_is_rejected(self):
        evidence = valid_evidence()
        evidence["sample"]["end_date"] = "2026-01-02"
        with self.assertRaises(ValueError):
            validate_provider_validation_evidence(evidence)

    def test_sample_security_code_must_be_supported_mainboard_format(self):
        evidence = valid_evidence()
        evidence["sample"]["security_code"] = "688001.SH"
        with self.assertRaises(ValueError):
            validate_provider_validation_evidence(evidence)

    def test_sample_cannot_extend_beyond_execution_date(self):
        evidence = valid_evidence()
        evidence["sample"]["start_date"] = "2026-09-01"
        evidence["sample"]["end_date"] = "2026-09-24"
        with self.assertRaises(ValueError):
            validate_provider_validation_evidence(evidence)

    def test_naive_execution_timestamp_is_rejected(self):
        evidence = valid_evidence()
        evidence["executed_at"] = "2026-09-23T12:00:00"
        with self.assertRaises(ValueError):
            validate_provider_validation_evidence(evidence)

    def test_supplied_evidence_id_must_match_canonical_payload(self):
        evidence = valid_evidence()
        evidence["evidence_id"] = "c" * 64
        with self.assertRaises(ValueError):
            validate_provider_validation_evidence(evidence)


if __name__ == "__main__":
    unittest.main()
