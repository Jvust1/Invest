"""Native-engine equivalence and the bounded, no-I/O adapter contract."""

from __future__ import annotations

import copy
import importlib.util
import json
import math
import statistics
import unittest
from unittest.mock import Mock, patch

from invest.opensource import data_engines


ENGINES = ("polars", "duckdb", "pyarrow")
FIXTURES = {
    "signed_integers": [-8, -3, -1, 0, 1, 2, 5, 12],
    "constant_zero": [0] * 8,
    "constant_nonzero": [4.25] * 20,
    "constant_tiny": [1e-200] * 8,
    "large_small_spread": [999000 + i / 8 for i in range(16)],
    "boundary_amplitude": [-1e6, 1e6] * 4,
    "maximum_length": [42 + ((i * 13) % 29 - 14) / 8 for i in range(5000)],
}


def installed(name: str) -> bool:
    """Only genuinely missing extras skip native tests; import failures fail."""
    return importlib.util.find_spec(name) is not None


class DataEngineInputTests(unittest.TestCase):
    def test_unknown_engine_rejected_before_optional_import(self) -> None:
        for name in ("sqlite", "numpy", "POLARS", "duckdb;select 1", None, [], True):
            with self.subTest(name=name), patch.object(data_engines, "load_dependency") as loader:
                with self.assertRaises(ValueError):
                    data_engines.run(name, {"values": list(range(8))})
                loader.assert_not_called()

    def test_extra_fields_cannot_introduce_sql_paths_urls_or_callbacks(self) -> None:
        for field in ("sql", "path", "url", "extension", "callback", "ddof"):
            for engine in ENGINES:
                payload = {"values": list(range(8)), field: "unused"}
                with self.subTest(engine=engine, field=field), patch.object(
                    data_engines, "load_dependency"
                ) as loader:
                    with self.assertRaises(ValueError):
                        data_engines.run(engine, payload)
                    loader.assert_not_called()

    def test_invalid_container_or_size_rejected_before_import(self) -> None:
        invalid = (None, [], {}, {"values": None}, {"values": "12345678"},
                   {"values": tuple(range(8))}, {"values": []},
                   {"values": list(range(7))}, {"values": [0] * 5001})
        for engine in ENGINES:
            for payload in invalid:
                with self.subTest(engine=engine, payload_type=type(payload)), patch.object(
                    data_engines, "load_dependency"
                ) as loader:
                    with self.assertRaises(ValueError):
                        data_engines.run(engine, payload)
                    loader.assert_not_called()

    def test_invalid_numeric_elements_rejected_before_import(self) -> None:
        invalid = (True, False, None, "1", "https://example.invalid", {}, [],
                   float("nan"), float("inf"), float("-inf"),
                   1000000.1, -1000000.1, 10**1000)
        for engine in ENGINES:
            for value in invalid:
                with self.subTest(engine=engine, value_type=type(value)), patch.object(
                    data_engines, "load_dependency"
                ) as loader:
                    with self.assertRaises(ValueError):
                        data_engines.run(engine, {"values": [0] * 7 + [value]})
                    loader.assert_not_called()

    def test_missing_dependency_is_explicit_not_python_fallback(self) -> None:
        for engine in ENGINES:
            with self.subTest(engine=engine), patch.object(
                data_engines, "load_dependency", side_effect=ValueError("unavailable")
            ):
                with self.assertRaisesRegex(ValueError, "unavailable"):
                    data_engines.run(engine, {"values": list(range(8))})

    def test_no_optional_import_when_module_is_reloaded(self) -> None:
        import importlib

        with patch("invest.opensource.common.load_dependency") as loader:
            importlib.reload(data_engines)
            loader.assert_not_called()
        # Restore the normal imported dependency function after the isolated check.
        importlib.reload(data_engines)

    def test_nonfinite_or_invalid_backend_results_are_not_reported(self) -> None:
        valid = {"count": 8, "mean": 1.0, "min": 0.0, "max": 2.0,
                 "std_population": 0.5}
        invalid = [dict(valid, count=7), dict(valid, std_population=-1)]
        for field in ("mean", "min", "max", "std_population"):
            invalid.extend(dict(valid, **{field: value})
                           for value in (None, float("nan"), float("inf")))
        for result in invalid:
            with self.subTest(result=result), patch.object(
                data_engines, "_polars", return_value=result
            ):
                with self.assertRaises(ValueError):
                    data_engines.run("polars", {"values": list(range(8))})


class DuckDBIsolationTests(unittest.TestCase):
    def test_only_fixed_query_bound_values_and_in_memory_safe_config(self) -> None:
        values = list(range(8))
        db = Mock()
        db.execute.return_value.fetchone.return_value = (8, 3.5, 0.0, 7.0, math.sqrt(5.25))
        dependency = Mock()
        dependency.connect.return_value = db
        with patch.object(data_engines, "load_dependency", return_value=dependency) as loader:
            result = data_engines.run("duckdb", {"values": values})
        loader.assert_called_once_with("duckdb", "duckdb")
        dependency.connect.assert_called_once()
        kwargs = dependency.connect.call_args.kwargs
        self.assertEqual(kwargs["database"], ":memory:")
        config = kwargs["config"]
        for key in ("enable_external_access", "autoinstall_known_extensions",
                    "autoload_known_extensions", "allow_unsigned_extensions"):
            self.assertEqual(config[key], "false")
        self.assertEqual(config["threads"], "1")
        self.assertEqual(config["temp_directory"], "")
        db.execute.assert_called_once_with(data_engines._DUCKDB_QUERY, [values])
        self.assertIn("?::DOUBLE[]", data_engines._DUCKDB_QUERY)
        db.close.assert_called_once_with()
        self.assertEqual(result["count"], 8)

    def test_connection_closed_after_native_query_failure(self) -> None:
        db = Mock()
        db.execute.side_effect = RuntimeError("native failure")
        dependency = Mock()
        dependency.connect.return_value = db
        with patch.object(data_engines, "load_dependency", return_value=dependency):
            with self.assertRaisesRegex(RuntimeError, "native failure"):
                data_engines.run("duckdb", {"values": list(range(8))})
        db.close.assert_called_once_with()

    def test_missing_row_is_not_reported_as_success(self) -> None:
        db = Mock()
        db.execute.return_value.fetchone.return_value = None
        dependency = Mock()
        dependency.connect.return_value = db
        with patch.object(data_engines, "load_dependency", return_value=dependency):
            with self.assertRaisesRegex(ValueError, "invalid"):
                data_engines.run("duckdb", {"values": list(range(8))})
        db.close.assert_called_once_with()


class NativeDataEngineTests(unittest.TestCase):
    def check_native(self, engine: str) -> None:
        """Reference is Python statistics, independent of all three backends."""
        if not installed(engine):
            self.skipTest(f"optional {engine} not installed")
        for label, values in FIXTURES.items():
            with self.subTest(engine=engine, fixture=label):
                payload = {"values": copy.deepcopy(values)}
                result = data_engines.run(engine, payload)
                self.assertEqual(payload, {"values": values})
                self.assertEqual(result["engine"], engine)
                self.assertEqual(result["operation"], "describe")
                self.assertEqual(result["ddof"], 0)
                self.assertEqual(result["count"], len(values))
                expected = {"mean": statistics.mean(values), "min": min(values),
                            "max": max(values), "std_population": statistics.pstdev(values)}
                for field, value in expected.items():
                    self.assertTrue(math.isclose(result[field], value,
                                                 rel_tol=1e-11, abs_tol=1e-10),
                                    (field, result[field], value))
                json.dumps(result, allow_nan=False)

    def test_real_polars_native_statistics(self) -> None:
        self.check_native("polars")

    def test_real_duckdb_native_statistics(self) -> None:
        self.check_native("duckdb")

    def test_real_pyarrow_native_statistics(self) -> None:
        self.check_native("pyarrow")

    def test_all_native_engines_equivalent(self) -> None:
        if not all(installed(engine) for engine in ENGINES):
            self.skipTest("all three optional data engines required")
        for label, values in FIXTURES.items():
            results = [data_engines.run(engine, {"values": values}) for engine in ENGINES]
            with self.subTest(fixture=label):
                for field in ("count", "mean", "min", "max", "std_population"):
                    for result in results[1:]:
                        self.assertTrue(math.isclose(result[field], results[0][field],
                                                     rel_tol=1e-11, abs_tol=1e-10),
                                        (field, result, results[0]))

    def test_native_underflow_is_rejected_not_zero_volatility(self) -> None:
        if not all(installed(engine) for engine in ENGINES):
            self.skipTest("all three optional data engines required")
        # At 1e-200 each engine previously returned a false zero; at 1e-162
        # their matching positive estimates were approximately 3% too small.
        for scale in (1e-200, 1e-162, 1e-160):
            values = [i * scale for i in range(8)]
            self.assertGreater(statistics.pstdev(values), 0)
            for engine in ENGINES:
                with self.subTest(engine=engine, scale=scale):
                    with self.assertRaisesRegex(ValueError, "NUMERIC_RANGE_EXCEEDED"):
                        data_engines.run(engine, {"values": values})

    def test_small_normal_variance_is_not_rejected(self) -> None:
        if not all(installed(engine) for engine in ENGINES):
            self.skipTest("all three optional data engines required")
        values = [i * 1e-150 for i in range(8)]
        expected = statistics.pstdev(values)
        for engine in ENGINES:
            with self.subTest(engine=engine):
                result = data_engines.run(engine, {"values": values})
                self.assertTrue(math.isclose(result["std_population"], expected,
                                             rel_tol=1e-12, abs_tol=0))


if __name__ == "__main__":
    unittest.main()
