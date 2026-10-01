"""No-SDK checks for diagnostics privacy and evidence handling."""
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('archive_profile', ROOT/'tools/profile_mlflow_archive.py')
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


def test_profile_discards_raw_logs_and_unexpected_fields():
    lines = ['SDK says private path and token',
        profile.MARKER+json.dumps({'name':'client_ready','seconds':1.2}),
        profile.MARKER+json.dumps({'name':'archive_error','seconds':2,'error_type':'OperationalError'}),
        profile.MARKER+json.dumps({'name':'oops','seconds':1,'raw_message':'private'}),
        profile.MARKER+json.dumps({'name':'oops','seconds':float('nan')}),
        profile.MARKER+'malformed']
    status, phases = profile.safe_output(b'{"status":"failed","reason":"archive_timeout"}', '\n'.join(lines).encode())
    assert status['reason'] == 'archive_timeout'
    assert phases == [{'name':'client_ready','seconds':1.2},
                      {'name':'archive_error','seconds':2,'error_type':'OperationalError'}]


def test_profile_requires_bounded_valid_status_and_local_run_id(tmp_path):
    assert profile.safe_output(b'x'*4097, b'')[0] == {}
    assert profile.safe_output(b'[1,2]', b'')[0] == {}
    for value in ('../outside', 'x'*32, None):
        assert profile.verify_committed(tmp_path, {'status':'archived','run_id':value}, b'{}') == {'success_emitted':False}
