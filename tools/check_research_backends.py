"""Mandatory real-backend smoke: no skips, mocks, external data or package installation."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from invest.opensource import PROFILES, integration_catalog, run_integration


def request(name):
    values = ([math.sin(i * .63) + .2 * math.cos(i * .17) for i in range(64)]
              if name == 'arch' else [100 + .1*i + math.sin(i * .7) for i in range(64)])
    return {'backend': name, 'values': values, 'source': 'SYNTHETIC deterministic backend acceptance; no real market data',
            'as_of': datetime.now(timezone(timedelta(hours=8))).date().isoformat()}


def local():
    results = {}
    for name in PROFILES:
        print('DIRECT_START ' + name, file=sys.stderr, flush=True)
        args = request(name)
        result = run_integration(name, {'values': args.pop('values')}, source=args['source'], as_of=args['as_of'])
        assert result['backend_executed'] and result['status'] == 'SCENARIO_ONLY'
        results[name] = result
    return {'transport': 'direct Python API', 'count': len(results), 'results': results}


async def mcp():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    results = {}
    params = StdioServerParameters(command=sys.executable, args=['-m', 'invest.chat.mcp_server'],
                                   cwd=str(ROOT), env=dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8'))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=45)
            tools = (await session.list_tools()).tools
            assert len(tools) == 18
            catalog = await asyncio.wait_for(session.call_tool('research_catalog', {}), timeout=45)
            assert not catalog.isError and catalog.structuredContent['count'] == 11
            for name in PROFILES:
                print('MCP_START ' + name, file=sys.stderr, flush=True)
                result = await asyncio.wait_for(session.call_tool('research_run', request(name)), timeout=45)
                assert not result.isError, (name, result)
                assert result.structuredContent['backend_executed'] is True
                results[name] = result.structuredContent
            bad = request('duckdb')
            bad['values'][0] = True
            assert (await session.call_tool('research_run', bad)).isError
    return {'transport': 'actual MCP stdio subprocess', 'chat_tools': 18, 'count': len(results),
            'boolean_rejected': True, 'ordinary_chat_account_acceptance': False, 'results': results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mcp', action='store_true')
    args = parser.parse_args()
    result = asyncio.run(mcp()) if args.mcp else local()
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True))


if __name__ == '__main__':
    main()
