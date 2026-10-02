"""Auditable raw-price datasets; no credentials are returned with market data.

CSV import is a declaration by its supplier, not verification by an exchange.
Unknown execution fields stay unknown. The first Tushare adapter deliberately
supports research only: four endpoints do not prove a corporate-action history.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, DecimalException, InvalidOperation
import hashlib
import io
import json
import math
import os
import re
import urllib.error
import urllib.request


REQUIRED = ("symbol", "date", "open", "high", "low", "close", "volume_shares")
OPTIONAL = ("suspended", "up_limit", "down_limit", "adj_factor", "corporate_action")
FIELDS = REQUIRED + OPTIONAL
MAX_ROWS = 10000
API_URL = "https://api.tushare.pro"
MAINBOARD = re.compile(r"(?:(?:600|601|603|605)[0-9]{3}\.SH|(?:000|001|002|003)[0-9]{3}\.SZ)\Z")


def is_mainboard_symbol(symbol: object) -> bool:
    """Validate supported code ranges, not issuer identity or listing status."""
    return isinstance(symbol, str) and MAINBOARD.fullmatch(symbol) is not None


def _date(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("日期必须是 YYYY-MM-DD，不能带时间或时区")
    try:
        result = date.fromisoformat(value)
    except ValueError:
        raise ValueError("日期不存在") from None
    if result > datetime.now(timezone(timedelta(hours=8))).date():
        raise ValueError("不接受未来日期的历史行情或日历")
    return result.isoformat()


def _number(value: str, field: str, *, optional: bool = False) -> float | int | None:
    if optional and value == "":
        return None
    if not isinstance(value, str) or len(value) > 100 or not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value):
        raise ValueError(f"{field} 必须是有限数值")
    try:
        number = Decimal(value)
        if not number.is_finite() or number < 0 or number > Decimal("1000000000000000"):
            raise ValueError(f"{field} 超出允许范围")
        if field == "volume_shares":
            if number != number.to_integral_value():
                raise ValueError("volume_shares 必须是非负整数股数")
            return int(number)
        if number <= 0:
            raise ValueError(f"{field} 必须大于零")
        if field in ("open", "high", "low", "close", "up_limit", "down_limit") and number * 100 != (number * 100).to_integral_value():
            raise ValueError(f"{field} 必须精确到人民币分，不能包含分以下价格")
        result = float(number)
        if not math.isfinite(result) or result <= 0:
            raise ValueError(f"{field} 超出可表示的正数范围")
        return result
    except (InvalidOperation, OverflowError):
        raise ValueError(f"{field} 必须是有限数值") from None


def _boolean(value: str, field: str) -> bool | None:
    if value == "":
        return None
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    raise ValueError(f"{field} 只能填写 true/false；空值保留未知")


def _csv_rows(text: str) -> list[list[str]]:
    if not isinstance(text, str) or len(text.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("CSV 必须为不超过 2 MiB 的文本")
    try:
        return list(csv.reader(io.StringIO(text.lstrip("\ufeff"), newline=""), strict=True))
    except csv.Error:
        raise ValueError("CSV 格式错误：请检查引号与分隔符") from None


def _calendar(text: str) -> list[str]:
    if not text:
        return []
    rows = _csv_rows(text)
    if rows and rows[0] == ["date"]:
        rows = rows[1:]
    result: list[str] = []
    for row in rows:
        if len(row) != 1:
            raise ValueError("交易日历每行必须只有一个日期，可带 date 表头")
        day = _date(row[0].strip())
        if result and day <= result[-1]:
            raise ValueError("交易日历必须严格递增，不能重复")
        result.append(day)
    if len(result) > MAX_ROWS:
        raise ValueError("交易日历行数过多")
    return result


def _issue(code: str, message: str, bar: dict | None = None) -> dict:
    item = {"code": code, "message": message}
    if bar:
        item.update({key: bar[key] for key in ("symbol", "date") if key in bar})
    return item


def _audit(bars: list[dict], calendar: list[str]) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    blockers: list[dict] = []
    if not calendar:
        blockers.append(_issue("calendar_missing", "没有独立交易日历，不能排除漏行或执行回测"))
    sessions = set(calendar)
    groups: dict[str, list[dict]] = {}
    for bar in bars:
        groups.setdefault(bar["symbol"], []).append(bar)
        if calendar and bar["date"] not in sessions:
            errors.append(_issue("date_outside_calendar", "行情日期不在声明的开市日历中", bar))
        for field in OPTIONAL:
            if bar[field] is None:
                blockers.append(_issue(f"unknown_{field}", f"{field} 未知，不得假定可交易", bar))
        if bar["corporate_action"] is True:
            blockers.append(_issue("corporate_action_unsupported", "第一版不处理公司行动，不能在该区间执行", bar))
        if bar["suspended"] is True and bar["volume_shares"] != 0:
            errors.append(_issue("suspension_volume_conflict", "停牌日成交量必须为零", bar))
        if bar["volume_shares"] == 0 and bar["suspended"] is not True:
            warnings.append(_issue("zero_volume", "成交量为零；该日不能模拟成交", bar))
        upper, lower = bar["up_limit"], bar["down_limit"]
        if upper is not None and lower is not None and lower >= upper:
            errors.append(_issue("invalid_price_limits", "跌停价必须低于涨停价；特殊交易机制暂不支持", bar))
        if upper is not None and bar["high"] > upper + 1e-8:
            errors.append(_issue("high_above_limit", "最高价高于声明的涨停价", bar))
        if lower is not None and bar["low"] < lower - 1e-8:
            errors.append(_issue("low_below_limit", "最低价低于声明的跌停价", bar))
    for symbol, rows in groups.items():
        days = {bar["date"] for bar in rows}
        for day in calendar:
            if rows[0]["date"] <= day <= rows[-1]["date"] and day not in days:
                errors.append(_issue("missing_session", "开市日缺少行情，不能自动视为停牌或填充", {"symbol": symbol, "date": day}))
        known_factors = {bar["adj_factor"] for bar in rows if bar["adj_factor"] is not None}
        if len(known_factors) > 1:
            blockers.append(_issue("adjustment_factor_changed", "复权因子变化，第一版不能模拟该区间的公司行动", {"symbol": symbol}))
    warnings.append(_issue("supplier_declaration", "来源、未复权价格和股数单位为供应方声明；未独立验证证券身份或日历完整性"))
    blockers = errors + blockers
    return {"errors": errors, "warnings": warnings, "backtest_blockers": blockers, "backtest_ready": not blockers}


def _identity(dataset: dict) -> str:
    meta = {key: value for key, value in dataset["meta"].items() if key != "retrieved_at"}
    canonical = {"meta": meta, "bars": dataset["bars"], "calendar": dataset["calendar"]}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def dataset_identity(dataset: dict) -> str:
    """Recompute content identity for engine/ledger integrity checks.

    Does not validate economics; execution modules still validate their window.
    """
    try:
        return _identity(dataset)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("数据集结构或数值无效，无法验证内容指纹") from None


def verify_dataset_identity(dataset: dict) -> None:
    """Reject changed content or missing/malformed identities before use."""
    if not isinstance(dataset, dict) or not isinstance(dataset.get("id"), str) or not re.fullmatch(r"[0-9a-f]{64}", dataset["id"]):
        raise ValueError("数据集缺少有效 SHA-256 内容指纹")
    if dataset["id"] != dataset_identity(dataset):
        raise ValueError("数据集内容与指纹不一致，拒绝使用已变更的数据")


def parse_csv(csv_text: str, *, source: str, calendar_csv: str = "") -> dict:
    """Read declared CNY/raw/share CSV, rejecting malformed rows atomically.

    Structural/value errors raise ValueError. Missing execution metadata and
    calendar gaps remain inspectable in audit, and block backtesting.
    """
    if not isinstance(source, str) or not source.strip() or len(source) > 500 or any(ord(c) < 32 for c in source):
        raise ValueError("请填写 1–500 字符的数据来源，不能包含控制字符")
    rows = _csv_rows(csv_text)
    if not rows:
        raise ValueError("CSV 为空")
    header = [field.strip() for field in rows[0]]
    if len(set(header)) != len(header):
        raise ValueError("CSV 表头不能重复")
    missing = set(REQUIRED) - set(header)
    if missing:
        raise ValueError("CSV 缺少必填列：" + ", ".join(sorted(missing)))
    unknown = set(header) - set(FIELDS)
    if unknown:
        raise ValueError("CSV 包含未支持的列：" + ", ".join(sorted(unknown)))
    if not 1 <= len(rows) - 1 <= MAX_ROWS:
        raise ValueError(f"CSV 必须包含 1–{MAX_ROWS} 行行情")
    bars: list[dict] = []
    previous: dict[str, str] = {}
    for line, row in enumerate(rows[1:], start=2):
        if len(row) != len(header):
            raise ValueError(f"CSV 第 {line} 行列数与表头不一致")
        values = {key: value.strip() for key, value in zip(header, row)}
        symbol = values["symbol"]
        if not is_mainboard_symbol(symbol):
            raise ValueError(f"CSV 第 {line} 行不是支持的沪深主板代码格式")
        day = _date(values["date"])
        if symbol in previous and day <= previous[symbol]:
            raise ValueError(f"{symbol} 行情日期必须严格递增，不能重复")
        previous[symbol] = day
        bar = {"symbol": symbol, "date": day}
        for field in ("open", "high", "low", "close", "volume_shares"):
            bar[field] = _number(values[field], field)
        for field in ("up_limit", "down_limit", "adj_factor"):
            bar[field] = _number(values.get(field, ""), field, optional=True)
        for field in ("suspended", "corporate_action"):
            bar[field] = _boolean(values.get(field, ""), field)
        if not bar["low"] <= min(bar["open"], bar["close"]) <= max(bar["open"], bar["close"]) <= bar["high"]:
            raise ValueError(f"CSV 第 {line} 行 OHLC 高低关系不成立")
        bars.append(bar)
    bars.sort(key=lambda bar: (bar["date"], bar["symbol"]))
    calendar = _calendar(calendar_csv)
    dataset = {
        "meta": {"source": source.strip(), "source_kind": "csv", "currency": "CNY", "price_basis": "raw", "volume_unit": "shares", "retrieved_at": datetime.now(timezone.utc).isoformat(), "calendar_source": source.strip() + " / 用户提供的开市日历" if calendar else "missing", "schema_version": 1},
        "bars": bars, "calendar": calendar, "audit": _audit(bars, calendar),
    }
    dataset["id"] = _identity(dataset)
    return dataset


def demo_dataset() -> dict:
    """140 synthetic weekday sessions, two code-shaped labels, no real prices."""
    days: list[str] = []
    day = date(2024, 1, 2)
    while len(days) < 140:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += timedelta(days=1)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for symbol, base, phase in (("600000.SH", 12, 0), ("000001.SZ", 20, 1.4)):
        previous = base
        for index, day in enumerate(days):
            close = round(base + 0.018 * index + 1.35 * math.sin(index / 8 + phase), 2)
            opening = round(previous * (1 + 0.003 * math.sin(index / 3 + phase)), 2)
            row = {"symbol": symbol, "date": day, "open": opening, "high": round(max(opening, close) + 0.18, 2), "low": round(min(opening, close) - 0.18, 2), "close": close, "volume_shares": 1500000 + 2500 * index, "suspended": "false", "up_limit": round(previous * 1.1, 2), "down_limit": round(previous * 0.9, 2), "adj_factor": 1, "corporate_action": "false"}
            # These are fabricated execution bounds, not a universal board rule.
            row["up_limit"] = max(row["up_limit"], row["high"] + 0.01)
            row["down_limit"] = min(row["down_limit"], row["low"] - 0.01)
            writer.writerow(row)
            previous = close
    dataset = parse_csv(output.getvalue(), source="合成演示 v1：所有价格和日历均为虚构，代码仅作格式示例", calendar_csv="date\n" + "\n".join(days))
    dataset["meta"]["source_kind"] = "demo"
    dataset["meta"]["calendar_source"] = "合成工作日日历；未排除中国节假日，不是真实交易日历"
    dataset["audit"]["warnings"] = [_issue("synthetic_demo", "全部行情、成交量、涨跌停价与日历均为确定性合成，仅供功能演示")]
    dataset["id"] = _identity(dataset)
    return dataset


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("拒绝数据源重定向；凭据仅发送至官方 HTTPS API")


def _transport(payload: dict) -> dict:
    """Single official HTTPS request. Mock this function in adapter tests."""
    request = urllib.request.Request(API_URL, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    try:
        opener = urllib.request.build_opener(_NoRedirect())
        with opener.open(request, timeout=20) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError("Tushare 响应过大")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Tushare 返回结构无效")
        return result
    except (urllib.error.URLError, OSError, UnicodeError, json.JSONDecodeError):
        # Never echo request/response/error text, which could contain a token.
        raise ValueError("Tushare 官方 HTTPS 请求失败；请检查网络和账户配置") from None


def _api(name: str, params: dict, fields: str, token: str) -> list[dict]:
    try:
        response = _transport({"api_name": name, "token": token, "params": params, "fields": fields})
    except Exception:
        raise ValueError(f"Tushare {name} 请求未成功，未使用替代或伪造数据") from None
    if not isinstance(response, dict) or type(response.get("code")) is not int or response["code"] != 0:
        raise ValueError(f"Tushare {name} 未授权、额度不足或服务拒绝；请检查官方账户权限")
    data = response.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("fields"), list) or not isinstance(data.get("items"), list):
        raise ValueError(f"Tushare {name} 响应缺少 fields/items")
    columns = data["fields"]
    if not all(isinstance(field, str) for field in columns) or len(set(columns)) != len(columns) or not set(fields.split(",")).issubset(columns):
        raise ValueError(f"Tushare {name} 响应缺少必需字段或表头重复")
    if len(data["items"]) > MAX_ROWS:
        raise ValueError(f"Tushare {name} 返回行数超限")
    result = []
    for row in data["items"]:
        if not isinstance(row, list) or len(row) != len(columns):
            raise ValueError(f"Tushare {name} 响应行列数不一致")
        result.append(dict(zip(columns, row)))
    return result


def _api_day(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{8}", value):
        raise ValueError("Tushare 返回无效日期")
    return _date(value[:4] + "-" + value[4:6] + "-" + value[6:])


def _index_api(rows: list[dict], symbol: str, start: str, end: str) -> dict[str, dict]:
    result = {}
    for row in rows:
        if row.get("ts_code") != symbol:
            raise ValueError("Tushare 返回了非请求证券的数据")
        day = _api_day(row.get("trade_date"))
        if not start <= day <= end or day in result:
            raise ValueError("Tushare 返回日期越界或重复行")
        result[day] = row
    return result



def akshare_available() -> bool:
    """Return whether the optional AKShare research connector is installed."""
    try:
        import importlib.util
        return importlib.util.find_spec("akshare") is not None
    except (ImportError, ValueError):
        return False


def _akshare_day(value: object) -> str:
    if isinstance(value, datetime):
        return _date(value.date().isoformat())
    if isinstance(value, date):
        return _date(value.isoformat())
    text = str(value)
    if len(text) < 10 or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text[:10]):
        raise ValueError("AKShare 返回无效交易日期")
    return _date(text[:10])


def _akshare_records(frame: object, required: set[str], label: str) -> list[dict]:
    columns = getattr(frame, "columns", None)
    to_dict = getattr(frame, "to_dict", None)
    if columns is None or not callable(to_dict):
        raise ValueError(f"AKShare {label} 返回结构无效")
    names = [str(name) for name in columns]
    if not required.issubset(set(names)):
        raise ValueError(f"AKShare {label} 缺少必要字段")
    try:
        rows = to_dict(orient="records")
    except Exception:
        raise ValueError(f"AKShare {label} 无法转换为记录") from None
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError(f"AKShare {label} 返回行数无效")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"AKShare {label} 返回记录格式无效")
    return rows


def fetch_akshare(symbol: str, start: str, end: str, *, client=None) -> dict:
    """Fetch real, unadjusted A-share daily bars through AKShare for research.

    AKShare is an optional connector. It supplies real historical OHLCV and a
    market calendar, but does not by itself prove suspension, corporate-action,
    risk-warning, survivorship, or point-in-time feature completeness. Those
    unknowns intentionally remain blockers for simulated execution.
    """
    if not is_mainboard_symbol(symbol):
        raise ValueError("仅支持单只沪深主板股票的标准代码")
    start, end = _date(start), _date(end)
    if start > end or (date.fromisoformat(end) - date.fromisoformat(start)).days > 365:
        raise ValueError("一次最多获取 366 个自然日，且起始日不能晚于结束日")
    if client is None:
        try:
            import akshare as client
        except ImportError:
            raise ValueError('未安装 AKShare 数据组件；请先运行 py -m pip install -e ".[market]"') from None

    code = symbol.split(".")[0]
    try:
        hist_frame = client.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start.replace("-", ""),
            end_date=end.replace("-", ""),
            adjust="",
        )
    except Exception:
        raise ValueError("AKShare 历史行情请求失败；未使用替代或伪造数据") from None

    rows = _akshare_records(
        hist_frame,
        {"日期", "开盘", "收盘", "最高", "最低", "成交量"},
        "stock_zh_a_hist",
    )
    if not rows:
        raise ValueError("AKShare 没有返回该区间行情，未生成替代数据")

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    seen_days: set[str] = set()
    for row in rows:
        day = _akshare_day(row.get("日期"))
        if not start <= day <= end or day in seen_days:
            raise ValueError("AKShare 返回日期越界或重复行")
        seen_days.add(day)
        provider_code = row.get("股票代码")
        if provider_code not in (None, "") and str(provider_code).zfill(6) != code:
            raise ValueError("AKShare 返回了非请求证券的数据")
        try:
            hands = Decimal(str(row.get("成交量")))
            shares = hands * 100
            if not shares.is_finite() or shares < 0 or shares != shares.to_integral_value():
                raise ValueError("AKShare 成交量不能精确转换为整数股数")
        except (DecimalException, ValueError):
            raise ValueError("AKShare 成交量无效") from None
        writer.writerow({
            "symbol": symbol,
            "date": day,
            "open": row.get("开盘"),
            "high": row.get("最高"),
            "low": row.get("最低"),
            "close": row.get("收盘"),
            "volume_shares": str(shares),
            "suspended": "",
            "up_limit": "",
            "down_limit": "",
            "adj_factor": "",
            "corporate_action": "",
        })

    calendar: list[str] = []
    calendar_error: str | None = None
    try:
        cal_frame = client.tool_trade_date_hist_sina()
        cal_rows = _akshare_records(cal_frame, {"trade_date"}, "tool_trade_date_hist_sina")
        calendar = sorted({
            _akshare_day(row.get("trade_date"))
            for row in cal_rows
            if start <= _akshare_day(row.get("trade_date")) <= end
        })
        if not calendar or calendar[0] > min(seen_days) or calendar[-1] < max(seen_days):
            raise ValueError("AKShare 交易日历未覆盖行情区间")
    except Exception:
        calendar = []
        calendar_error = "AKShare 交易日历不可用或覆盖不完整"

    version = str(getattr(client, "__version__", "unknown"))
    source = f"AKShare {version} / stock_zh_a_hist + tool_trade_date_hist_sina"
    dataset = parse_csv(
        output.getvalue(),
        source=source,
        calendar_csv="date\n" + "\n".join(calendar) if calendar else "",
    )
    dataset["meta"].update({
        "source_kind": "akshare",
        "calendar_source": "AKShare tool_trade_date_hist_sina / Sina Finance" if calendar else "missing",
        "requested_start": start,
        "requested_end": end,
        "provider_volume_unit": "hands (100 shares)",
        "provider_price_adjustment": "none",
        "adapter_version": 1,
        "provider_library_license": "MIT",
        "provider_data_use_note": "AKShare states its data is for academic/research reference; upstream source terms still apply",
    })
    dataset["audit"]["warnings"].append(_issue(
        "akshare_research_only",
        "AKShare 提供真实历史行情用于研究，但上游接口可能变化；当前不把它视为交易所官方执行事实",
    ))
    dataset["audit"]["warnings"].append(_issue(
        "provider_execution_metadata_pending",
        "停牌、公司行动、风险警示、逐日涨跌停与 PIT 身份仍未完整验证；真实数据仅供研究，禁止模拟成交",
    ))
    if calendar_error:
        item = _issue("provider_calendar_incomplete", calendar_error)
        dataset["audit"]["warnings"].append(item)
        dataset["audit"]["backtest_blockers"].append(item)
    dataset["audit"]["backtest_ready"] = not dataset["audit"]["backtest_blockers"]
    dataset["id"] = _identity(dataset)
    return dataset


def fetch_tushare(symbol: str, start: str, end: str, *, token: str | None = None) -> dict:
    """Official four-endpoint adapter; unknown flags block execution.

    Public server calls never accept a token. The keyword is only for trusted
    programmatic tests; normal use reads TUSHARE_TOKEN from the environment.
    """
    if not is_mainboard_symbol(symbol):
        raise ValueError("仅支持单只沪深主板股票的标准代码")
    start, end = _date(start), _date(end)
    if start > end or (date.fromisoformat(end) - date.fromisoformat(start)).days > 365:
        raise ValueError("一次最多获取 366 个自然日，且起始日不能晚于结束日")
    credential = token if token is not None else os.environ.get("TUSHARE_TOKEN", "")
    if not isinstance(credential, str) or not credential.strip():
        raise ValueError("尚未配置服务端 TUSHARE_TOKEN；真实在线数据验证待完成")
    params = {"ts_code": symbol, "start_date": start.replace("-", ""), "end_date": end.replace("-", "")}
    daily = _index_api(_api("daily", params, "ts_code,trade_date,open,high,low,close,vol", credential), symbol, start, end)
    if not daily:
        raise ValueError("Tushare 没有返回该区间行情，未生成替代数据")
    optional_errors = []
    supplemental = {}
    for name, fields in (("adj_factor", "ts_code,trade_date,adj_factor"), ("stk_limit", "ts_code,trade_date,up_limit,down_limit")):
        try:
            supplemental[name] = _index_api(_api(name, params, fields, credential), symbol, start, end)
        except ValueError as error:
            supplemental[name] = {}
            optional_errors.append(_issue("provider_incomplete", str(error)))
    exchange = "SSE" if symbol.endswith(".SH") else "SZSE"
    cal_params = {"exchange": exchange, "start_date": params["start_date"], "end_date": params["end_date"]}
    calendar = []
    try:
        seen = set()
        for row in _api("trade_cal", cal_params, "exchange,cal_date,is_open", credential):
            day = _api_day(row.get("cal_date"))
            if row.get("exchange") != exchange or not start <= day <= end or day in seen:
                raise ValueError("Tushare 交易日历交易所、区间或唯一性不匹配")
            seen.add(day)
            open_flag = row.get("is_open")
            if not ((type(open_flag) is int and open_flag in (0, 1)) or (type(open_flag) is str and open_flag in ("0", "1"))):
                raise ValueError("Tushare 交易日历缺少明确开市状态")
            if open_flag in (1, "1"):
                calendar.append(day)
        expected_days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
        if len(seen) != expected_days:
            raise ValueError("Tushare 交易日历未覆盖请求区间的每个自然日")
        calendar.sort()
    except ValueError as error:
        calendar = []
        optional_errors.append(_issue("provider_calendar_incomplete", str(error)))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for day, row in sorted(daily.items()):
        if isinstance(row.get("vol"), bool) or row.get("vol") is None:
            raise ValueError("Tushare vol 缺失或类型无效")
        try:
            shares = Decimal(str(row["vol"])) * 100
            if not shares.is_finite() or shares < 0 or shares != shares.to_integral_value():
                raise ValueError("Tushare 成交量不能精确转换为整数股数")
        except DecimalException:
            raise ValueError("Tushare 成交量无效") from None
        factors = supplemental["adj_factor"].get(day, {})
        limits = supplemental["stk_limit"].get(day, {})
        normalized = {key: row[key] for key in ("open", "high", "low", "close")}
        normalized.update({"symbol": symbol, "date": day, "volume_shares": str(shares), "adj_factor": factors.get("adj_factor"), "up_limit": limits.get("up_limit"), "down_limit": limits.get("down_limit"), "suspended": "", "corporate_action": ""})
        writer.writerow(normalized)
    dataset = parse_csv(output.getvalue(), source="Tushare Pro 官方 API / daily+adj_factor+stk_limit+trade_cal", calendar_csv="date\n" + "\n".join(calendar) if calendar else "")
    dataset["meta"].update({"source_kind": "tushare", "calendar_source": f"Tushare trade_cal {exchange}" if calendar else "missing", "requested_start": start, "requested_end": end, "provider_volume_unit": "hands (100 shares)", "adapter_version": 1})
    if calendar:
        for day in calendar:
            if day not in daily and not any(item.get("date") == day and item["code"] == "missing_session" for item in dataset["audit"]["errors"]):
                item = _issue("missing_session", "请求区间开市日没有行情，未猜测为停牌或未上市", {"symbol": symbol, "date": day})
                dataset["audit"]["errors"].append(item)
                dataset["audit"]["backtest_blockers"].append(item)
    dataset["audit"]["warnings"].append(_issue("provider_execution_metadata_pending", "四个官方接口不能完整证明停牌与公司行动状态；保持未知，真实数据仅供研究，禁止模拟成交"))
    dataset["audit"]["warnings"].extend(optional_errors)
    dataset["audit"]["backtest_blockers"].extend(optional_errors)
    dataset["audit"]["backtest_ready"] = not dataset["audit"]["backtest_blockers"]
    dataset["id"] = _identity(dataset)
    return dataset
