import copy
import unittest
from unittest import mock

from invest import opening


H64_A = "a" * 64
H64_B = "b" * 64
H64_C = "c" * 64
H64_D = "d" * 64
G40 = "1" * 40


def valid_pair():
    boundaries = {
        key: {
            "status": "verified",
            "evidence": f"frozen evidence for {key}",
            "evidence_sha256": H64_D,
        }
        for key in opening.BOUNDARY_KEYS
    }
    provider_evidence = {
        "code_sha": G40,
        "dataset_identity": {
            "raw_artifact_identity": "local-authorized-snapshot-001",
            "raw_sha256": H64_A,
            "normalized_dataset_id": H64_B,
        },
        "market_data_boundaries": copy.deepcopy(boundaries),
    }
    provider_result = {
        "evidence_id": H64_C,
        "license_evidence_sha256": H64_D,
        "can_support_holdout_opening": True,
    }
    binding = {
        "provider_evidence": {
            "evidence_id": H64_C,
            "license_evidence_sha256": H64_D,
            "raw_sha256": H64_A,
            "normalized_dataset_id": H64_B,
            "code_sha": G40,
        },
        "dataset": {
            "raw_artifact_identity": "local-authorized-snapshot-001",
        },
        "market_data_boundaries": copy.deepcopy(boundaries),
    }
    binding_result = {
        "binding_id": "e" * 64,
        "can_open_holdout": True,
        "blocking_boundary_fields": [],
        "known_blockers": [],
    }
    return binding, provider_evidence, provider_result, binding_result


class OpeningModuleTests(unittest.TestCase):
    def validate_pair(self, binding, provider_evidence, provider_result, binding_result):
        with mock.patch.object(
            opening, "validate_provider_validation_evidence", return_value=provider_result
        ), mock.patch.object(
            opening, "validate_evaluation_binding", return_value=binding_result
        ):
            return opening.validate_opening_pair(binding, provider_evidence)

    def test_pair_validator_is_exposed(self):
        self.assertTrue(callable(opening.validate_opening_pair))

    def test_matching_pair_is_openable_when_both_sides_are_ready(self):
        binding, evidence, provider_result, binding_result = valid_pair()
        result = self.validate_pair(binding, evidence, provider_result, binding_result)
        self.assertTrue(result["provider_pair_verified"])
        self.assertTrue(result["provider_side_ready"])
        self.assertTrue(result["binding_side_ready"])
        self.assertTrue(result["can_open_holdout"])

    def test_identity_and_license_mismatches_fail_closed(self):
        cases = (
            ("evidence_id", "f" * 64),
            ("license_evidence_sha256", "0" * 64),
            ("raw_sha256", "1" * 64),
            ("normalized_dataset_id", "2" * 64),
            ("code_sha", "3" * 40),
        )
        for field, mismatched in cases:
            with self.subTest(field=field):
                binding, evidence, provider_result, binding_result = valid_pair()
                binding["provider_evidence"][field] = mismatched
                with self.assertRaisesRegex(ValueError, field):
                    self.validate_pair(binding, evidence, provider_result, binding_result)

    def test_raw_artifact_identity_mismatch_fails_closed(self):
        binding, evidence, provider_result, binding_result = valid_pair()
        binding["dataset"]["raw_artifact_identity"] = "different-local-snapshot"
        with self.assertRaisesRegex(ValueError, "raw_artifact_identity"):
            self.validate_pair(binding, evidence, provider_result, binding_result)

    def test_every_boundary_status_mismatch_fails_closed(self):
        for key in opening.BOUNDARY_KEYS:
            with self.subTest(boundary=key):
                binding, evidence, provider_result, binding_result = valid_pair()
                binding["market_data_boundaries"][key]["status"] = "unknown"
                with self.assertRaisesRegex(ValueError, rf"{key}\.status"):
                    self.validate_pair(binding, evidence, provider_result, binding_result)

    def test_every_boundary_evidence_hash_mismatch_fails_closed(self):
        for key in opening.BOUNDARY_KEYS:
            with self.subTest(boundary=key):
                binding, evidence, provider_result, binding_result = valid_pair()
                binding["market_data_boundaries"][key]["evidence_sha256"] = "9" * 64
                with self.assertRaisesRegex(ValueError, rf"{key}\.evidence_sha256"):
                    self.validate_pair(binding, evidence, provider_result, binding_result)

    def test_both_validators_must_independently_be_ready_to_open(self):
        for provider_ready, binding_ready in ((False, True), (True, False), (False, False)):
            with self.subTest(provider_ready=provider_ready, binding_ready=binding_ready):
                binding, evidence, provider_result, binding_result = valid_pair()
                provider_result["can_support_holdout_opening"] = provider_ready
                binding_result["can_open_holdout"] = binding_ready
                result = self.validate_pair(binding, evidence, provider_result, binding_result)
                self.assertTrue(result["provider_pair_verified"])
                self.assertEqual(result["provider_side_ready"], provider_ready)
                self.assertEqual(result["binding_side_ready"], binding_ready)
                self.assertFalse(result["can_open_holdout"])


if __name__ == "__main__":
    unittest.main()
