"""Cloud research job used by ChatGPT/GitHub integration.

This module intentionally produces PUBLIC_RESEARCH_ONLY evidence.  It must not
create an evaluation binding, open a holdout, authorize trading, or pretend
that public-web data has independently verified licensing/market facts.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from invest.data import is_mainboard_symbol


SCHEMA = "invest-assistant-job-v1"
RESULT_SCHEMA = "invest-public-research-result-v1"
MAX_DAYS = 366
ALLOWED = {"schema", "job_id", "operation", "symbol", "start_date", "end_date"}


class JobError(ValueError):
    pass


def _parse_date(value: object, name: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise JobError(f"{name} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise JobError(f"{name} is invalid") from None


def load_request(path: Path) -> dict:
    try:
        request = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JobError("request JSON is unreadable") from exc
    if not isinstance(request, dict) or set(request) - ALLOWED:
        raise JobError("request has unsupported fields")
    if request.get("schema") != SCHEMA or request.get("operation") != "public_stock_research":
        raise JobError("unsupported job schema or operation")
    job_id = request.get("job_id")
    if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,80}", job_id):
        raise JobError("job_id is invalid")
    symbol = request.get("symbol")
    if not is_mainboard_symbol(symbol):
        raise JobError("only the Invest main-board symbol contract is accepted")
    start = _parse_date(request.get("start_date"), "start_date")
    end = _parse_date(request.get("end_date"), "end_date")
    if start > end:
        raise JobError("start_date is after end_date")
    if end > datetime.now(timezone.utc).date():
        raise JobError("future dates are not accepted")
    if (end - start).days > MAX_DAYS:
        raise JobError(f"range exceeds {MAX_DAYS} natural days")
    return dict(request)


def _as_date(value: object) -> str:
    text = str(value)
    if len(text) >= 10:
        text = text[:10]
    return _parse_date(text, "provider date").isoformat()


def _finite(value: object, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise JobError(f"{name} is not numeric") from None
    if not math.isfinite(number):
        raise JobError(f"{name} is not finite")
    return number


def normalize_frame(frame) -> list[dict]:
    required = {"日期", "开盘", "收盘", "最高", "最低"}
    if frame is None or getattr(frame, "empty", True):
        raise JobError("provider returned no rows")
    columns = {str(c) for c in frame.columns}
    missing = required - columns
    if missing:
        raise JobError("provider response missing columns: " + ",".join(sorted(missing)))
    rows: list[dict] = []
    for _, source in frame.iterrows():
        row = {
            "date": _as_date(source["日期"]),
            "open": _finite(source["开盘"], "open"),
            "close": _finite(source["收盘"], "close"),
            "high": _finite(source["最高"], "high"),
            "low": _finite(source["最低"], "low"),
        }
        if min(row["open"], row["close"], row["high"], row["low"]) <= 0:
            raise JobError("provider returned non-positive prices")
        if row["low"] > min(row["open"], row["close"]) or row["high"] < max(row["open"], row["close"]):
            raise JobError("provider OHLC relation is invalid")
        for src, dst in (("成交量", "volume_provider_unit"), ("成交额", "amount"),
                         ("换手率", "turnover_rate_pct"), ("涨跌幅", "change_pct")):
            if src in columns:
                value = source[src]
                try:
                    row[dst] = _finite(value, dst)
                except JobError:
                    row[dst] = None
        rows.append(row)
    rows.sort(key=lambda item: item["date"])
    days = [r["date"] for r in rows]
    if days != sorted(set(days)):
        raise JobError("provider dates are duplicated")
    return rows


def _return(closes: list[float], sessions: int) -> float | None:
    if len(closes) <= sessions:
        return None
    return closes[-1] / closes[-1-sessions] - 1


def _ma(closes: list[float], sessions: int) -> float | None:
    if len(closes) < sessions:
        return None
    return sum(closes[-sessions:]) / sessions


def summarize(rows: list[dict]) -> dict:
    if not rows:
        raise JobError("no normalized rows")
    closes = [float(r["close"]) for r in rows]
    returns = [closes[i] / closes[i-1] - 1 for i in range(1, len(closes))]
    peak = closes[0]
    drawdown = 0.0
    for close in closes:
        peak = max(peak, close)
        drawdown = min(drawdown, close / peak - 1)
    volatility = statistics.stdev(returns) * math.sqrt(252) if len(returns) >= 2 else None
    return {
        "sessions": len(rows),
        "first_date": rows[0]["date"],
        "last_date": rows[-1]["date"],
        "first_close": closes[0],
        "last_close": closes[-1],
        "period_return": closes[-1] / closes[0] - 1,
        "return_5_sessions": _return(closes, 5),
        "return_20_sessions": _return(closes, 20),
        "ma_5": _ma(closes, 5),
        "ma_20": _ma(closes, 20),
        "ma_60": _ma(closes, 60),
        "annualized_daily_volatility": volatility,
        "max_close_drawdown": drawdown,
        "period_high": max(float(r["high"]) for r in rows),
        "period_low": min(float(r["low"]) for r in rows),
    }


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def write_csv(rows: list[dict], path: Path) -> None:
    fields = ["date", "open", "high", "low", "close", "volume_provider_unit",
              "amount", "turnover_rate_pct", "change_pct"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value*100:.2f}%"


def render_report(result: dict) -> str:
    s = result["summary"]
    return f"""# Invest 云端公开研究报告

- Job：{result['job_id']}
- 标的：{result['symbol']}
- 区间：{s['first_date']} → {s['last_date']}
- 数据层级：**PUBLIC_RESEARCH_ONLY**
- 数据接口：AKShare `stock_zh_a_hist`，版本 {result['provider']['akshare_version']}
- 运行源码：{result['repository']['commit']}

## 客观统计

- 交易日数：{s['sessions']}
- 区间首/末收盘：{s['first_close']:.2f} / {s['last_close']:.2f}
- 区间价格变化：{_pct(s['period_return'])}
- 最近 5 个交易日变化：{_pct(s['return_5_sessions'])}
- 最近 20 个交易日变化：{_pct(s['return_20_sessions'])}
- 收盘序列最大回撤：{_pct(s['max_close_drawdown'])}
- 日收益年化波动率：{_pct(s['annualized_daily_volatility'])}
- MA5 / MA20 / MA60：{s['ma_5'] if s['ma_5'] is not None else 'N/A'} / {s['ma_20'] if s['ma_20'] is not None else 'N/A'} / {s['ma_60'] if s['ma_60'] is not None else 'N/A'}
- 区间最高 / 最低：{s['period_high']:.2f} / {s['period_low']:.2f}

## 边界

这份结果用于公开数据研究和 ChatGPT ↔ Invest 云端协作验证。它**不是**经独立许可审阅的真实执行数据，
不提供完整停复牌、公司行动、历史有效交易规则或券商成本事实，因此不会送入 Invest 的正式执行回测、
evaluation binding、frozen holdout 或交易授权链。AKShare 自身也将其数据接口定位为研究用途并提示数据风险。

没有买卖结论、收益承诺或自动下单。
"""


def run(request_path: Path, output: Path) -> dict:
    request = load_request(request_path)
    output.mkdir(parents=True, exist_ok=False)
    (output / "request.json").write_bytes(_canonical(request) + b"\n")
    try:
        import akshare as ak
        frame = ak.stock_zh_a_hist(
            symbol=request["symbol"][:6],
            period="daily",
            start_date=request["start_date"].replace("-", ""),
            end_date=request["end_date"].replace("-", ""),
            adjust="",
        )
        rows = normalize_frame(frame)
        summary = summarize(rows)
        csv_path = output / "market-data.csv"
        write_csv(rows, csv_path)
        csv_hash = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        result = {
            "schema": RESULT_SCHEMA,
            "status": "PASS",
            "job_id": request["job_id"],
            "operation": request["operation"],
            "symbol": request["symbol"],
            "requested_range": {"start": request["start_date"], "end": request["end_date"]},
            "summary": summary,
            "provider": {
                "name": "AKShare",
                "interface": "stock_zh_a_hist",
                "akshare_version": getattr(ak, "__version__", "UNKNOWN"),
                "license_or_rights_independently_verified": False,
                "data_scope": "PUBLIC_RESEARCH_ONLY",
                "raw_provider_units_preserved": True,
            },
            "repository": {
                "commit": __import__("os").environ.get("GITHUB_SHA", "LOCAL"),
                "workflow_run_id": __import__("os").environ.get("GITHUB_RUN_ID"),
            },
            "artifacts": {"normalized_csv_sha256": csv_hash, "rows": len(rows)},
            "gates": {
                "execution_authorized": False,
                "evaluation_binding_created": False,
                "frozen_holdout_opened": False,
                "broker_connected": False,
                "real_market_acceptance": False,
            },
            "limitations": [
                "public research data is not independently licensed/verified execution evidence",
                "suspension/company actions/effective-date market rules are not completed by this job",
                "provider volume units are preserved as provider output and are not promoted to Invest execution volume",
                "this job computes descriptive statistics only and does not issue a buy/sell recommendation",
            ],
        }
        (output / "result.json").write_bytes(_canonical(result) + b"\n")
        (output / "report.md").write_text(render_report(result), encoding="utf-8")
        return result
    except Exception as exc:
        failure = {
            "schema": RESULT_SCHEMA,
            "status": "FAILED",
            "job_id": request["job_id"],
            "symbol": request["symbol"],
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
            "execution_authorized": False,
        }
        (output / "failure.json").write_bytes(_canonical(failure) + b"\n")
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = run(args.request, args.output)
    except Exception as exc:
        print(f"ASSISTANT_RESEARCH_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "job_id": result["job_id"],
                      "symbol": result["symbol"], "sessions": result["summary"]["sessions"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
