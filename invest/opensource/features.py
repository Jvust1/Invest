"""Real, optional offline feature/research engines; no code or source URL input.

Primary API references:
https://technical-analysis-library-in-python.readthedocs.io/en/latest/ta.html
https://pmorissette.github.io/ffn/ffn.html
https://networkx.org/documentation/stable/reference/algorithms/link_analysis.html
https://plotly.com/python/creating-and-updating-figures/
https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
"""
from __future__ import annotations

import json
import math

from .common import load_dependency, positive_prices, validated_series


def _ta(values):
    momentum = load_dependency('ta.momentum', 'ta')
    trend = load_dependency('ta.trend', 'ta')
    volatility = load_dependency('ta.volatility', 'ta')
    pd = load_dependency('pandas', 'pandas')
    positive_prices(values, minimum_count=26)
    series = pd.Series(values, dtype=float)
    bands = volatility.BollingerBands(series, window=20, window_dev=2, fillna=False)
    return {'rsi_14': float(momentum.RSIIndicator(series, window=14, fillna=False).rsi().iloc[-1]),
            'sma_20': float(trend.SMAIndicator(series, window=20, fillna=False).sma_indicator().iloc[-1]),
            'ema_12': float(trend.EMAIndicator(series, window=12, fillna=False).ema_indicator().iloc[-1]),
            'bollinger_20': {'lower': float(bands.bollinger_lband().iloc[-1]), 'upper': float(bands.bollinger_hband().iloc[-1])},
            'position': len(values) - 1, 'warmup_filled': False,
            'interpretation': 'Library-defined descriptive indicators at the last observation, not buy/sell recommendations.'}


def _ffn(values):
    ffn = load_dependency('ffn.core', 'ffn')
    pd = load_dependency('pandas', 'pandas')
    positive_prices(values)
    series = pd.Series(values, dtype=float)
    returns = ffn.to_returns(series).iloc[1:]
    drawdowns = ffn.to_drawdown_series(series)
    return {'total_return': float(ffn.calc_total_return(series)),
            'max_drawdown': float(ffn.calc_max_drawdown(series)),
            'last_drawdown': float(drawdowns.iloc[-1]),
            'simple_returns_count': len(returns), 'mean_simple_return': float(returns.mean()),
            'interpretation': 'Input is a positive price/NAV path. No dividends, trading costs, calendar or annualization inferred.'}


def _networkx(values):
    nx = load_dependency('networkx', 'networkx')
    states = ['up' if b > a else 'down' if b < a else 'flat' for a, b in zip(values, values[1:])]
    graph = nx.DiGraph()
    graph.add_nodes_from(sorted(set(states)))
    for a, b in zip(states, states[1:]):
        graph.add_edge(a, b, weight=graph.get_edge_data(a, b, {}).get('weight', 0) + 1)
    ranks = nx.pagerank(graph, alpha=0.85, max_iter=500, tol=1e-12, weight='weight')
    return {'nodes': sorted(graph.nodes),
            'transitions': [{'from': a, 'to': b, 'count': int(w['weight'])} for a, b, w in sorted(graph.edges(data=True))],
            'pagerank': {key: float(ranks[key]) for key in sorted(ranks)},
            'strongly_connected_components': len(list(nx.strongly_connected_components(graph))),
            'interpretation': 'Descriptive transition graph of up/down/flat changes; PageRank is not a transition probability or expected return.'}


def _plotly(values):
    go = load_dependency('plotly.graph_objects', 'plotly')
    pio = load_dependency('plotly.io', 'plotly')
    fig = go.Figure(data=[go.Scatter(x=list(range(len(values))), y=values, mode='lines', name='Caller-supplied series')])
    fig.update_layout(template=None, title='Invest: caller-supplied research series',
                      xaxis_title='Observation index (not a verified calendar)', yaxis_title='Declared value')
    return {'figure': json.loads(pio.to_json(fig, pretty=False, remove_uids=True)),
            'format': 'plotly-figure-json', 'external_resources_requested': False,
            'interpretation': 'Figure specification only; no HTML execution, remote chart hosting or ordinary Chat widget acceptance.'}


def _sklearn(values):
    np = load_dependency('numpy', 'numpy')
    model_selection = load_dependency('sklearn.model_selection', 'scikit-learn')
    preprocessing = load_dependency('sklearn.preprocessing', 'scikit-learn')
    linear = load_dependency('sklearn.linear_model', 'scikit-learn')
    metrics = load_dependency('sklearn.metrics', 'scikit-learn')
    pipeline = load_dependency('sklearn.pipeline', 'scikit-learn')
    if len(values) < 24:
        raise ValueError('sklearn requires at least 24 observations')
    raw = np.asarray(values, dtype=float)
    x = np.column_stack([raw[2:-1], raw[1:-2], raw[:-3]])
    y = raw[3:]
    splitter = model_selection.TimeSeriesSplit(n_splits=3, gap=1)
    folds = []
    for train, test in splitter.split(x):
        estimator = pipeline.make_pipeline(preprocessing.StandardScaler(), linear.Ridge(alpha=1.0))
        estimator.fit(x[train], y[train])
        predicted = estimator.predict(x[test])
        baseline = x[test, 0]
        folds.append({'train_count': len(train), 'test_count': len(test),
                      'train_target_last_index': int(train[-1]) + 3,
                      'test_target_first_index': int(test[0]) + 3,
                      'test_target_last_index': int(test[-1]) + 3,
                      'ridge_mae': float(metrics.mean_absolute_error(y[test], predicted)),
                      'persistence_mae': float(metrics.mean_absolute_error(y[test], baseline))})
    return {'folds': folds, 'gap': 1, 'lags': [1, 2, 3], 'scaler_fit': 'training fold only',
            'evaluation_mode': 'rolling one-step: earlier observed test values may be lag features for later targets',
            'interpretation': 'Chronological synthetic research benchmark, not recursive multi-step forecasting, untouched holdout or trading P&L.'}


_RUNNERS = {'ta': _ta, 'ffn': _ffn, 'networkx': _networkx, 'plotly': _plotly, 'sklearn': _sklearn}


def run(name: str, payload: dict) -> dict:
    if name not in _RUNNERS:
        raise ValueError('unknown feature integration')
    values = validated_series(payload)
    result = _RUNNERS[name](values)
    # Reject backend overflow/NaN instead of emitting invalid JSON or fabricating values.
    try:
        json.dumps(result, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        raise ValueError('backend returned a non-finite or non-JSON result') from None
    return result
