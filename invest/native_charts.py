"""Bounded, offline PNG views of saved native research, separate from cash studies.

The complete native record is arithmetic-validated before optional SDK discovery.
No provider, search, model, market-data conversion or cash-execution engine runs.
The original JSON is authoritative; a PNG preserves declarations, not attestations.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from importlib import metadata
import io
import math

from .native_research import validate_native_record
from .study_charts import (ChartBusyError, ChartDependencyError, TESTED_MATPLOTLIB_VERSION,
                           _RENDER_LOCK, drawdowns)
from .workspace import canonical, digest

SCHEMA = 'invest-native-research-chart-v1'
MAX_PLOT_MAGNITUDE = 1e12
WIDTH, HEIGHT = 1200, 900
SCOPE = 'exploratory native close-to-close signal research; not A-share cash execution or investment advice'


def prepare_native_chart(record):
    """Validate the entire envelope and derive a later-only, signed unit curve.

    Chart limits are stricter than storage limits: reject extreme plot magnitudes
    rather than clipping or silently changing valid arithmetic. Negative unit
    capital, if accepted by the native validator, is never clamped to zero.
    """
    validate_native_record(record)
    payload = record['payload']
    curve = payload['curve']
    equity_index = curve['columns'].index('equity')
    equity = [float(row[equity_index]) for row in curve['rows']]
    declines = drawdowns(equity, 1.0)
    if any(not math.isfinite(v) or abs(v) > MAX_PLOT_MAGNITUDE for v in equity + declines):
        raise ValueError('native chart values exceed the finite plotting magnitude limit (1e12); JSON remains authoritative')
    if any(v > 0 for v in declines):
        raise ValueError('native chart drawdown must be a nonpositive fraction')
    dates = [date.fromisoformat(day) for day in curve['dates']]
    identity = {
        'schema': SCHEMA,
        'record_id': record['id'],
        # The Workspace content ID excludes recorded_at. Bind the full exported
        # envelope too, preserving the original timestamp spelling as a claim.
        'record_sha256': digest(record),
        'record_kind': record['kind'],
        'record_schema': payload['schema'],
        'recorded_at_declaration': record['recorded_at'],
        'curve_sha256': digest(curve),
        'input_role': payload['input_role'],
        'source_declaration': deepcopy(payload['snapshot']),
        'producer_declaration': deepcopy(payload['producer']),
        'split_declaration': deepcopy(payload['split']),
        'optimization_declaration': deepcopy(payload['optimization']),
        'conventions': deepcopy(payload['conventions']),
        'limitations': deepcopy(payload['limitations']),
        'initial_unit_capital': 1.0,
        'scope': SCOPE,
        'renderer': {'name': 'matplotlib', 'version': TESTED_MATPLOTLIB_VERSION,
                     'backend': 'FigureCanvasAgg', 'width': WIDTH, 'height': HEIGHT,
                     'style': SCHEMA},
    }
    identity['render_id'] = digest(identity)
    return {'dates': dates, 'equity': equity, 'drawdown': declines, 'identity': identity}


def render_native_png(record):
    """Render one immutable native report with the actual pinned Agg canvas.

    Share the cash renderer's nonblocking lock without changing its validators.
    Acquiring before validation also bounds simultaneous native trial replays.
    The HTTP caller separately serializes study/validation work and releases all
    locks before replying, including dependency and renderer failure responses.
    """
    if not _RENDER_LOCK.acquire(blocking=False):
        raise ChartBusyError('已有图表正在生成，请稍后重试')
    try:
        data = prepare_native_chart(record)
        try:
            version = metadata.version('matplotlib')
        except metadata.PackageNotFoundError:
            raise ChartDependencyError('原生研究图表需要可选 charts 扩展（Matplotlib 3.10.8）；保存记录仍保留') from None
        if version != TESTED_MATPLOTLIB_VERSION:
            raise ChartDependencyError('原生研究图表需要已验证版本 Matplotlib 3.10.8；请安装 Invest 的 charts 扩展')
        try:
            from matplotlib.backends.backend_agg import FigureCanvasAgg
            from matplotlib.figure import Figure
            from matplotlib.text import Text
        except ImportError:
            raise ChartDependencyError('Matplotlib 图表依赖无法载入，请重新安装 charts 扩展') from None

        # Fixed size, backend, fonts and literal labels. No pyplot, rc mutation,
        # user text/TeX, source path, URL or caller-controlled renderer options.
        figure = Figure(figsize=(10, 7.5), dpi=120, facecolor='#f7f9fc', layout='none')
        canvas = FigureCanvasAgg(figure)
        top = figure.add_axes((.10, .45, .86, .28))
        bottom = figure.add_axes((.10, .24, .86, .16))
        x = list(range(len(data['dates'])))
        top.plot(x, data['equity'], label='Later evaluation unit capital', color='#155e75', linewidth=1.8)
        top.axhline(1.0, label='Initial unit capital = 1', color='#94a3b8', linestyle='--', linewidth=1)
        top.set_ylabel('Unit capital (initial = 1)', fontsize=10)
        top.legend(loc='best', fontsize=9)
        bottom.plot(x, data['drawdown'], color='#9a3412', linewidth=1.5)
        bottom.axhline(0, color='#94a3b8', linewidth=.7)
        bottom.set_ylim(min(-.001, min(data['drawdown'])) * 1.08, 0)
        bottom.set_ylabel('Drawdown (fraction)', fontsize=10)
        ticks = sorted({round(i * (len(x) - 1) / 4) for i in range(5)})
        for axes in (top, bottom):
            axes.set_facecolor('white')
            axes.grid(axis='y', color='#e2e8f0', linewidth=.7)
            axes.set_xticks(ticks, [data['dates'][i].isoformat() for i in ticks], fontsize=8)
            axes.ticklabel_format(axis='y', style='sci', scilimits=(-3, 5), useOffset=False, useMathText=False)
            for spine in axes.spines.values():
                spine.set_edgecolor('#cbd5e1')
        bottom.set_xlabel('Observed evaluation sessions (equal spacing; no sessions invented)', fontsize=9)
        identity = data['identity']
        label = ('SYNTHETIC INPUT DECLARATION' if identity['input_role'] == 'synthetic'
                 else 'USER-SUPPLIED INPUT DECLARATION / UNVERIFIED')
        figure.text(.10, .945, 'Invest | native research report', fontsize=19, weight='bold', color='#123047')
        figure.text(.10, .905, label, fontsize=10, weight='bold', color='#9a3412')
        figure.text(.10, .87, 'EXPLORATORY / NOT A-SHARE CASH EXECUTION', fontsize=10, weight='bold', color='#9a3412')
        symbol = identity['source_declaration']['request']['symbol']
        optimization = identity['optimization_declaration']
        params = optimization['params']
        figure.text(.10, .832, f"Declared symbol {symbol} | Selected MA {params['fast']}/{params['slow']} | Native signal fee {optimization['fee_bps']:g} bps", fontsize=10)
        figure.text(.10, .80, f"Later evaluation only: {data['dates'][0]} to {data['dates'][-1]} | {len(x)} observations", fontsize=10)
        figure.text(.10, .767, 'Native price and volume units unverified. No cash, lot-size or T+1 execution claims.', fontsize=9)
        figure.text(.10, .155, 'Drawdown includes initial unit capital. Earlier training observations are not plotted.', fontsize=8)
        figure.text(.10, .128, 'Source, producer and timestamps are declarations, not independently verified provenance.', fontsize=8)
        figure.text(.10, .101, 'Frozen holdout unopened. Saved JSON is authoritative; arithmetic is not market validation.', fontsize=8)
        figure.text(.10, .067, f"Record {identity['record_id'][:16]} | Curve {identity['curve_sha256'][:16]}", fontsize=8)
        figure.text(.10, .040, f"Render {identity['render_id'][:16]} | Full identity and original declarations in PNG metadata", fontsize=8)
        for text in figure.findobj(match=Text):
            text.set_usetex(False)
            text.set_parse_math(False)
            text.set_fontfamily('DejaVu Sans')
        output = io.BytesIO()
        canvas.print_png(output, metadata={
            'Software': 'Invest / Matplotlib ' + version,
            'Description': canonical(identity),
            'Disclaimer': label + '; ' + SCOPE + '; native price/volume units unverified; source and producer are declarations',
        })
        return output.getvalue()
    finally:
        _RENDER_LOCK.release()
