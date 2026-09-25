"""Local-only HTTP application. No brokerage, public hosting, or cloud account sync."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
from typing import Any
from urllib.parse import parse_qs, urlsplit
import uuid

from . import __version__
from .data import akshare_available, demo_dataset, fetch_akshare, fetch_tushare, parse_csv, verify_dataset_identity
from .engine import backtest, research
from .portfolio import PaperLedger

MAX_BODY = 2 * 1024 * 1024
DEFAULT_PARAMETERS = {
    "initial_cash": 100000,
    "fast": 5,
    "slow": 20,
    "commission_rate": 0.0003,
    "min_commission": 5,
    "stamp_tax_rate": 0.0005,
    "transfer_fee_rate": 0.00001,
    "slippage_bps": 5,
    "cost_model_acknowledged": False,
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _no_constant(value: str) -> None:
    raise ValueError("JSON 不能包含非有限数值")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON 存在重复字段")
        result[key] = value
    return result


class StateStore:
    """Content-addressed datasets and immutable run records; no delete API."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
            """)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def save_dataset(self, dataset: dict) -> dict:
        verify_dataset_identity(dataset)
        key = dataset.get("id", "")
        if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValueError("数据身份无效")
        payload = encode_json(dataset).decode("utf-8")
        with self.connection() as conn:
            conn.execute("INSERT OR IGNORE INTO datasets VALUES (?, ?, ?)", (key, payload, now()))
        return self.dataset(key)

    def dataset(self, key: str) -> dict:
        if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key):
            raise LookupError("数据集不存在，请先导入行情")
        with self.connection() as conn:
            row = conn.execute("SELECT payload FROM datasets WHERE id=?", (key,)).fetchone()
        if not row:
            raise LookupError("数据集不存在，请先导入行情")
        data = json.loads(row[0])
        verify_dataset_identity(data)
        return data

    def datasets(self) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("SELECT payload FROM datasets ORDER BY created_at DESC, id").fetchall()
        result = []
        for row in rows:
            data = json.loads(row[0])
            verify_dataset_identity(data)
            dates = [bar["date"] for bar in data["bars"]]
            result.append({
                "id": data["id"], "meta": data["meta"], "audit": data["audit"],
                "symbols": sorted({bar["symbol"] for bar in data["bars"]}),
                "start": min(dates) if dates else None,
                "end": max(dates) if dates else None, "rows": len(dates),
            })
        return result

    def save_run(self, result: dict) -> dict:
        record = dict(result, run_id=uuid.uuid4().hex, recorded_at=now(), program_version=__version__)
        with self.connection() as conn:
            conn.execute("INSERT INTO runs VALUES (?, ?, ?, ?)", (
                record["run_id"], record["dataset_id"], encode_json(record).decode(), record["recorded_at"],
            ))
        return record

    def runs(self, dataset_id: str | None) -> list[dict]:
        with self.connection() as conn:
            if dataset_id:
                rows = conn.execute("SELECT payload FROM runs WHERE dataset_id=? ORDER BY created_at DESC", (dataset_id,)).fetchall()
            else:
                rows = conn.execute("SELECT payload FROM runs ORDER BY created_at DESC").fetchall()
        return [json.loads(row[0]) for row in rows]


class InvestServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], data_dir: Path):
        if address[0] not in {"127.0.0.1", "localhost"}:
            raise ValueError("v0.1 仅允许本机访问；不提供公开托管或未认证局域网账户访问")
        self.state = StateStore(Path(data_dir) / "state.sqlite")
        self.ledger = PaperLedger(Path(data_dir) / "paper.sqlite")
        self.csrf_token = secrets.token_urlsafe(32)
        self.web_root = Path(__file__).parent / "web"
        super().__init__(address, InvestHandler)


class InvestHandler(BaseHTTPRequestHandler):
    server: InvestServer
    server_version = "Invest/" + __version__

    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def log_message(self, fmt, *args):
        # Do not log query strings, request bodies, private notes or upstream tokens.
        pass

    def _reply(self, code: int, data: Any = None, *, body: bytes | None = None,
               content_type: str = "application/json; charset=utf-8", attachment: str | None = None):
        body = encode_json(data) if body is None else body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if attachment:
            self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _request_context(self):
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        host = self.headers.get("Host", "")
        if host not in allowed:
            raise PermissionError("仅接受本机地址访问")
        origin = self.headers.get("Origin")
        if origin is not None and origin != "http://" + host:
            raise PermissionError("请求来源不匹配")
        fetch_site = self.headers.get("Sec-Fetch-Site", "")
        if fetch_site == "cross-site":
            raise PermissionError("不接受跨站请求")

    def _json_body(self) -> dict:
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("不支持分块请求")
        lengths = self.headers.get_all("Content-Length") or []
        if len(lengths) != 1 or not lengths[0].isdigit():
            raise ValueError("需要唯一且有效的 Content-Length")
        size = int(lengths[0])
        if not 0 < size <= MAX_BODY:
            raise ValueError("请求不能为空且不能超过 2 MiB")
        if self.headers.get_content_type() != "application/json":
            raise ValueError("请使用 JSON 请求")
        if not secrets.compare_digest(self.headers.get("X-Invest-CSRF", ""), self.server.csrf_token):
            raise PermissionError("请求令牌已失效，请刷新页面后重试")
        raw = self.rfile.read(size)
        if len(raw) != size:
            raise ValueError("请求内容不完整")
        data = json.loads(raw.decode("utf-8"), parse_constant=_no_constant, object_pairs_hook=_unique_object)
        if not isinstance(data, dict):
            raise ValueError("请求必须是 JSON 对象")
        return data

    def _dispatch(self):
        self._request_context()
        url = urlsplit(self.path)
        path = url.path
        query = parse_qs(url.query, strict_parsing=False)

        def parameter(name: str, required=False):
            items = query.get(name, [])
            if len(items) > 1 or (required and not items):
                raise ValueError("查询参数缺失或重复：" + name)
            return items[0] if items else None

        if self.command == "GET":
            if path in {"/", "/index.html", "/app.css", "/app.js"}:
                name = "index.html" if path == "/" else path[1:]
                mime = {"index.html": "text/html; charset=utf-8", "app.css": "text/css; charset=utf-8", "app.js": "text/javascript; charset=utf-8"}[name]
                return self._reply(200, body=(self.server.web_root / name).read_bytes(), content_type=mime)
            if path == "/api/config":
                return self._reply(200, {"version": __version__, "csrf_token": self.server.csrf_token,
                    "tushare_configured": bool(os.environ.get("TUSHARE_TOKEN")), "akshare_available": akshare_available(), "default_parameters": DEFAULT_PARAMETERS})
            if path == "/api/datasets":
                return self._reply(200, {"datasets": self.server.state.datasets()})
            if path.startswith("/api/datasets/"):
                return self._reply(200, self.server.state.dataset(path.split("/")[-1]))
            if path == "/api/research":
                return self._reply(200, research(self.server.state.dataset(parameter("dataset_id", True))))
            if path == "/api/runs":
                return self._reply(200, {"runs": self.server.state.runs(parameter("dataset_id"))})
            if path == "/api/export":
                dataset = self.server.state.dataset(parameter("dataset_id", True))
                return self._reply(200, {"version": __version__, "dataset": dataset,
                    "backtests": self.server.state.runs(dataset["id"])}, attachment="invest-research-export.json")
            if path == "/api/accounts":
                return self._reply(200, {"accounts": self.server.ledger.list_accounts()})
            match = re.fullmatch(r"/api/accounts/([A-Za-z0-9_-]+)", path)
            if match:
                key = parameter("dataset_id")
                dataset = self.server.state.dataset(key) if key else None
                return self._reply(200, self.server.ledger.snapshot(match[1], dataset))
            if path == "/api/notes":
                return self._reply(200, {"notes": self.server.ledger.list_notes()})
            raise LookupError("页面或记录不存在")

        payload = self._json_body()
        if path == "/api/datasets/demo":
            return self._reply(200, self.server.state.save_dataset(demo_dataset()))
        if path == "/api/datasets/import":
            if payload.get("raw_prices_confirmed") is not True or payload.get("volume_shares_confirmed") is not True:
                raise ValueError("导入前请确认：价格为未复权价格，成交量单位为股")
            csv_text, source, calendar_csv = payload.get("csv"), payload.get("source"), payload.get("calendar_csv", "")
            if not all(isinstance(x, str) for x in (csv_text, source, calendar_csv)):
                raise ValueError("CSV、来源和日历必须是文本")
            data = parse_csv(csv_text, source=source, calendar_csv=calendar_csv)
            return self._reply(200, self.server.state.save_dataset(data))
        if path == "/api/datasets/akshare":
            args = [payload.get(key) for key in ("symbol", "start", "end")]
            if not all(isinstance(x, str) for x in args):
                raise ValueError("请输入证券代码和日期范围")
            data = fetch_akshare(*args)
            return self._reply(200, self.server.state.save_dataset(data))
        if path == "/api/datasets/tushare":
            if not os.environ.get("TUSHARE_TOKEN"):
                raise ValueError("尚未配置 TUSHARE_TOKEN；可先载入合成示例或导入 CSV")
            args = [payload.get(key) for key in ("symbol", "start", "end")]
            if not all(isinstance(x, str) for x in args):
                raise ValueError("请输入证券代码和日期范围")
            data = fetch_tushare(*args)
            return self._reply(200, self.server.state.save_dataset(data))
        if path == "/api/backtest":
            key = payload.pop("dataset_id", None)
            result = backtest(self.server.state.dataset(key), payload)
            return self._reply(200, self.server.state.save_run(result))
        if path == "/api/accounts":
            return self._reply(200, self.server.ledger.create_account(payload.get("name"), payload.get("initial_cash", 100000)))
        match = re.fullmatch(r"/api/accounts/([A-Za-z0-9_-]+)/trades", path)
        if match:
            key = payload.pop("dataset_id", None)
            dataset = self.server.state.dataset(key)
            self.server.ledger.record_trade(match[1], dataset, payload)
            return self._reply(200, self.server.ledger.snapshot(match[1], dataset))
        if path == "/api/notes":
            return self._reply(200, self.server.ledger.save_note(payload))
        raise LookupError("接口不存在")

    def _handle(self):
        try:
            self._dispatch()
        except PermissionError as exc:
            self._reply(403, {"error": str(exc)})
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            # These errors originate in bounded validation; never return upstream raw payloads.
            self._reply(400, {"error": str(exc) or "输入无效"})
        except LookupError as exc:
            self._reply(404, {"error": str(exc)})
        except sqlite3.Error:
            self._reply(503, {"error": "本地数据暂不可写，请稍后重试；原记录保留"})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except Exception as exc:
            print("Invest internal error:", type(exc).__name__)
            self._reply(500, {"error": "操作未完成，原始记录保留。请检查本地运行环境。"})

    do_GET = _handle
    do_POST = _handle

    def do_OPTIONS(self):
        self._reply(405, {"error": "不支持跨站接口调用"})


def main(argv=None):
    parser = argparse.ArgumentParser(description="Invest — 人民币 A 股研究与模拟工作台")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=Path(".invest"), help="本地私密数据目录（默认 .invest）")
    parser.add_argument("--open", action="store_true", help="启动后打开本机浏览器")
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("端口应在 1024–65535 之间")
    app = InvestServer(("127.0.0.1", args.port), args.data_dir)
    print(f"Invest {__version__}: http://127.0.0.1:{app.server_port}")
    print("本机研究与模拟账本；按 Ctrl+C 停止。数据保存在：", args.data_dir.resolve())
    if args.open:
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{app.server_port}")
    try:
        app.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.server_close()


if __name__ == "__main__":
    main()
