"""Chronological study planning backed by scikit-learn's TimeSeriesSplit.

The splitter is the installed upstream implementation, not a local rewrite.
Inspected source: scikit-learn 1.8.0, 646da0f072a8afef6a980aa427a710311e67eb9d
(BSD-3-Clause; attribution in third_party/scikit_learn/COPYING).
"""
from __future__ import annotations

import sklearn
from sklearn.model_selection import TimeSeriesSplit

SCHEMA = 'invest-walk-forward-study-v1'
MAX_SESSIONS = 2500


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name}必须是 {minimum}–{maximum} 范围内的整数')
    return value


def plan_folds(bars, warmup, configuration):
    """Return explicit inclusive windows in session units, after common warmup.

    Gap bars are excluded from candidate selection. They may subsequently be
    used as known, past signal warmup before a test order. This is not label
    purging, a wall-clock-duration split, or access to a frozen holdout.
    """
    if not isinstance(configuration, dict) or set(configuration) - {
        'n_splits', 'gap', 'test_size', 'max_train_size'
    }:
        raise ValueError('滚动验证设置只支持 n_splits/gap/test_size/max_train_size')
    config = {
        'n_splits': _integer(configuration.get('n_splits', 3), '滚动折数', 2, 5),
        'gap': _integer(configuration.get('gap', 0), '训练评价间隔', 0, 60),
        'test_size': configuration.get('test_size'),
        'max_train_size': configuration.get('max_train_size'),
    }
    for key in ('test_size', 'max_train_size'):
        if config[key] is not None:
            config[key] = _integer(config[key], key, 10, MAX_SESSIONS)
    days = [bar['date'] for bar in bars]
    if days != sorted(set(days)):
        raise ValueError('滚动验证日期必须递增且无重复')
    sessions = days[warmup:]
    if not 1 <= len(sessions) <= MAX_SESSIONS:
        raise ValueError(f'滚动验证共同预热后须为1–{MAX_SESSIONS}个交易日')
    folds = []
    splitter = TimeSeriesSplit(**config)
    for number, (train, test) in enumerate(splitter.split(sessions), 1):
        if len(train) < 10 or len(test) < 10:
            raise ValueError('每折训练和评价都至少需要10个交易日；请减少折数或间隔')
        folds.append({
            'fold': number,
            'train': {'start': sessions[int(train[0])], 'end': sessions[int(train[-1])],
                      'sessions': len(train)},
            'test': {'start': sessions[int(test[0])], 'end': sessions[int(test[-1])],
                     'sessions': len(test)},
            'gap_sessions': config['gap'],
        })
    return config, folds


def run_walkforward(dataset, *, symbol, candidates, cash, costs, warmup, configuration):
    """Select each fold's candidate on earlier data, then replay it forward.

    This entry is called by experiments.run_study after the normal dataset,
    parameter and cost-acknowledgment gates. Only existing declared candidates
    compete. All training runs (including failures) are retained. Any failed
    training run blocks that fold/cost's selection rather than dropping it.
    """
    from .engine import backtest
    from .experiments import replay_ledger
    from .provenance import code_identity, SCHEME as CODE_IDENTITY_SCHEME
    from .workspace import digest

    bars = [bar for bar in dataset['bars'] if bar['symbol'] == symbol]
    config, folds = plan_folds(bars, warmup, configuration)
    protocol = {
        'schema': SCHEMA, 'mode': 'EXPLORATORY_WALK_FORWARD',
        'dataset_id': dataset['id'], 'symbol': symbol, 'initial_cash': cash,
        'candidates': candidates, 'costs': costs, 'shared_warmup': warmup,
        'splitter': 'sklearn.model_selection.TimeSeriesSplit',
        'splitter_version': sklearn.__version__, 'configuration': config,
        'folds': folds, 'selection_metric': 'training_excess_vs_buy_hold',
        'tie_break': 'declared_candidate_order',
        'parameter_budget': len(folds) * len(costs) * (len(candidates) + 1),
        'frozen_holdout_opened': False, 'code_identity': code_identity(),
        'code_identity_scheme': CODE_IDENTITY_SCHEME,
    }

    def evaluate(candidate, cost, window):
        record = {'candidate': candidate['name']}
        params = {key: value for key, value in cost.items() if key != 'name'}
        params.update(symbol=symbol, initial_cash=cash, fast=candidate['fast'],
                      slow=candidate['slow'], cost_model_acknowledged=True,
                      start_date=window['start'], end_date=window['end'])
        try:
            result = backtest(dataset, params)
            if (result['evaluation_start'] != window['start'] or
                    result['evaluation_end'] != window['end']):
                raise ValueError('候选的共同训练/评价窗口不一致')
            record.update(status='PASS', result=result, replay=replay_ledger(dataset, result),
                          cash_baseline_return=0.0,
                          excess_vs_buy_hold=result['metrics']['total_return'] -
                          result['metrics']['benchmark_return'])
        except ValueError as exc:
            record.update(status='FAILED', reason=str(exc))
        return record

    results = []
    for fold in folds:
        for cost in costs:
            training = [evaluate(candidate, cost, fold['train']) for candidate in candidates]
            record = {'period': f"滚动折 {fold['fold']}", 'fold': fold['fold'],
                      'cost': cost['name'], 'train_window': fold['train'],
                      'test_window': fold['test'], 'training': training,
                      'candidate': None}
            if any(row['status'] != 'PASS' for row in training):
                record.update(status='FAILED', reason='训练候选存在失败；本折未选优、未评价')
            else:
                # max returns the first matching candidate on ties. No test
                # scores have been computed or read when selection is made.
                selected = max(range(len(training)),
                               key=lambda i: training[i]['excess_vs_buy_hold'])
                record['selected_on_or_before'] = fold['train']['end']
                record['training_score'] = training[selected]['excess_vs_buy_hold']
                record.update(evaluate(candidates[selected], cost, fold['test']))
            results.append(record)
    passed = [row for row in results if row['status'] == 'PASS']
    return {
        'schema': SCHEMA, 'protocol': protocol, 'protocol_id': digest(protocol),
        'results': results, 'source_kind': dataset['meta'].get('source_kind'),
        'summary': {'planned': len(results), 'succeeded': len(passed),
                    'failed': len(results) - len(passed),
                    'below_buy_hold': sum(row['excess_vs_buy_hold'] < 0 for row in passed),
                    'training_runs': sum(len(row['training']) for row in results)},
        'limitations': [
            '每折只依据此前训练窗口选候选；同分按声明顺序，失败候选不静默丢弃',
            '间隔按交易日计，仅排除候选评分；评价前已知价格仍可用于均线预热',
            '各折独立重置初始资金，不把重置账户曲线拼成连续投资收益',
            '后续折训练可包含此前评价段；反复查看和调整仍可能造成研究者过拟合',
            '全部为探索性历史验证；没有打开冻结留出集，不证明真实样本外策略有效',
        ],
    }
