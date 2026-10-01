"""Save, validate or explicitly restore exact offline native research JSON.

Run from the source checkout with ``python -m examples.native_research_record``.
Exports contain embedded source rows and the caller's source_id declaration.
No provider download, broker, credentials, holdings or trade API is used.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from invest.native_research import (MAX_BYTES, parse_native_json, restore_native_json,
                                    run_and_save_native_research, validate_native_record)
from invest.providers.duckdb_cache import DuckDBMarketCache, DuckDBReplayProvider
from invest.workspace import Workspace


def save_from_cache(cache_path, workspace, source_id, symbol, start, end, input_role, trials=12):
    """Read one exact cached request; a miss fails without an upstream fallback."""
    with DuckDBMarketCache(cache_path, read_only=True) as cache:
        replay = DuckDBReplayProvider(cache, source_id=source_id)
        return run_and_save_native_research(Workspace(Path(workspace) / 'state.sqlite'), replay,
            symbol, start_date=start, end_date=end, input_role=input_role,
            optimization_trials=trials, optimization_splits=3, training_fraction=.7, optimization_seed=7)


def synthetic_pilot(destination):
    from .qlib_local_research import write_synthetic_dataset
    from invest.qlib_bridge import create_qlib_market_provider

    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    source = destination / 'synthetic-qlib-source'
    write_synthetic_dataset(source)
    source_id = 'synthetic-native-qlib-pilot/v1;unconverted-unverified-units'
    request = {'symbol': '000001.SH', 'start_date': '20250102', 'end_date': '20250618', 'adjust': 'qlib'}
    cache_path = destination / 'native.duckdb'
    with DuckDBMarketCache(cache_path) as cache:
        provider = create_qlib_market_provider(provider_uri=source)
        refresh = DuckDBReplayProvider(cache, source_id=source_id, upstream=provider, mode='refresh')
        refresh.history(**request)
    record = save_from_cache(cache_path, destination, source_id, request['symbol'],
                             request['start_date'], request['end_date'], 'synthetic')
    reopened = Workspace(destination / 'state.sqlite').get(record['id'], 'native_research')
    validate_native_record(reopened)
    assert reopened == record
    (destination / 'native-research.json').write_text(json.dumps(record, indent=2, allow_nan=False), encoding='utf-8')
    return record


def read_native_json(path):
    """One bounded read, even if a file grows while it is being opened/read."""
    with Path(path).open('rb') as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('native record JSON exceeds 8 MiB')
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError('native record JSON must be UTF-8') from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    pilot = commands.add_parser('synthetic-pilot', help='create a NEW directory with synthetic input and a durable report')
    pilot.add_argument('destination', type=Path)
    run = commands.add_parser('run', help='run/save from an existing exact native cache; never refresh')
    run.add_argument('--workspace', required=True, type=Path)
    run.add_argument('--cache', required=True, type=Path)
    run.add_argument('--source-id', required=True)
    run.add_argument('--symbol', required=True)
    run.add_argument('--start', required=True, help='YYYYMMDD')
    run.add_argument('--end', required=True, help='YYYYMMDD')
    run.add_argument('--input-role', choices=['synthetic', 'user_supplied_unverified'], required=True)
    run.add_argument('--trials', type=int, default=12)
    check = commands.add_parser('validate', help='fully replay a saved JSON record without optional SDKs')
    check.add_argument('record', type=Path)
    restore = commands.add_parser('restore', help='restore one native JSON export without replacing existing records')
    restore.add_argument('record', type=Path)
    restore.add_argument('--workspace', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == 'synthetic-pilot':
        record = synthetic_pilot(args.destination)
    elif args.command == 'run':
        record = save_from_cache(args.cache, args.workspace, args.source_id, args.symbol,
                                 args.start, args.end, args.input_role, args.trials)
    elif args.command == 'restore':
        record = restore_native_json(read_native_json(args.record), args.workspace / 'state.sqlite')
    else:
        record = parse_native_json(read_native_json(args.record))
        validate_native_record(record)
    result = {'record_id': record['id'], 'kind': record['kind'],
        'input_rows': len(record['payload']['input']['rows']),
        'evaluation_rows': len(record['payload']['curve']['rows']),
        'summary': record['payload']['summary'], 'validated': True}
    if args.command == 'restore':
        result.update(recorded_at=record['recorded_at'],
                      provenance='preserved_producer_and_timestamp_declarations_not_authenticated')
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
