"""Portfolio allocation adapters."""
from __future__ import annotations
import numpy as np
import pandas as pd

from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit
from uuid import uuid4

from .data import is_mainboard_symbol, verify_dataset_identity
from .engine import execute_order, validate_market_window, validate_parameters
from ._vendor import load_vendor

def inverse_variance_weights(prices: pd.DataFrame) -> dict[str, float]:
    """Dependency-light fallback allocation for missing convex solvers."""
    if prices.shape[1] == 0:
        raise ValueError("prices must contain at least one asset")
    returns = prices.astype("float64").pct_change().dropna(how="all")
    variances = returns.var(ddof=1).replace([np.inf, -np.inf], np.nan)
    if variances.isna().all():
        raise ValueError("prices do not contain enough variation")
    variances = variances.fillna(variances.dropna().median()).clip(lower=np.finfo(float).eps)
    raw = 1.0 / variances
    weights = raw / raw.sum()
    return {str(name): float(value) for name, value in weights.items()}

def minimum_variance_weights(prices: pd.DataFrame, weight_bounds: tuple[float, float] = (0.0, 1.0)) -> dict[str, float]:
    """Use vendored PyPortfolioOpt when its optional solver stack is present."""
    if not isinstance(prices, pd.DataFrame) or prices.shape[1] == 0:
        raise ValueError("prices must be a non-empty DataFrame")
    lower, upper = weight_bounds
    if not 0 <= lower <= upper:
        raise ValueError("weight_bounds must satisfy 0 <= lower <= upper")
    try:
        from pypfopt import EfficientFrontier, expected_returns, risk_models
        load_vendor("pypfopt")
        mu = expected_returns.mean_historical_return(prices)
        covariance = risk_models.sample_cov(prices)
        optimizer = EfficientFrontier(mu, covariance, weight_bounds=weight_bounds)
        optimizer.min_volatility()
        cleaned = optimizer.clean_weights()
        return {str(name): float(value) for name, value in cleaned.items()}
    except (ImportError, ModuleNotFoundError, RuntimeError, ValueError):
        return inverse_variance_weights(prices)

def optimize_weights(returns, engine: str = "auto") -> dict[str, float]:
    """Select a portfolio engine behind one stable return-weights interface."""
    frame = pd.DataFrame(returns).astype(float)
    if frame.empty or frame.shape[1] == 0:
        raise ValueError("returns must contain at least one asset")
    if engine == "inverse_variance":
        return inverse_variance_weights((1.0 + frame).cumprod())
    if engine == "riskfolio":
        from .riskfolio_adapter import riskfolio_weights
        return riskfolio_weights(frame)
    if engine == "skfolio":
        from .skfolio_adapter import skfolio_weights
        return skfolio_weights(frame)
    if engine == "pypfopt":
        return minimum_variance_weights((1.0 + frame).cumprod())
    if engine == "auto":
        return optimize_weights(frame, engine="skfolio")
    raise ValueError("engine must be one of: auto, inverse_variance, pypfopt, riskfolio, skfolio")


# Restored append-only paper ledger API retained by the desktop and server layers.
CENT = Decimal("0.01")
COST_FIELDS = ("commission_rate", "min_commission", "stamp_tax_rate", "transfer_fee_rate", "slippage_bps", "cost_model_acknowledged")
HTML = re.compile(r"<\s*/?\s*[A-Za-z][^>]*>")
SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    initial_cash_cents INTEGER NOT NULL CHECK(initial_cash_cents > 0),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trades (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    trade_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
    quantity INTEGER NOT NULL CHECK(quantity > 0 AND quantity % 100 = 0),
    record_json TEXT NOT NULL,
    checkpoint_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS trades_account_sequence ON trades(account_id, sequence);
CREATE TABLE IF NOT EXISTS notes (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    record_json TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS trades_append_only_update
BEFORE UPDATE ON trades BEGIN SELECT RAISE(ABORT, 'append-only trade journal'); END;
CREATE TRIGGER IF NOT EXISTS trades_append_only_delete
BEFORE DELETE ON trades BEGIN SELECT RAISE(ABORT, 'append-only trade journal'); END;
CREATE TRIGGER IF NOT EXISTS accounts_append_only_update
BEFORE UPDATE ON accounts BEGIN SELECT RAISE(ABORT, 'append-only account journal'); END;
CREATE TRIGGER IF NOT EXISTS accounts_append_only_delete
BEFORE DELETE ON accounts BEGIN SELECT RAISE(ABORT, 'append-only account journal'); END;
CREATE TRIGGER IF NOT EXISTS notes_append_only_update
BEFORE UPDATE ON notes BEGIN SELECT RAISE(ABORT, 'append-only research journal'); END;
CREATE TRIGGER IF NOT EXISTS notes_append_only_delete
BEFORE DELETE ON notes BEGIN SELECT RAISE(ABORT, 'append-only research journal'); END;
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _money(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("金额必须是有限数字。")
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or abs(amount) > Decimal("1000000000"):
            raise ValueError("金额必须有限，且不得超过十亿元。")
        rounded = amount.quantize(CENT, rounding=ROUND_HALF_UP)
        if amount != rounded:
            raise ValueError("初始资金最多保留两位小数。")
        return rounded
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("金额必须是有限的人民币数值。") from exc


def _text(value, label, maximum=4000, *, required=True):
    if not isinstance(value, str):
        raise ValueError(f"{label}必须是纯文本。")
    value = value.strip()
    if (required and not value) or len(value) > maximum:
        raise ValueError(f"{label}不能为空，且不得超过 {maximum} 字符。")
    if HTML.search(value) or any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise ValueError(f"{label}只能包含纯文本，不允许 HTML 或控制字符。")
    return value


def _symbol(value):
    if not is_mainboard_symbol(value):
        raise ValueError("仅支持 600000.SH / 000001.SZ 格式的沪深主板股票。")
    return value


def _date(value):
    if not isinstance(value, str):
        raise ValueError("交易日期必须使用 YYYY-MM-DD 格式。")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("交易日期无效。") from exc
    if parsed.isoformat() != value:
        raise ValueError("交易日期必须使用 YYYY-MM-DD 格式。")
    return value


def _canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("行情必须由有限数字和普通 JSON 数据组成。") from exc


def _provenance(dataset):
    if not isinstance(dataset, dict):
        raise ValueError("请先选择已审计的数据集。")
    verify_dataset_identity(dataset)
    identity = dataset.get("id")
    if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{64}", identity):
        raise ValueError("数据集缺少有效的 SHA256 身份。")
    meta = dataset.get("meta")
    if not isinstance(meta, dict) or not isinstance(meta.get("source"), str) or not meta["source"].strip():
        raise ValueError("数据集必须说明来源。")
    return {key: meta.get(key) for key in ("source", "source_kind", "currency", "price_basis", "volume_unit", "calendar_source")}


def _checkpoint(dataset, symbol, start, end):
    """Store the checked holding lifecycle, not a mutable pointer to market data."""
    bars = validate_market_window(dataset, symbol, start_date=start, end_date=end)
    if not bars or bars[0]["date"] != start or bars[-1]["date"] != end:
        raise ValueError("行情不覆盖持仓开始日和本次记账日期。")
    record = {
        "source": _provenance(dataset),
        "start": start,
        "end": end,
        "bars": bars,
        "calendar": [d for d in dataset["calendar"] if start <= d <= end],
    }
    return record


def _check_compatible(dataset, symbol, old):
    if old["source"] != _provenance(dataset):
        raise ValueError("持仓期间不能切换不兼容的数据来源、单位或价格口径。")
    current = _checkpoint(dataset, symbol, old["start"], old["end"])
    if _canonical(current) != _canonical(old):
        raise ValueError("持仓期间历史行情已变更；请保留原数据并另建模拟账户复核。")


class PaperLedger:
    """A private SQLite journal; callers must locate it in ignored runtime data."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass  # Windows permissions are inherited from the private user folder.

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(str(self.path), timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        try:
            yield db
        finally:
            db.close()

    @staticmethod
    def _account(db, account_id):
        if not isinstance(account_id, str):
            raise ValueError("模拟账户 ID 无效。")
        row = db.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        if row is None:
            raise ValueError("模拟账户不存在。")
        return row

    @staticmethod
    def _state(db, row):
        cash = Decimal(row["initial_cash_cents"]) / 100
        positions = {}
        trades = []
        for item in db.execute("SELECT * FROM trades WHERE account_id=? ORDER BY sequence", (row["id"],)):
            record = json.loads(item["record_json"])
            trades.append(record)
            cash = Decimal(record["cash_after_exact"])
            pos = positions.setdefault(item["symbol"], {
                "quantity": 0, "cost": Decimal(0), "buys": [],
                "start": item["trade_date"], "last_date": item["trade_date"],
            })
            quantity = item["quantity"]
            if item["side"] == "BUY":
                if pos["quantity"] == 0:
                    pos["start"] = item["trade_date"]
                pos["cost"] += Decimal(record["gross_exact"]) + Decimal(record["fees_exact"])
                pos["quantity"] += quantity
                pos["buys"].append((item["trade_date"], quantity))
            else:
                removed = (pos["cost"] * quantity / pos["quantity"]).quantize(CENT, rounding=ROUND_HALF_UP)
                pos["cost"] -= removed
                pos["quantity"] -= quantity
                if pos["quantity"] == 0:
                    pos["cost"] = Decimal(0)
                    pos["buys"] = []
            pos["last_date"] = item["trade_date"]
            pos["checkpoint"] = json.loads(item["checkpoint_json"])
        return cash, positions, trades

    def create_account(self, name, initial_cash=100000):
        name = _text(name, "账户名称", 80)
        cash = _money(initial_cash)
        if cash <= 0:
            raise ValueError("初始资金必须大于零。")
        account_id = uuid4().hex
        created = _now()
        with self._connection() as db:
            db.execute("INSERT INTO accounts VALUES (?, ?, ?, ?)", (account_id, name, int(cash * 100), created))
        return {"id": account_id, "name": name, "initial_cash": float(cash), "cash": float(cash), "created_at": created}

    def list_accounts(self):
        with self._connection() as db:
            db.execute("BEGIN")
            result = []
            for row in db.execute("SELECT * FROM accounts ORDER BY created_at, id").fetchall():
                cash, _, _ = self._state(db, row)
                result.append({"id": row["id"], "name": row["name"], "initial_cash": row["initial_cash_cents"] / 100, "cash": float(cash), "created_at": row["created_at"]})
            return result

    def record_trade(self, account_id, dataset, payload):
        if not isinstance(payload, dict):
            raise ValueError("交易输入必须是 JSON 对象。")
        symbol = _symbol(payload.get("symbol"))
        day = _date(payload.get("date"))
        side = payload.get("side")
        if side not in ("BUY", "SELL"):
            raise ValueError("交易方向只能为 BUY 或 SELL。")
        quantity = payload.get("quantity")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0 or quantity % 100 or quantity > 100_000_000:
            raise ValueError("模拟交易数量须为正整数、100 股的倍数，且不超过一亿股。")
        reason = _text(payload.get("reason"), "交易理由")
        cost_input = {key: payload[key] for key in COST_FIELDS if key in payload}
        source = _provenance(dataset)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = self._account(db, account_id)
                params = validate_parameters({**cost_input, "initial_cash": row["initial_cash_cents"] / 100}, require_strategy=False)
                cash, positions, trades = self._state(db, row)
                if trades and day < trades[-1]["date"]:
                    raise ValueError("模拟账户按日期顺序记账，不能回填早于上一笔的日期。")
                pos = positions.get(symbol)
                held = pos["quantity"] if pos else 0
                if held:
                    _check_compatible(dataset, symbol, pos["checkpoint"])
                    start = pos["start"]
                else:
                    start = day
                checkpoint = _checkpoint(dataset, symbol, start, day)
                bar = checkpoint["bars"][-1]
                day_volume = sum(t["quantity"] for t in trades if t["symbol"] == symbol and t["date"] == day)
                if day_volume + quantity > bar["volume_shares"]:
                    raise ValueError("同一模拟账户的当日累计成交量不能超过行情实际股数。")
                today_buys = sum(q for d, q in pos["buys"] if d == day) if pos else 0
                available = max(0, held - today_buys)
                execution = execute_order(bar, side, quantity, cash, available, params)
                record = {
                    "id": uuid4().hex, "account_id": account_id, "symbol": symbol,
                    "date": day, "side": side, "quantity": quantity,
                    "reason": reason, "dataset_id": dataset["id"],
                    "dataset_source": source["source"], "source_kind": source["source_kind"],
                    "history_sha256": hashlib.sha256(_canonical(checkpoint).encode()).hexdigest(),
                    "recorded_at": _now(), "parameters": params,
                    "execution_basis": "历史原始开盘价及显式固定费用场景；非券商成交",
                }
                for key in ("price", "gross", "commission", "stamp_tax", "transfer_fee", "fees", "cash_after"):
                    value = Decimal(str(execution[key]))
                    record[key] = float(value)
                    record[key + "_exact"] = str(value)
                db.execute(
                    "INSERT INTO trades(id, account_id, trade_date, symbol, side, quantity, record_json, checkpoint_json) VALUES(?,?,?,?,?,?,?,?)",
                    (record["id"], account_id, day, symbol, side, quantity, _canonical(record), _canonical(checkpoint)),
                )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return self.snapshot(account_id, dataset)

    def snapshot(self, account_id, dataset=None):
        if dataset is not None:
            _provenance(dataset)
        with self._connection() as db:
            db.execute("BEGIN")
            row = self._account(db, account_id)
            cash, holdings, trades = self._state(db, row)
            account = {"id": row["id"], "name": row["name"], "initial_cash": row["initial_cash_cents"] / 100, "cash": float(cash), "created_at": row["created_at"]}
        positions = []
        risk_notes = ["历史模拟记账，不接入券商；持仓与研究笔记只保存在本机。"]
        complete = True
        total = cash
        values = []
        for symbol, pos in sorted(holdings.items()):
            if not pos["quantity"]:
                continue
            entry = {"symbol": symbol, "quantity": pos["quantity"], "average_cost": float(pos["cost"] / pos["quantity"]), "market_price": None, "market_value": None, "unrealized_pnl": None, "mark_date": None}
            try:
                if dataset is None:
                    raise ValueError("未选择估值行情。")
                _check_compatible(dataset, symbol, pos["checkpoint"])
                latest = max(b["date"] for b in dataset.get("bars", []))
                if latest < pos["last_date"]:
                    raise ValueError("行情日期早于最近一笔交易。")
                checkpoint = _checkpoint(dataset, symbol, pos["start"], latest)
                bar = checkpoint["bars"][-1]
                price = Decimal(str(bar["close"]))
                value = (price * pos["quantity"]).quantize(CENT, rounding=ROUND_HALF_UP)
                entry.update(market_price=float(price), market_value=float(value), unrealized_pnl=float(value - pos["cost"]), mark_date=latest)
                values.append(value)
                total += value
                if dataset["meta"].get("source_kind") == "demo":
                    risk_notes.append(f"{symbol} 使用合成演示行情估值。")
            except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
                complete = False
                entry["valuation_warning"] = str(exc)
                risk_notes.append(f"{symbol} 估值缺失：{exc}")
            positions.append(entry)
        largest = float(max(values) / total) if complete and values and total > 0 else (0.0 if complete and not values else None)
        if largest is not None and largest > 0.5:
            risk_notes.append("单一持仓超过总资产的 50%，存在集中度风险。")
        if positions:
            risk_notes.append("成本包含买入费用；未实现盈亏未预扣未来卖出费用。估值日期见各持仓，不是实时行情。")
        return {"account": account, "positions": positions, "trades": trades, "equity": float(total) if complete else None, "valuation_complete": complete, "risk": {"largest_position_weight": largest, "notes": risk_notes}}

    def save_note(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("研究笔记必须是 JSON 对象。")
        note = {"id": uuid4().hex, "symbol": _symbol(payload.get("symbol")), "created_at": _now()}
        for key, label in (("thesis", "投资假设"), ("evidence", "证据"), ("risks", "风险"), ("invalidation", "失效条件")):
            note[key] = _text(payload.get(key), label, 12000)
        url = _text(payload.get("source_url"), "来源链接", 2000)
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in url):
                raise ValueError
            parsed.port
        except ValueError as exc:
            raise ValueError("来源必须是有效的 http/https 链接，不能含登录凭据。") from exc
        note["source_url"] = url
        with self._connection() as db:
            db.execute("INSERT INTO notes(id, record_json) VALUES(?,?)", (note["id"], _canonical(note)))
        return note

    def list_notes(self):
        with self._connection() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT record_json FROM notes ORDER BY sequence DESC")]
