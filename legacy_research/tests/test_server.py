import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from invest.server import InvestServer, StateStore


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = InvestServer(("127.0.0.1", 0), Path(self.temp.name))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        status, config = self.request("/api/config")
        self.assertEqual(status, 200)
        self.token = config["csrf_token"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temp.cleanup()

    def request(self, path, payload=None, *, headers=None, raw=None):
        data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
        actual_headers = {}
        if data is not None:
            actual_headers.update({"Content-Type": "application/json", "X-Invest-CSRF": getattr(self, "token", "")})
        actual_headers.update(headers or {})
        request = Request(self.url + path, data=data, headers=actual_headers)
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as exc:
            response = exc
        with response:
            body = response.read()
            return response.status, json.loads(body) if "application/json" in response.headers.get("Content-Type", "") else body

    def demo(self):
        status, dataset = self.request("/api/datasets/demo", {})
        self.assertEqual(status, 200, dataset)
        return dataset

    def test_complete_research_run_and_persistent_export(self):
        data = self.demo()
        self.assertEqual(data["meta"]["source_kind"], "demo")
        status, view = self.request("/api/research?dataset_id=" + data["id"])
        self.assertEqual(status, 200, view)
        self.assertEqual(len(view["symbols"]), 2)
        status, result = self.request("/api/backtest", {
            "dataset_id": data["id"], "symbol": "600000.SH", "cost_model_acknowledged": True,
        })
        self.assertEqual(status, 200, result)
        self.assertTrue(result["run_id"])
        self.assertGreater(len(result["curve"]), 20)
        self.assertEqual(result["dataset_id"], data["id"])
        status, exported = self.request("/api/export?dataset_id=" + data["id"])
        self.assertEqual(status, 200)
        self.assertEqual(exported["backtests"][0]["run_id"], result["run_id"])
        reopened = StateStore(Path(self.temp.name) / "state.sqlite")
        self.assertEqual(reopened.dataset(data["id"])["bars"], data["bars"])
        self.assertEqual(len(reopened.runs(data["id"])), 1)

    def test_duplicate_demo_does_not_create_duplicate_dataset(self):
        a, b = self.demo(), self.demo()
        self.assertEqual(a["id"], b["id"])
        _, listing = self.request("/api/datasets")
        self.assertEqual(len(listing["datasets"]), 1)

    def test_store_rejects_forged_identity_and_detects_local_corruption(self):
        dataset = self.demo()
        dataset["bars"][0]["close"] += 1
        with self.assertRaises(ValueError):
            self.server.state.save_dataset(dataset)
        with self.server.state.connection() as conn:
            conn.execute("UPDATE datasets SET payload=? WHERE id=?", (json.dumps(dataset), dataset["id"]))
        status, error = self.request("/api/datasets/" + dataset["id"])
        self.assertEqual(status, 400, error)

    def test_account_order_note_and_bad_order_rollback(self):
        data = self.demo()
        status, account = self.request("/api/accounts", {"name": "模拟验证", "initial_cash": 100000})
        self.assertEqual(status, 200, account)
        account_id = account["id"]
        order = {"dataset_id": data["id"], "symbol": "600000.SH", "date": data["calendar"][0],
                 "side": "BUY", "quantity": 100, "reason": "功能验证，不是真实买入", "cost_model_acknowledged": True}
        status, snapshot = self.request(f"/api/accounts/{account_id}/trades", order)
        self.assertEqual(status, 200, snapshot)
        self.assertEqual(snapshot["positions"][0]["quantity"], 100)
        status, error = self.request(f"/api/accounts/{account_id}/trades", dict(order, side="SELL"))
        self.assertEqual(status, 400, error)
        _, after = self.request(f"/api/accounts/{account_id}?dataset_id=" + data["id"])
        self.assertEqual(len(after["trades"]), 1)
        status, note = self.request("/api/notes", {"symbol": "600000.SH", "thesis": "趋势假设",
            "evidence": "仅功能演示", "risks": "合成数据", "invalidation": "真实证据不支持", "source_url": "https://example.com/source"})
        self.assertEqual(status, 200, note)
        _, notes = self.request("/api/notes")
        self.assertEqual(len(notes["notes"]), 1)

    def test_cross_site_and_wrong_host_cannot_read_private_data(self):
        self.assertEqual(self.request("/api/accounts", headers={"Origin": "https://hostile.invalid"})[0], 403)
        self.assertEqual(self.request("/api/config", headers={"Host": "hostile.invalid"})[0], 403)
        self.assertEqual(self.request("/api/config", headers={"Sec-Fetch-Site": "cross-site"})[0], 403)

    def test_post_requires_valid_csrf_and_never_writes_on_failure(self):
        for token in ["", "invalid"]:
            self.assertEqual(self.request("/api/accounts", {"name": "forbidden"}, headers={"X-Invest-CSRF": token})[0], 403)
        self.assertEqual(self.request("/api/accounts")[1]["accounts"], [])

    def test_duplicate_json_fields_nonfinite_and_nonobject_rejected(self):
        for raw in [b'{"initial_cash":100,"initial_cash":200}', b'{"initial_cash":NaN}', b'[]']:
            self.assertEqual(self.request("/api/accounts", raw=raw)[0], 400)

    def test_unknown_dataset_and_traversal_rejected(self):
        self.assertEqual(self.request("/api/datasets/not-an-id")[0], 404)
        self.assertEqual(self.request("/../SECURITY_POLICY.md")[0], 404)
        self.assertEqual(self.request("/.invest/state.sqlite")[0], 404)

    def test_import_requires_unit_declarations(self):
        self.assertEqual(self.request("/api/datasets/import", {"csv": "x", "source": "test"})[0], 400)
        self.assertEqual(self.request("/api/datasets")[1]["datasets"], [])

    def test_tushare_secret_not_returned_and_not_called_when_unconfigured(self):
        with patch.dict(os.environ, {"TUSHARE_TOKEN": ""}), patch("invest.server.fetch_tushare") as fetch:
            status, error = self.request("/api/datasets/tushare", {"symbol": "600000.SH", "start": "2025-01-01", "end": "2025-06-01"})
            self.assertEqual(status, 400)
            fetch.assert_not_called()
        with patch.dict(os.environ, {"TUSHARE_TOKEN": "private-test-token"}):
            _, config = self.request("/api/config")
            self.assertTrue(config["tushare_configured"])
            self.assertNotIn("private-test-token", json.dumps(config))

    def test_akshare_research_endpoint_and_config(self):
        with patch("invest.server.akshare_available", return_value=True):
            _, config = self.request("/api/config")
            self.assertTrue(config["akshare_available"])
        realish = self.demo()
        realish["meta"]["source_kind"] = "akshare"
        from invest import data as data_module
        realish["id"] = data_module.dataset_identity(realish)
        with patch("invest.server.fetch_akshare", return_value=realish) as fetch:
            status, result = self.request("/api/datasets/akshare", {
                "symbol": "600000.SH", "start": "2024-01-02", "end": "2024-01-03"
            })
        self.assertEqual(status, 200, result)
        self.assertEqual(result["meta"]["source_kind"], "akshare")
        fetch.assert_called_once_with("600000.SH", "2024-01-02", "2024-01-03")


    def test_refuses_unprotected_network_binding(self):
        with self.assertRaises(ValueError):
            InvestServer(("0.0.0.0", 0), Path(self.temp.name))


if __name__ == "__main__":
    unittest.main()
