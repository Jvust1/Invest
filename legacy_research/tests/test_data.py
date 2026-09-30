import copy
import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from invest import data


HEADER = ",".join(data.FIELDS) + "\n"
ROW = "600000.SH,2024-01-02,10,11,9,10.5,12300,false,12,8,1,false\n"
CALENDAR = "date\n2024-01-02\n"


def parse(text=HEADER + ROW, calendar=CALENDAR, source="自有历史导出"):
    return data.parse_csv(text, source=source, calendar_csv=calendar)


def response(fields, rows):
    return {"code": 0, "data": {"fields": fields.split(","), "items": rows}}


def provider(payload):
    name = payload["api_name"]
    if name == "daily":
        return response("ts_code,trade_date,open,high,low,close,vol", [["600000.SH", "20240102", 10, 11, 9, 10.5, 123.45]])
    if name == "adj_factor":
        return response("ts_code,trade_date,adj_factor", [["600000.SH", "20240102", 1]])
    if name == "stk_limit":
        return response("ts_code,trade_date,up_limit,down_limit", [["600000.SH", "20240102", 12, 8]])
    if name == "trade_cal":
        return response("exchange,cal_date,is_open", [["SSE", "20240102", 1]])
    raise AssertionError(name)


class CSVTests(unittest.TestCase):
    def test_good_csv_units_and_identity(self):
        first = parse()
        self.assertTrue(first["audit"]["backtest_ready"])
        self.assertEqual(first["meta"]["volume_unit"], "shares")
        self.assertEqual(first["meta"]["price_basis"], "raw")
        self.assertEqual(first["bars"][0]["volume_shares"], 12300)
        self.assertEqual(first["id"], parse()["id"])
        self.assertNotEqual(first["id"], parse(source="另一个来源")["id"])

    def test_identity_includes_calendar_and_units(self):
        original = parse()
        expanded = parse(calendar=CALENDAR + "2024-01-03\n")
        self.assertNotEqual(original["id"], expanded["id"])
        original["meta"]["retrieved_at"] = "changed"
        self.assertEqual(original["id"], data._identity(original))
        original["meta"]["volume_unit"] = "hands"
        self.assertNotEqual(original["id"], data._identity(original))

    def test_public_identity_validation_detects_changed_prices_and_missing_id(self):
        dataset = parse()
        data.verify_dataset_identity(dataset)
        dataset["bars"][0]["close"] = 10.6
        with self.assertRaisesRegex(ValueError, "指纹不一致"):
            data.verify_dataset_identity(dataset)
        dataset["id"] = data.dataset_identity(dataset)
        data.verify_dataset_identity(dataset)
        del dataset["id"]
        with self.assertRaises(ValueError):
            data.verify_dataset_identity(dataset)

    def test_underflow_and_subcent_price_rejected(self):
        for field, value in (("adj_factor", "1e-999"), ("close", "10.501"), ("up_limit", "12.001"), ("low", "1e-999")):
            row = ROW.strip().split(",")
            row[data.FIELDS.index(field)] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                parse(HEADER + ",".join(row) + "\n")

    def test_missing_or_duplicate_columns_rejected(self):
        for header in (HEADER.replace("open,", ""), HEADER.replace("open", "close")):
            with self.subTest(header=header), self.assertRaises(ValueError):
                parse(header + ROW)

    def test_unknown_unit_or_adjusted_fields_rejected(self):
        for column in ("vol", "qfq_close", "price_basis"):
            with self.subTest(column=column), self.assertRaises(ValueError):
                parse(HEADER.rstrip() + "," + column + "\n" + ROW.rstrip() + ",1\n")

    def test_empty_ragged_and_malformed_quotes(self):
        for text in ("", HEADER, HEADER + ROW.rstrip() + ",extra\n", HEADER + ROW.rsplit(",", 1)[0] + "\n", HEADER + '"unclosed'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse(text)

    def test_nonfinite_negative_fractional_volume(self):
        for field, value in (("open", "NaN"), ("close", "Infinity"), ("high", "1e999"), ("low", "-1"), ("adj_factor", "0"), ("volume_shares", "12.3"), ("volume_shares", "true")):
            row = ROW.strip().split(",")
            row[data.FIELDS.index(field)] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                parse(HEADER + ",".join(row) + "\n")

    def test_duplicate_or_reverse_dates(self):
        for rows in (ROW + ROW, ROW.replace("2024-01-02", "2024-01-03") + ROW):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                parse(HEADER + rows)

    def test_invalid_dates_and_timestamps(self):
        for day in ("2024-1-2", "2024-02-30", "2024-01-02T00:00:00Z", "9999-12-31"):
            with self.subTest(day=day), self.assertRaises(ValueError):
                parse(HEADER + ROW.replace("2024-01-02", day))

    def test_unsupported_codes(self):
        for symbol in ("688001.SH", "300001.SZ", "510300.SH", "920000.BJ", "600000.SZ", "000001.SH", "SH600000", "600000.sh"):
            with self.subTest(symbol=symbol), self.assertRaises(ValueError):
                parse(HEADER + ROW.replace("600000.SH", symbol))

    def test_source_required(self):
        for source in ("", "   ", "source\ntoken", None):
            with self.subTest(source=source), self.assertRaises(ValueError):
                parse(source=source)

    def test_ohlc_and_limit_conflicts(self):
        with self.assertRaises(ValueError):
            parse(HEADER + ROW.replace(",10,11,9,10.5,", ",12,11,9,10.5,"))
        result = parse(HEADER + ROW.replace(",false,12,8,1,false", ",false,10,8,1,false"))
        self.assertIn("high_above_limit", [item["code"] for item in result["audit"]["errors"]])
        self.assertFalse(result["audit"]["backtest_ready"])

    def test_missing_execution_fields_remain_unknown(self):
        result = parse(",".join(data.REQUIRED) + "\n" + ",".join(ROW.split(",")[:7]) + "\n")
        self.assertFalse(result["audit"]["backtest_ready"])
        for field in data.OPTIONAL:
            self.assertIsNone(result["bars"][0][field])
            self.assertIn("unknown_" + field, [item["code"] for item in result["audit"]["backtest_blockers"]])

    def test_flags_require_explicit_boolean(self):
        for field in ("suspended", "corporate_action"):
            for value in ("0", "1", "unknown", "no"):
                row = ROW.strip().split(",")
                row[data.FIELDS.index(field)] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    parse(HEADER + ",".join(row) + "\n")

    def test_suspension_requires_zero_volume(self):
        result = parse(HEADER + ROW.replace("12300,false", "12300,true"))
        self.assertEqual(result["audit"]["errors"][0]["code"], "suspension_volume_conflict")
        suspended = parse(HEADER + ROW.replace("12300,false", "0,true"))
        self.assertTrue(suspended["audit"]["backtest_ready"])

    def test_calendar_missing_mismatch_and_gap(self):
        self.assertFalse(parse(calendar="")["audit"]["backtest_ready"])
        mismatch = parse(calendar="date\n2024-01-03\n")
        self.assertEqual(mismatch["audit"]["errors"][0]["code"], "date_outside_calendar")
        gap = parse(HEADER + ROW + ROW.replace("2024-01-02", "2024-01-04"), "date\n2024-01-02\n2024-01-03\n2024-01-04\n")
        self.assertIn("missing_session", [item["code"] for item in gap["audit"]["errors"]])

    def test_calendar_shape_and_order(self):
        for calendar in ("date\n2024-01-02,1\n", "date\n2024-01-02\n2024-01-02\n", "date\n2024-01-03\n2024-01-02\n", "date\n\n"):
            with self.subTest(calendar=calendar), self.assertRaises(ValueError):
                parse(calendar=calendar)
        self.assertTrue(parse(calendar="2024-01-02\n")["audit"]["backtest_ready"])

    def test_action_or_factor_change_blocks(self):
        action = parse(HEADER + ROW.rstrip().removesuffix("false") + "true\n")
        self.assertFalse(action["audit"]["backtest_ready"])
        text = HEADER + ROW + ROW.replace("2024-01-02", "2024-01-03").replace(",1,false", ",1.1,false")
        result = parse(text, CALENDAR + "2024-01-03\n")
        self.assertIn("adjustment_factor_changed", [item["code"] for item in result["audit"]["backtest_blockers"]])

    def test_global_chronological_sort_with_per_symbol_order(self):
        other = ROW.replace("600000.SH", "000001.SZ")
        result = parse(HEADER + ROW + ROW.replace("2024-01-02", "2024-01-03") + other + other.replace("2024-01-02", "2024-01-03"), CALENDAR + "2024-01-03\n")
        self.assertEqual([bar["date"] for bar in result["bars"]], ["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-03"])
        self.assertTrue(result["audit"]["backtest_ready"])

    def test_demo_is_complete_deterministic_and_explicit(self):
        result = data.demo_dataset()
        self.assertEqual(len(result["calendar"]), 140)
        self.assertEqual(len(result["bars"]), 280)
        self.assertEqual(result["meta"]["source_kind"], "demo")
        self.assertIn("合成", result["meta"]["source"])
        self.assertTrue(result["audit"]["backtest_ready"])
        self.assertEqual(result["id"], data.demo_dataset()["id"])
        json.dumps(result, allow_nan=False)


class TushareTests(unittest.TestCase):
    def fetch(self):
        return data.fetch_tushare("600000.SH", "2024-01-02", "2024-01-02", token="secret-placeholder")

    def test_no_token_never_calls_network(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(data, "_transport") as transport:
            with self.assertRaisesRegex(ValueError, "TUSHARE_TOKEN"):
                data.fetch_tushare("600000.SH", "2024-01-02", "2024-01-02")
            transport.assert_not_called()

    def test_mock_normalization_and_secrets(self):
        with patch.object(data, "_transport", side_effect=provider) as transport:
            result = self.fetch()
        self.assertEqual(transport.call_count, 4)
        self.assertEqual(result["bars"][0]["volume_shares"], 12345)
        self.assertEqual(result["meta"]["source_kind"], "tushare")
        self.assertIsNone(result["bars"][0]["corporate_action"])
        self.assertIsNone(result["bars"][0]["suspended"])
        self.assertFalse(result["audit"]["backtest_ready"])
        self.assertNotIn("secret-placeholder", json.dumps(result))

    def test_token_can_only_come_from_trusted_caller_or_environment(self):
        with patch.dict(os.environ, {"TUSHARE_TOKEN": "env-secret"}), patch.object(data, "_transport", side_effect=provider) as transport:
            result = data.fetch_tushare("600000.SH", "2024-01-02", "2024-01-02")
        self.assertEqual(transport.call_args_list[0].args[0]["token"], "env-secret")
        self.assertNotIn("env-secret", json.dumps(result))

    def test_permission_denied_does_not_echo_server_secret(self):
        with patch.object(data, "_transport", return_value={"code": -2002, "msg": "secret-placeholder invalid"}):
            with self.assertRaises(ValueError) as caught:
                self.fetch()
        self.assertIn("未授权", str(caught.exception))
        self.assertNotIn("secret-placeholder", str(caught.exception))

    def test_optional_permission_loss_is_inspectable_blocker(self):
        def denied(payload):
            return {"code": -2002, "msg": "secret-placeholder"} if payload["api_name"] == "stk_limit" else provider(payload)
        with patch.object(data, "_transport", side_effect=denied):
            result = self.fetch()
        self.assertIsNone(result["bars"][0]["up_limit"])
        self.assertIn("provider_incomplete", [item["code"] for item in result["audit"]["backtest_blockers"]])
        self.assertNotIn("secret-placeholder", json.dumps(result))

    def test_missing_columns_or_ragged_response(self):
        for payload in (response("ts_code,trade_date", [["600000.SH", "20240102"]]), response("ts_code,trade_date,open,high,low,close,vol", [["600000.SH", "20240102"]])):
            with self.subTest(payload=payload), patch.object(data, "_transport", return_value=payload), self.assertRaises(ValueError):
                self.fetch()

    def test_symbol_mismatch_and_duplicate_daily(self):
        for mode in ("mismatch", "duplicate", "out_of_range"):
            def malformed(payload):
                result = provider(payload)
                if payload["api_name"] == "daily":
                    if mode == "mismatch":
                        result["data"]["items"][0][0] = "000001.SZ"
                    elif mode == "duplicate":
                        result["data"]["items"].append(result["data"]["items"][0][:])
                    else:
                        result["data"]["items"][0][1] = "20240103"
                return result
            with self.subTest(mode=mode), patch.object(data, "_transport", side_effect=malformed), self.assertRaises(ValueError):
                self.fetch()

    def test_partial_calendar_not_treated_as_complete(self):
        with patch.object(data, "_transport", side_effect=provider):
            result = data.fetch_tushare("600000.SH", "2024-01-01", "2024-01-02", token="placeholder")
        self.assertEqual(result["calendar"], [])
        self.assertIn("provider_calendar_incomplete", [item["code"] for item in result["audit"]["backtest_blockers"]])

    def test_calendar_accepts_documented_string_and_integer_flags_only(self):
        for open_flag, closed_flag in (("1", "0"), (1, 0)):
            def with_flags(payload):
                if payload["api_name"] == "trade_cal":
                    return response("exchange,cal_date,is_open", [["SSE", "20240101", closed_flag], ["SSE", "20240102", open_flag]])
                return provider(payload)
            with self.subTest(open_flag=open_flag), patch.object(data, "_transport", side_effect=with_flags):
                result = data.fetch_tushare("600000.SH", "2024-01-01", "2024-01-02", token="placeholder")
            self.assertEqual(result["calendar"], ["2024-01-02"])
            self.assertNotIn("provider_calendar_incomplete", [item["code"] for item in result["audit"]["backtest_blockers"]])
        for invalid in (True, False, 1.0, 0.0, "true", "false", "01", " 1", "", None, 2):
            def bad_flag(payload):
                result = provider(payload)
                if payload["api_name"] == "trade_cal":
                    result["data"]["items"][0][2] = invalid
                return result
            with self.subTest(invalid=invalid), patch.object(data, "_transport", side_effect=bad_flag):
                result = self.fetch()
            self.assertEqual(result["calendar"], [])
            self.assertIn("provider_calendar_incomplete", [item["code"] for item in result["audit"]["backtest_blockers"]])

    def test_missing_edge_day_not_filled_or_mistaken_for_suspension(self):
        def extended(payload):
            if payload["api_name"] == "trade_cal":
                return response("exchange,cal_date,is_open", [["SSE", "20240102", 1], ["SSE", "20240103", 1]])
            return provider(payload)
        with patch.object(data, "_transport", side_effect=extended):
            result = data.fetch_tushare("600000.SH", "2024-01-02", "2024-01-03", token="placeholder")
        self.assertEqual(len(result["bars"]), 1)
        self.assertIn("missing_session", [item["code"] for item in result["audit"]["errors"]])

    def test_fractional_shares_rejected(self):
        def fractional(payload):
            result = provider(payload)
            if payload["api_name"] == "daily":
                result["data"]["items"][0][-1] = 0.001
            return result
        with patch.object(data, "_transport", side_effect=fractional), self.assertRaises(ValueError):
            self.fetch()

    def test_request_bounds_prevent_network(self):
        with patch.object(data, "_transport") as transport:
            for symbol, start, end in (("600000.SH,000001.SZ", "2024-01-02", "2024-01-03"), ("600000.SH", "2022-01-01", "2024-01-01"), ("600000.SH", "2024-01-03", "2024-01-02")):
                with self.subTest(symbol=symbol, start=start), self.assertRaises(ValueError):
                    data.fetch_tushare(symbol, start, end, token="placeholder")
            transport.assert_not_called()

    def test_network_exception_does_not_leak_credentials(self):
        with patch.object(data, "_transport", side_effect=RuntimeError("secret-placeholder")):
            with self.assertRaises(ValueError) as caught:
                self.fetch()
        self.assertNotIn("secret-placeholder", str(caught.exception))

    def test_redirect_cannot_forward_credential(self):
        with self.assertRaises(ValueError):
            data._NoRedirect().redirect_request(None, None, 307, "redirect", {}, "https://other.example/")


class _FakeFrame:
    def __init__(self, rows):
        self._rows = rows
        self.columns = list(rows[0].keys()) if rows else []

    def to_dict(self, orient=None):
        if orient != "records":
            raise AssertionError("records orientation required")
        return [dict(row) for row in self._rows]


class _FakeAkShare:
    __version__ = "1.18.97"

    def stock_zh_a_hist(self, **kwargs):
        self.hist_kwargs = kwargs
        return _FakeFrame([
            {"日期": "2024-01-02", "股票代码": "600000", "开盘": 8.00, "收盘": 8.10, "最高": 8.20, "最低": 7.90, "成交量": 1234},
            {"日期": "2024-01-03", "股票代码": "600000", "开盘": 8.12, "收盘": 8.20, "最高": 8.30, "最低": 8.01, "成交量": 2000},
        ])

    def tool_trade_date_hist_sina(self):
        return _FakeFrame([
            {"trade_date": "2024-01-02"},
            {"trade_date": "2024-01-03"},
        ])


class AkShareAdapterTests(unittest.TestCase):
    def test_real_research_adapter_normalizes_unadjusted_daily_data(self):
        client = _FakeAkShare()
        result = data.fetch_akshare("600000.SH", "2024-01-02", "2024-01-03", client=client)
        self.assertEqual(result["meta"]["source_kind"], "akshare")
        self.assertEqual(result["meta"]["provider_price_adjustment"], "none")
        self.assertEqual(result["bars"][0]["volume_shares"], 123400)
        self.assertEqual(result["calendar"], ["2024-01-02", "2024-01-03"])
        self.assertIsNone(result["bars"][0]["suspended"])
        self.assertIsNone(result["bars"][0]["corporate_action"])
        self.assertFalse(result["audit"]["backtest_ready"])
        self.assertIn("akshare_research_only", [item["code"] for item in result["audit"]["warnings"]])
        self.assertEqual(client.hist_kwargs["adjust"], "")

    def test_calendar_failure_preserves_real_bars_and_blocks_execution(self):
        client = _FakeAkShare()
        def fail_calendar():
            raise RuntimeError("upstream unavailable")
        client.tool_trade_date_hist_sina = fail_calendar
        result = data.fetch_akshare("600000.SH", "2024-01-02", "2024-01-03", client=client)
        self.assertEqual(len(result["bars"]), 2)
        self.assertEqual(result["calendar"], [])
        self.assertIn("provider_calendar_incomplete", [item["code"] for item in result["audit"]["backtest_blockers"]])

    def test_symbol_mismatch_and_fractional_share_conversion_fail_closed(self):
        bad_symbol = _FakeAkShare()
        bad_symbol.stock_zh_a_hist = lambda **_: _FakeFrame([
            {"日期": "2024-01-02", "股票代码": "000001", "开盘": 8, "收盘": 8, "最高": 8, "最低": 8, "成交量": 1}
        ])
        with self.assertRaises(ValueError):
            data.fetch_akshare("600000.SH", "2024-01-02", "2024-01-02", client=bad_symbol)

        fractional = _FakeAkShare()
        fractional.stock_zh_a_hist = lambda **_: _FakeFrame([
            {"日期": "2024-01-02", "股票代码": "600000", "开盘": 8, "收盘": 8, "最高": 8, "最低": 8, "成交量": "0.001"}
        ])
        with self.assertRaises(ValueError):
            data.fetch_akshare("600000.SH", "2024-01-02", "2024-01-02", client=fractional)



if __name__ == "__main__":
    unittest.main()
