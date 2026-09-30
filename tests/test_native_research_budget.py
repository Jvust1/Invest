"""Exact serialized-byte bounds without allocating an over-budget aggregate."""
import json

import pytest

from invest import native_research as native
from invest.workspace import canonical


@pytest.mark.parametrize('value', [
    {}, [], None, True, False, 0, -1, 1.234e-50,
    {'z': [True, None, False, -100, 1e100], 'a': {'empty': []}},
    {'unicode': '行情 😀 café', 'escaped': '\\"\n\t\r\b\f', 'control': '\x00\x1f'},
    {'名"\n': ['a\\b', {'nested😀': 'x\u2028y'}]},
])
def test_incremental_budget_equals_canonical_utf8_including_escaping(value, monkeypatch):
    exact = len(canonical(value).encode('utf-8'))
    monkeypatch.setattr(native, 'MAX_BYTES', exact)
    native._bounded_json(value)
    monkeypatch.setattr(native, 'MAX_BYTES', exact - 1)
    with pytest.raises(ValueError, match='8 MiB'):
        native._bounded_json(value)


def test_large_caller_object_is_rejected_without_aggregate_serialization(monkeypatch):
    # Shared references keep this fixture tiny in memory; naive whole-object
    # serialization would still allocate roughly 200 MiB before an 8 MiB check.
    value = [['é' * 1024] * 1000] * 100
    original = json.dumps
    calls = []

    def scalar_only(item, *args, **kwargs):
        assert type(item) not in (dict, list), 'over-budget aggregate was serialized'
        calls.append(None)
        return original(item, *args, **kwargs)

    monkeypatch.setattr(native.json, 'dumps', scalar_only)
    monkeypatch.setattr(native, 'canonical', lambda *a, **k: pytest.fail('aggregate canonicalization'))
    with pytest.raises(ValueError, match='8 MiB'):
        native._bounded_json(value)
    assert len(calls) < 5000  # Stop once byte budget is consumed, not after all nodes.
