"use strict";

(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const state = {config: null, dataset: null, datasets: [], accountId: "", accountGeneration: 0};
  const moneyFormatter = new Intl.NumberFormat("zh-CN", {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const numberFormatter = new Intl.NumberFormat("zh-CN", {maximumFractionDigits: 2});
  const feeFields = [
    {key: "commission_rate", label: "佣金费率（小数）", value: 0.0003, step: "0.00001", max: "0.02"},
    {key: "min_commission", label: "最低佣金（元）", value: 5, step: "0.01", max: "1000"},
    {key: "stamp_tax_rate", label: "卖出印花税率（小数）", value: 0.0005, step: "0.00001", max: "0.02"},
    {key: "transfer_fee_rate", label: "过户费率（小数）", value: 0.00001, step: "0.000001", max: "0.02"},
    {key: "slippage_bps", label: "滑点（基点，1 = 0.01%）", value: 5, step: "0.1", max: "1000"}
  ];

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function finite(value) { return typeof value === "number" && Number.isFinite(value); }
  function money(value) { return finite(value) ? moneyFormatter.format(value) : "—"; }
  function number(value) { return finite(value) ? numberFormatter.format(value) : "—"; }
  function percent(value) { return finite(value) ? `${(value * 100).toFixed(2)}%` : "—"; }
  function sideLabel(value) { return value === "BUY" ? "买入" : value === "SELL" ? "卖出" : String(value ?? "—"); }
  function stamp(value) {
    if (!value) return "未提供";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString("zh-CN", {hour12: false});
  }
  function textMessage(item) {
    if (typeof item === "string") return item;
    if (!item || typeof item !== "object") return String(item ?? "");
    const prefix = [item.symbol, item.date].filter(Boolean).join(" · ");
    return `${prefix ? `${prefix}：` : ""}${item.message || item.reason || item.code || JSON.stringify(item)}`;
  }
  function showMessage(text, isError = false) {
    const node = $("#message");
    node.textContent = text;
    node.classList.remove("hidden");
    node.classList.toggle("error", isError);
    node.setAttribute("role", isError ? "alert" : "status");
    if (isError) node.focus();
  }
  function clearMessage() { $("#message").classList.add("hidden"); }
  function updateDatasetControls() {
    $$("[data-requires-dataset]").forEach(button => { button.disabled = !state.dataset; });
    $("#export-data").disabled = !state.dataset;
    $("#record-trade").disabled = !state.dataset || !state.accountId;
  }
  async function api(path, payload) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 90000);
    try {
      const options = {credentials: "same-origin", signal: controller.signal, headers: {Accept: "application/json"}};
      if (payload !== undefined) {
        if (!state.config?.csrf_token) throw new Error("服务配置尚未加载，请刷新页面后重试。");
        options.method = "POST";
        options.headers["Content-Type"] = "application/json";
        options.headers["X-Invest-CSRF"] = state.config.csrf_token;
        options.body = JSON.stringify(payload);
        if (new TextEncoder().encode(options.body).length > 2 * 1024 * 1024) throw new Error("请求超过 2 MiB，请缩小导入文件或数据区间。");
      }
      const response = await fetch(path, options);
      let result;
      try { result = await response.json(); } catch (_) { throw new Error(`服务响应无法解析（HTTP ${response.status}），请检查本地服务。`); }
      if (!response.ok) throw new Error(typeof result.error === "string" ? result.error : `操作失败（HTTP ${response.status}）。`);
      return result;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("请求超时，请先刷新查看操作是否已保存，再决定是否重试。");
      if (error instanceof TypeError) throw new Error("无法连接本地服务。请确认服务仍在运行；提交过交易时，请先刷新账本核对结果。");
      throw error;
    } finally { clearTimeout(timer); }
  }
  async function busy(button, action) {
    if (button.dataset.busy === "true") return;
    const previous = button.textContent;
    button.dataset.busy = "true";
    button.disabled = true;
    button.textContent = "处理中…";
    clearMessage();
    try { await action(); }
    catch (error) { showMessage(error.message || "操作未完成，请检查输入。", true); }
    finally {
      button.textContent = previous;
      button.dataset.busy = "false";
      button.disabled = false;
      updateDatasetControls();
      $("#fetch-tushare").disabled = !state.config?.tushare_configured;
    }
  }
  function switchTab(name, focus = false) {
    $$("[data-tab]").forEach(button => {
      const active = button.dataset.tab === name;
      button.setAttribute("aria-selected", String(active));
      button.tabIndex = active ? 0 : -1;
      $(`#panel-${button.dataset.tab}`).hidden = !active;
      if (active && focus) button.focus();
    });
  }
  function listItems(node, values, fallback) {
    node.replaceChildren();
    const list = Array.isArray(values) ? values : [];
    (list.length ? list : fallback ? [fallback] : []).forEach(item => node.append(el("li", "", textMessage(item))));
  }
  function metric(label, value, note = "") {
    const node = el("div", "metric");
    const valueNode = el("strong", "metric-value", value);
    if (/^\d{4}-\d{2}-\d{2}$/.test(String(value))) valueNode.classList.add("metric-date");
    node.append(el("span", "metric-label", label), valueNode);
    if (note) node.append(el("span", "metric-note", note));
    return node;
  }
  function option(value, text) {
    const node = el("option", "", text);
    node.value = String(value ?? "");
    return node;
  }
  function datasetLabel(dataset) {
    const meta = dataset.meta || {};
    const prefix = meta.source_kind === "demo" ? "[合成示例] " : "";
    return `${prefix}${meta.source || "未标注来源"} · ${dataset.start || ""}${dataset.end ? ` — ${dataset.end}` : ""}`;
  }
  function symbolsOf(dataset) { return [...new Set((dataset?.bars || []).map(bar => bar.symbol))].sort(); }
  function rememberDataset(id) { try { localStorage.setItem("invest.lastDataset", id); } catch (_) { /* Browser storage is optional. */ } }
  function recalledDataset() { try { return localStorage.getItem("invest.lastDataset"); } catch (_) { return null; } }
  async function refreshDatasetList(selectedId) {
    const response = await api("/api/datasets");
    state.datasets = Array.isArray(response.datasets) ? response.datasets : [];
    const select = $("#dataset-select");
    select.replaceChildren();
    if (!state.datasets.length) select.append(option("", "尚未载入数据"));
    else state.datasets.forEach(dataset => select.append(option(dataset.id, datasetLabel(dataset))));
    if (selectedId && state.datasets.some(item => item.id === selectedId)) select.value = selectedId;
  }
  async function selectDataset(dataset) {
    if (!dataset || !dataset.id || !Array.isArray(dataset.bars)) throw new Error("服务返回的数据集格式不完整。");
    state.dataset = dataset;
    rememberDataset(dataset.id);
    $("#dataset-select").value = dataset.id;
    renderProvenance(dataset);
    renderAudit(dataset.audit || {});
    const symbols = symbolsOf(dataset);
    $$("[data-symbol-select]").forEach(select => {
      const previous = select.value;
      select.replaceChildren(...symbols.map(symbol => option(symbol, symbol)));
      if (!symbols.length) select.append(option("", "数据中没有标的"));
      if (symbols.includes(previous)) select.value = previous;
    });
    const dates = (dataset.bars || []).map(bar => bar.date).filter(Boolean).sort();
    if (dates.length) {
      [$("#start-date"), $("#end-date"), $("#paper-date")].forEach(input => { input.min = dates[0]; input.max = dates[dates.length - 1]; });
      $("#start-date").value = "";
      $("#end-date").value = "";
      $("#paper-date").value = dates[dates.length - 1];
    }
    $("#backtest-empty").classList.remove("hidden");
    $("#backtest-results").classList.add("hidden");
    $("#backtest-records").classList.add("hidden");
    $("#research-empty").classList.add("hidden");
    $("#research-content").classList.remove("hidden");
    $("#research-cards").replaceChildren(el("p", "muted", "正在计算研究指标…"));
    $("#research-summary").replaceChildren();
    $("#research-limitations").replaceChildren();
    updateDatasetControls();
    const result = await Promise.allSettled([loadResearch(dataset.id), state.accountId ? loadAccount(state.accountId) : Promise.resolve()]);
    const failures = result.filter(item => item.status === "rejected");
    if (failures.length) throw new Error(`数据已载入。${failures.map(item => item.reason.message).join("；")}`);
  }
  function renderProvenance(dataset) {
    const meta = dataset.meta || {};
    $("#demo-notice").classList.toggle("hidden", meta.source_kind !== "demo");
    const node = $("#provenance");
    node.classList.remove("hidden");
    node.replaceChildren();
    [["来源", meta.source || "未提供"], ["载入时间", stamp(meta.retrieved_at)], ["日历", meta.calendar_source || "未提供"], ["口径", "CNY · 未复权 · 股"], ["数据标识", dataset.id.slice(0, 12)]].forEach(([label, value]) => {
      const item = el("span", "", label);
      item.append(el("strong", "", value));
      if (label === "数据标识") item.title = dataset.id;
      node.append(item);
    });
  }
  function renderAudit(audit) {
    $("#audit-badge").textContent = audit.backtest_ready ? "满足回测数据检查" : "存在执行限制";
    const node = $("#audit-content");
    node.replaceChildren();
    const groups = [["errors", "错误", "error"], ["backtest_blockers", "阻止回测的原因", "error"], ["warnings", "警告与待核实项", "warning"]];
    let count = 0;
    groups.forEach(([key, title, className]) => {
      if (!Array.isArray(audit[key]) || !audit[key].length) return;
      count += audit[key].length;
      const group = el("div", `audit-group ${className}`);
      group.append(el("h4", "", `${title} · ${audit[key].length}`));
      const list = el("ul", "plain-list");
      listItems(list, audit[key]);
      group.append(list);
      node.append(group);
    });
    if (!count) node.append(el("p", "audit-pass", "当前数据检查未发现阻止项；具体交易区间仍会由回测引擎再次校验。"));
  }
  async function loadResearch(datasetId) {
    try {
      const result = await api(`/api/research?dataset_id=${encodeURIComponent(datasetId)}`);
      if (state.dataset?.id !== datasetId) return;
      renderResearch(result);
    } catch (error) {
      if (state.dataset?.id === datasetId) $("#research-cards").replaceChildren(el("p", "info-note", `研究计算未完成：${error.message}`));
      throw error;
    }
  }
  function renderResearch(result) {
    const symbols = Array.isArray(result.symbols) ? result.symbols : [];
    const dataset = state.dataset;
    const summary = $("#research-summary");
    summary.replaceChildren(
      metric("研究标的", String(symbols.length), "沪深 A 股主板"),
      metric("行情记录", number(dataset.bars.length), "逐标的 · 日频"),
      metric("数据截止", result.as_of || "—", "历史数据时间"),
      metric("执行检查", dataset.audit?.backtest_ready ? "可验证" : "有限制", "详细原因见数据管理")
    );
    const container = $("#research-cards");
    container.replaceChildren();
    symbols.forEach(item => {
      const card = el("article", "card research-card");
      const heading = el("div", "card-heading");
      heading.append(el("h3", "symbol-heading", item.symbol), el("span", "subtle-badge", `${item.bars ?? "—"} 条日线`));
      card.append(heading);
      const metrics = el("div", "metrics-inline");
      [["最新收盘价（元）", money(item.last_close)], ["20 日区间涨跌", percent(item.return_20d)], ["历史最大回撤", percent(item.max_drawdown)]].forEach(([label, value]) => {
        const column = el("div");
        column.append(el("span", "", label), el("strong", "", value));
        metrics.append(column);
      });
      card.append(metrics, el("p", "body-copy", `20 日波动指标：${percent(item.volatility_20d)} · 趋势描述：${item.trend ?? "数据不足"}`));
      card.append(el("h4", "", "数据事实"));
      const facts = el("ul", "plain-list");
      listItems(facts, item.facts, "当前区间暂无可计算事实。");
      card.append(facts);
      const counter = el("div", "counterarguments");
      counter.append(el("h4", "", "反证与局限"));
      const argumentsList = el("ul", "plain-list");
      listItems(argumentsList, [...(item.counterarguments || []), ...(item.warnings || [])], "历史走势无法确定未来回报；还需核实公司与市场信息。");
      counter.append(argumentsList);
      card.append(counter);
      container.append(card);
    });
    if (!symbols.length) container.append(el("p", "info-note", "当前数据暂无可分析标的，请检查数据管理中的错误信息。"));
    listItems($("#research-limitations"), result.limitations, "仅基于已载入日线进行算术汇总，未分析财务、公告或实时行情。");
  }
  function buildFees() {
    $$("[data-fee-fields]").forEach(group => {
      feeFields.forEach(field => {
        const wrapper = el("div");
        const id = `${group.dataset.feeFields}-${field.key}`;
        const label = el("label", "", field.label);
        label.htmlFor = id;
        const input = el("input");
        Object.assign(input, {id, name: field.key, type: "number", min: "0", max: field.max, step: field.step, required: true, value: String(field.value)});
        wrapper.append(label, input);
        group.append(wrapper);
      });
    });
  }
  function feesFromForm(form) {
    const data = new FormData(form);
    const result = {cost_model_acknowledged: data.get("cost_model_acknowledged") === "on"};
    feeFields.forEach(field => { result[field.key] = Number(data.get(field.key)); });
    return result;
  }
  function renderTable(container, columns, rows, emptyMessage) {
    container.replaceChildren();
    if (!rows?.length) { container.append(el("p", "table-empty", emptyMessage)); return; }
    const table = el("table");
    const thead = el("thead");
    const headRow = el("tr");
    columns.forEach(column => { const th = el("th", "", column.label); th.scope = "col"; headRow.append(th); });
    thead.append(headRow);
    const tbody = el("tbody");
    rows.forEach(row => {
      const tr = el("tr");
      columns.forEach(column => {
        const value = column.format ? column.format(row[column.key], row) : row[column.key];
        tr.append(el("td", column.wrap ? "wrap-cell" : "", value === undefined || value === null || value === "" ? "—" : value));
      });
      tbody.append(tr);
    });
    table.append(thead, tbody);
    container.append(table);
  }
  const tradeColumns = [
    {key: "date", label: "成交日期"}, {key: "signal_date", label: "信号日期"}, {key: "side", label: "方向", format: sideLabel},
    {key: "quantity", label: "股数", format: number}, {key: "price", label: "成交价 / 元", format: money},
    {key: "fees", label: "费用 / 元", format: money}, {key: "cash_after", label: "余款 / 元", format: money}, {key: "reason", label: "理由", wrap: true}
  ];
  function renderBacktest(result, dataset) {
    $("#backtest-empty").classList.add("hidden");
    $("#backtest-results").classList.remove("hidden");
    $("#backtest-records").classList.remove("hidden");
    const prefix = dataset.meta?.source_kind === "demo" ? "合成示例 · 非真实行情 / " : "";
    $("#result-context").textContent = `${prefix}${result.symbol} · 数据 ${String(result.dataset_id || dataset.id).slice(0, 12)} · 本次运行结果`;
    const metrics = result.metrics || {};
    $("#backtest-metrics").replaceChildren(
      metric("策略累计回报", percent(metrics.total_return), "已计执行费用"),
      metric("买入持有回报", percent(metrics.benchmark_return), "同区间成本基准"),
      metric("最大回撤", percent(metrics.max_drawdown), "历史峰值至谷值"),
      metric("期末权益（元）", money(metrics.final_equity), "现金 + 持仓估值"),
      metric("期末持仓（股）", number(metrics.shares), `现金 ${money(metrics.cash)} 元`),
      metric("累计费用（元）", money(metrics.total_fees), "按本次固定费用情景")
    );
    drawCurve(result.curve || [], dataset.meta?.source_kind === "demo");
    const assumptions = [...(result.assumptions || []), ...(result.warnings || [])];
    if (result.parameters) assumptions.push(`本次参数：${Object.entries(result.parameters).map(([key, value]) => `${key}=${value}`).join("；")}`);
    listItems($("#backtest-assumptions"), assumptions);
    renderTable($("#trade-table"), tradeColumns, result.trades || [], "该区间没有成交记录。");
    renderTable($("#rejection-table"), [{key: "date", label: "日期"}, {key: "side", label: "方向", format: sideLabel}, {key: "reason", label: "未成交原因", wrap: true}], result.rejected_orders || [], "本次没有被拒绝的订单。");
  }
  function drawCurve(rows, synthetic) {
    const container = $("#equity-chart");
    container.replaceChildren();
    const validRows = rows.filter(row => finite(row.equity));
    if (!validRows.length) { container.append(el("p", "muted", "没有可绘制的有效净值数据。")); return; }
    const ns = "http://www.w3.org/2000/svg";
    const svgEl = (tag, attributes, text) => {
      const node = document.createElementNS(ns, tag);
      Object.entries(attributes || {}).forEach(([key, value]) => node.setAttribute(key, String(value)));
      if (text !== undefined) node.textContent = text;
      return node;
    };
    const width = 640, height = 270, left = 77, right = 14, top = 16, bottom = 37;
    const values = validRows.flatMap(row => [row.equity, row.benchmark_equity].filter(finite));
    let min = Math.min(...values), max = Math.max(...values);
    const margin = max === min ? Math.max(Math.abs(max) * 0.02, 1) : (max - min) * 0.1;
    min -= margin; max += margin;
    const x = index => validRows.length === 1 ? (left + width - right) / 2 : left + index * (width - left - right) / (validRows.length - 1);
    const y = value => top + (max - value) * (height - top - bottom) / (max - min);
    const svg = svgEl("svg", {viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": `${synthetic ? "合成示例，" : ""}策略与买入持有净值，${validRows[0].date} 至 ${validRows[validRows.length - 1].date}，策略期末 ${money(validRows[validRows.length - 1].equity)} 元。`});
    svg.append(svgEl("title", {}, "账户净值与买入持有基准（人民币）"));
    for (let i = 0; i < 5; i++) {
      const value = min + (max - min) * i / 4;
      svg.append(svgEl("line", {x1: left, y1: y(value), x2: width - right, y2: y(value), stroke: "#e3ebea", "stroke-width": 1}));
      svg.append(svgEl("text", {x: left - 9, y: y(value) + 4, "text-anchor": "end", fill: "#637780", "font-size": 10}, number(value)));
    }
    [["benchmark_equity", "#87979e"], ["equity", "#137765"]].forEach(([key, color]) => {
      let path = "", drawing = false;
      validRows.forEach((row, index) => {
        if (!finite(row[key])) { drawing = false; return; }
        path += `${drawing ? "L" : "M"}${x(index).toFixed(2)},${y(row[key]).toFixed(2)} `;
        drawing = true;
      });
      if (path) svg.append(svgEl("path", {d: path, fill: "none", stroke: color, "stroke-width": key === "equity" ? 2.5 : 1.8, "stroke-linejoin": "round", "stroke-linecap": "round"}));
    });
    const interval = Math.max(1, Math.ceil(validRows.length / 8));
    validRows.forEach((row, index) => {
      if (index % interval !== 0 && index !== validRows.length - 1) return;
      const title = `${row.date}：策略 ${money(row.equity)} 元，基准 ${money(row.benchmark_equity)} 元`;
      const dot = svgEl("circle", {cx: x(index), cy: y(row.equity), r: 3.5, fill: "#137765", stroke: "white", "stroke-width": 1.5, tabindex: "0", role: "img", "aria-label": title});
      dot.append(svgEl("title", {}, title));
      svg.append(dot);
    });
    svg.append(svgEl("text", {x: left, y: height - 10, fill: "#637780", "font-size": 10}, validRows[0].date));
    if (validRows.length > 1) svg.append(svgEl("text", {x: width - right, y: height - 10, "text-anchor": "end", fill: "#637780", "font-size": 10}, validRows[validRows.length - 1].date));
    container.append(svg);
  }
  async function refreshAccounts(preferredId) {
    const result = await api("/api/accounts");
    const accounts = Array.isArray(result.accounts) ? result.accounts : [];
    const select = $("#account-select");
    select.replaceChildren(...accounts.map(account => option(account.id, account.name || account.id)));
    if (!accounts.length) select.append(option("", "尚未创建账户"));
    const chosen = accounts.some(account => String(account.id) === String(preferredId)) ? String(preferredId) : (accounts[0] ? String(accounts[0].id) : "");
    select.value = chosen;
    state.accountId = chosen;
    updateDatasetControls();
    if (chosen) await loadAccount(chosen);
  }
  async function loadAccount(id) {
    if (!id) return;
    const generation = ++state.accountGeneration;
    const query = state.dataset ? `?dataset_id=${encodeURIComponent(state.dataset.id)}` : "";
    const snapshot = await api(`/api/accounts/${encodeURIComponent(id)}${query}`);
    if (generation === state.accountGeneration && state.accountId === String(id)) renderAccount(snapshot);
  }
  function renderAccount(snapshot) {
    const account = snapshot.account || {};
    const node = $("#account-snapshot");
    node.replaceChildren();
    if ((snapshot.trades || []).some(trade => trade.source_kind === "demo")) {
      node.append(el("p", "info-note account-demo-note", "本账户包含合成示例交易。账户余额与持仓变化仅用于流程验证，不代表真实市场收益。"));
    }
    const metrics = el("div", "metric-grid");
    metrics.append(metric("账户权益（元）", money(snapshot.equity), snapshot.valuation_complete ? "按当前数据估值" : "估值资料不完整"), metric("可用现金（元）", money(account.cash), "模拟账本余额"), metric("最大单一仓位", percent(snapshot.risk?.largest_position_weight), "以有效估值计算"));
    node.append(metrics);
    const card = el("div", "card table-card");
    card.append(el("h3", "", "当前模拟持仓"));
    const table = el("div", "table-scroll");
    table.tabIndex = 0;
    table.setAttribute("aria-label", "模拟持仓，可横向滚动");
    renderTable(table, [{key: "symbol", label: "标的"}, {key: "quantity", label: "股数", format: number}, {key: "average_cost", label: "平均成本", format: money}, {key: "market_price", label: "估值价格", format: money}, {key: "market_value", label: "市值 / 元", format: money}, {key: "unrealized_pnl", label: "浮动盈亏 / 元", format: money}, {key: "mark_date", label: "估值日期"}], snapshot.positions || [], "当前没有持仓。");
    card.append(table);
    node.append(card);
    const notes = snapshot.risk?.notes || [];
    if (notes.length || !snapshot.valuation_complete) {
      const risk = el("div", "risk-note");
      risk.append(el("strong", "", "仓位与估值提示"));
      const list = el("ul", "plain-list");
      listItems(list, notes, "估值不完整，不使用成本价替代缺失的行情。");
      risk.append(list);
      node.append(risk);
    }
    renderTable($("#paper-trade-table"), [{key: "symbol", label: "标的"}, ...tradeColumns.filter(column => column.key !== "signal_date"), {key: "dataset_source", label: "数据来源", wrap: true, format: (value, row) => `${row.source_kind === "demo" ? "[合成示例] " : ""}${value || "未提供"}`}, {key: "recorded_at", label: "登记时间", format: stamp}], snapshot.trades || [], "暂无交易记录。先选择历史日期并填写理由。");
  }
  async function refreshNotes() {
    const result = await api("/api/notes");
    const notes = Array.isArray(result.notes) ? result.notes : [];
    if (!notes.length) return;
    const node = $("#notes-list");
    node.replaceChildren();
    notes.slice().sort((a, b) => String(b.created_at || b.timestamp || "").localeCompare(String(a.created_at || a.timestamp || ""))).forEach(note => {
      const card = el("article", "card note-card");
      card.append(el("h3", "", `${note.symbol || "研究笔记"} · ${note.thesis || ""}`));
      card.append(el("div", "note-meta", `记录于 ${stamp(note.created_at || note.timestamp)}${note.id ? ` · ${String(note.id).slice(0, 8)}` : ""}`));
      [["支持证据", note.evidence], ["风险与反证", note.risks], ["判断失效条件", note.invalidation]].forEach(([title, value]) => { card.append(el("h4", "", title), el("p", "", value || "未填写")); });
      if (note.source_url) {
        try {
          const url = new URL(note.source_url);
          if (["https:", "http:"].includes(url.protocol)) {
            const link = el("a", "", `查看来源 · ${url.hostname} ↗`);
            link.href = url.href;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            card.append(link);
          }
        } catch (_) { card.append(el("p", "field-help", "来源地址格式无效。")); }
      }
      node.append(card);
    });
  }
  async function acceptDataset(dataset) {
    await refreshDatasetList(dataset.id);
    await selectDataset(dataset);
    showMessage(dataset.audit?.backtest_ready ? "数据已载入，数据检查通过。可以查看研究或运行回测。" : "数据已载入，但存在执行限制；请到数据管理查看具体原因。");
  }
  function bindEvents() {
    const tabs = $$("[data-tab]");
    tabs.forEach((button, index) => {
      button.addEventListener("click", () => switchTab(button.dataset.tab));
      button.addEventListener("keydown", event => {
        let next;
        if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
        if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = tabs.length - 1;
        if (next !== undefined) { event.preventDefault(); switchTab(tabs[next].dataset.tab, true); }
      });
    });
    $$("[data-open-tab]").forEach(button => button.addEventListener("click", () => switchTab(button.dataset.openTab, true)));
    $("#load-demo").addEventListener("click", event => busy(event.currentTarget, async () => { await acceptDataset(await api("/api/datasets/demo", {})); }));
    $("#dataset-select").addEventListener("change", async event => {
      const id = event.target.value;
      if (!id) return;
      clearMessage();
      try { await selectDataset(await api(`/api/datasets/${encodeURIComponent(id)}`)); }
      catch (error) { showMessage(error.message, true); }
    });
    $("#export-data").addEventListener("click", event => busy(event.currentTarget, async () => {
      if (!state.dataset) throw new Error("请先选择数据集。");
      const id = state.dataset.id;
      const exported = await api(`/api/export?dataset_id=${encodeURIComponent(id)}`);
      const blob = new Blob([JSON.stringify(exported, null, 2)], {type: "application/json;charset=utf-8"});
      const url = URL.createObjectURL(blob);
      const link = el("a");
      link.href = url;
      link.download = `invest-dataset-${id.slice(0, 12)}.json`;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      showMessage("数据 JSON 已准备下载，导出内容不含本地账户和凭据。");
    }));
    $("#import-form").addEventListener("submit", event => {
      event.preventDefault();
      const form = event.currentTarget;
      busy($("button[type=submit]", form), async () => {
        const data = new FormData(form);
        const file = $("#csv-file").files[0];
        const calendar = $("#calendar-file").files[0];
        if (!file) throw new Error("请选择行情 CSV 文件。");
        if (file.size + (calendar?.size || 0) > 2 * 1024 * 1024) throw new Error("文件总大小超过 2 MiB，请缩小数据区间。");
        const [csv, calendarCsv] = await Promise.all([file.text(), calendar ? calendar.text() : Promise.resolve("")]);
        await acceptDataset(await api("/api/datasets/import", {csv, calendar_csv: calendarCsv, source: String(data.get("source") || "").trim(), raw_prices_confirmed: data.get("raw_prices_confirmed") === "on", volume_shares_confirmed: data.get("volume_shares_confirmed") === "on"}));
      });
    });
    $("#tushare-form").addEventListener("submit", event => {
      event.preventDefault();
      const data = new FormData(event.currentTarget);
      busy($("#fetch-tushare"), async () => {
        if (!state.config?.tushare_configured) throw new Error("运行服务的环境尚未配置 TUSHARE_TOKEN。");
        await acceptDataset(await api("/api/datasets/tushare", {symbol: String(data.get("symbol")).trim().toUpperCase(), start: data.get("start"), end: data.get("end")}));
      });
    });
    $("#backtest-form").addEventListener("submit", event => {
      event.preventDefault();
      const form = event.currentTarget;
      busy($("button[type=submit]", form), async () => {
        const dataset = state.dataset;
        if (!dataset) throw new Error("请先载入数据集。");
        const data = new FormData(form);
        const payload = {dataset_id: dataset.id, symbol: data.get("symbol"), initial_cash: Number(data.get("initial_cash")), fast: Number(data.get("fast")), slow: Number(data.get("slow")), ...feesFromForm(form)};
        if (data.get("start_date")) payload.start_date = data.get("start_date");
        if (data.get("end_date")) payload.end_date = data.get("end_date");
        if (payload.fast >= payload.slow) throw new Error("短均线天数必须小于长均线天数。");
        const result = await api("/api/backtest", payload);
        if (state.dataset?.id !== dataset.id) { showMessage("回测已完成并保存，但当前数据集已切换。请选择原数据后重新运行以查看。"); return; }
        renderBacktest(result, dataset);
        showMessage(dataset.meta?.source_kind === "demo" ? "合成示例回测完成。结果仅用于验证流程，不反映真实市场收益。" : "历史回测完成，结果已保存。请同时查看费用、假设和未成交原因。");
      });
    });
    $("#account-select").addEventListener("change", async event => {
      state.accountId = event.target.value;
      updateDatasetControls();
      try { await loadAccount(state.accountId); } catch (error) { showMessage(error.message, true); }
    });
    $("#account-form").addEventListener("submit", event => {
      event.preventDefault();
      const form = event.currentTarget;
      busy($("button[type=submit]", form), async () => {
        const data = new FormData(form);
        const account = await api("/api/accounts", {name: String(data.get("name")).trim(), initial_cash: Number(data.get("initial_cash"))});
        await refreshAccounts(account.id || account.account?.id);
        $("#account-name").value = "";
        $(".create-account").open = false;
        showMessage("模拟账户已创建；所有操作仅记录于本地账本。");
      });
    });
    $("#paper-trade-form").addEventListener("submit", event => {
      event.preventDefault();
      const form = event.currentTarget;
      busy($("#record-trade"), async () => {
        if (!state.dataset || !state.accountId) throw new Error("请先载入数据并创建或选择模拟账户。");
        const data = new FormData(form);
        const accountId = state.accountId;
        const datasetId = state.dataset.id;
        const snapshot = await api(`/api/accounts/${encodeURIComponent(accountId)}/trades`, {dataset_id: datasetId, symbol: data.get("symbol"), date: data.get("date"), side: data.get("side"), quantity: Number(data.get("quantity")), reason: String(data.get("reason")).trim(), ...feesFromForm(form)});
        if (state.accountId === accountId && state.dataset?.id === datasetId) renderAccount(snapshot);
        else if (state.accountId) await loadAccount(state.accountId);
        $("#paper-reason").value = "";
        form.elements.cost_model_acknowledged.checked = false;
        showMessage("历史模拟交易已追加保存。可以在账户交易记录中核对成交与费用。");
      });
    });
    $("#note-form").addEventListener("submit", event => {
      event.preventDefault();
      const form = event.currentTarget;
      busy($("button[type=submit]", form), async () => {
        const data = Object.fromEntries(new FormData(form));
        Object.keys(data).forEach(key => { data[key] = String(data[key]).trim(); });
        await api("/api/notes", data);
        await refreshNotes();
        form.reset();
        showMessage("研究笔记已保存，证据与失效条件可随时回看。");
      });
    });
  }
  async function initialize() {
    buildFees();
    bindEvents();
    try {
      state.config = await api("/api/config");
      const version = String(state.config.version || "0.1");
      $("#version").textContent = version.startsWith("v") ? version : `v${version}`;
      $("#footer-version").textContent = $("#version").textContent;
      $("#tushare-status").textContent = state.config.tushare_configured ? "服务端已配置" : "尚未配置";
      $("#fetch-tushare").disabled = !state.config.tushare_configured;
      if (!state.config.tushare_configured) $("#tushare-help").textContent = "在运行本地服务的环境中配置 TUSHARE_TOKEN 后重启服务。网页不会读取、显示或保存 Token；没有配置时可使用 CSV 和合成示例。";
      const defaults = state.config.default_parameters || {};
      [$("#backtest-form"), $("#paper-trade-form")].forEach(form => {
        Object.entries(defaults).forEach(([key, value]) => {
          const input = form.elements.namedItem(key);
          if (input && input.type !== "checkbox" && (typeof value === "number" || typeof value === "string")) input.value = String(value);
        });
      });
      const results = await Promise.allSettled([refreshDatasetList(), refreshAccounts(), refreshNotes()]);
      const errors = results.filter(result => result.status === "rejected");
      if (state.datasets.length) {
        const remembered = recalledDataset();
        const latest = state.datasets.slice().sort((a, b) => String(b.meta?.retrieved_at || "").localeCompare(String(a.meta?.retrieved_at || "")))[0];
        const id = state.datasets.some(dataset => dataset.id === remembered) ? remembered : latest.id;
        await selectDataset(await api(`/api/datasets/${encodeURIComponent(id)}`));
      }
      if (errors.length) showMessage(`部分本地记录未能恢复：${errors.map(result => result.reason.message).join("；")}`, true);
    } catch (error) { showMessage(`工作台初始化未完成：${error.message}`, true); }
  }
  initialize();
})();
