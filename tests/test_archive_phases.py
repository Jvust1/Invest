"""Fixed-vocabulary diagnostics for the actual bounded archive invocation."""
import json
from pathlib import Path
import subprocess

import pytest

from invest.data import demo_dataset
from invest.experiments import run_study
from invest.mlflow_tracking import (ARCHIVE_PHASES, WORKER_TIMEOUT, LocalMLflowArchive,
    _mark_archive_phase, _read_archive_phase, _write_archive_phase)
from invest.workspace import Workspace


@pytest.fixture
def record(tmp_path):
    return Workspace(tmp_path/'state.sqlite').put('study', run_study(demo_dataset(), {
        'symbol': '600000.SH', 'cost_model_acknowledged': True}))


def test_phase_journal_is_bounded_fixed_vocabulary_and_overwrites(tmp_path):
    path = tmp_path/'phase'
    for phase in sorted(ARCHIVE_PHASES):
        _write_archive_phase(path, phase)
        assert path.read_bytes() == phase.encode('ascii')
        assert path.stat().st_size < 65
        assert _read_archive_phase(path) == phase
    before = path.read_bytes()
    for invalid in ('private path/token/run ID', [], {}, None, 1):
        _write_archive_phase(path, invalid)
    assert path.read_bytes() == before
    for raw in (b'private path/token/run ID', b'client_initialization\nsecret', b'x'*100000, b'\xff', b''):
        path.write_bytes(raw)
        assert _read_archive_phase(path) is None
    assert _read_archive_phase(tmp_path/'missing') is None


def test_diagnostic_io_failures_do_not_replace_archive_behavior(tmp_path):
    _write_archive_phase(tmp_path/'absent'/'phase', 'sdk_import')
    assert _read_archive_phase(tmp_path) is None
    def unavailable(_):
        raise OSError('private directory')
    _mark_archive_phase(unavailable, 'artifact_write')
    seen = []
    _mark_archive_phase(seen.append, 'not_an_allowed_phase')
    assert seen == []
    _mark_archive_phase(seen.append, 'artifact_write')
    assert seen == ['artifact_write']


@pytest.mark.parametrize('phase', sorted(ARCHIVE_PHASES))
def test_timeout_reports_actual_phase_without_accepting_early_success(tmp_path, monkeypatch, record, phase):
    paths = []
    def timeout(command, **kwargs):
        assert kwargs['timeout'] == WORKER_TIMEOUT == 45
        assert kwargs['stderr'] is subprocess.DEVNULL
        assert kwargs['check'] is False
        path = Path(command[-1]); paths.append(path)
        assert path.parent != tmp_path and path.name == 'phase'
        _write_archive_phase(path, phase)
        raise subprocess.TimeoutExpired(command, 45,
            output=b'{"status":"archived","run_id":"do-not-trust-before-exit"}',
            stderr=b'private path or credential')
    monkeypatch.setattr(subprocess, 'run', timeout)
    result = LocalMLflowArchive(tmp_path).archive(record)
    assert result == {'status':'failed','reason':'archive_timeout','study_saved':True,'phase':phase}
    assert all(not path.exists() and not path.parent.exists() for path in paths)
    assert Workspace(tmp_path/'state.sqlite').get(record['id']) == record


def test_unknown_phase_is_not_reflected_and_journal_is_removed(tmp_path, monkeypatch, record):
    paths = []
    def timeout(command, **kwargs):
        path = Path(command[-1]); paths.append(path)
        path.write_text('private directory and token', encoding='ascii')
        raise subprocess.TimeoutExpired(command, 45)
    monkeypatch.setattr(subprocess, 'run', timeout)
    assert LocalMLflowArchive(tmp_path).archive(record) == {
        'status':'failed','reason':'archive_timeout','study_saved':True}
    assert not paths[0].parent.exists()


def test_completed_and_nonzero_children_retain_existing_success_rule(tmp_path, monkeypatch, record):
    for returncode in (0, 1):
        paths = []
        def result(command, **kwargs):
            path = Path(command[-1]); paths.append(path)
            _write_archive_phase(path, 'response_written')
            return subprocess.CompletedProcess(command, returncode,
                json.dumps({'status':'archived','reused':True,'study_saved':True}).encode())
        monkeypatch.setattr(subprocess, 'run', result)
        status = LocalMLflowArchive(tmp_path).archive(record)
        assert status['status'] == ('archived' if returncode == 0 else 'failed')
        assert 'phase' not in status
        assert not paths[0].parent.exists()


def test_actual_worker_reports_output_phase_then_exits_before_success(tmp_path, monkeypatch, record):
    import importlib.util
    if importlib.util.find_spec('mlflow') is None:
        pytest.skip('optional actual MLflow missing')
    original = subprocess.run
    observed = []
    def run(command, **kwargs):
        result = original(command, **kwargs)
        observed.append((_read_archive_phase(command[-1]), result.returncode))
        return result
    monkeypatch.setattr(subprocess, 'run', run)
    archive = LocalMLflowArchive(tmp_path)
    first = archive.archive(record)
    assert first['status'] == 'archived', first
    second = archive.archive(record)
    assert second['status'] == 'archived' and second['reused'] is True, second
    assert first['run_id'] == second['run_id']
    assert observed == [('response_written', 0), ('response_written', 0)]
    assert Workspace(tmp_path/'state.sqlite').get(record['id']) == record


def test_temp_setup_failure_falls_back_to_original_worker(tmp_path, monkeypatch, record):
    import tempfile
    def unavailable(*args, **kwargs):
        raise OSError('full private temp path or secret')
    monkeypatch.setattr(tempfile, 'TemporaryDirectory', unavailable)
    calls = []
    def completed(command, **kwargs):
        calls.append(command)
        assert command[-1] == str(tmp_path.resolve())
        assert kwargs['timeout'] == 45
        return subprocess.CompletedProcess(command, 0, b'{"status":"archived","study_saved":true}')
    monkeypatch.setattr(subprocess, 'run', completed)
    assert LocalMLflowArchive(tmp_path).archive(record) == {'status':'archived','study_saved':True}
    assert len(calls) == 1
    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 45)
    monkeypatch.setattr(subprocess, 'run', timeout)
    assert LocalMLflowArchive(tmp_path).archive(record) == {
        'status':'failed','reason':'archive_timeout','study_saved':True}


def test_diagnostic_cleanup_failure_does_not_replace_completed_success(tmp_path, monkeypatch, record):
    import tempfile
    original = tempfile.TemporaryDirectory
    class FailingCleanup:
        def __init__(self, **kwargs):
            self.inner = original(**kwargs)
            self.name = self.inner.name
        def cleanup(self):
            self.inner.cleanup()
            raise OSError('private diagnostic cleanup detail')
    monkeypatch.setattr(tempfile, 'TemporaryDirectory', FailingCleanup)
    def completed(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, b'{"status":"archived","study_saved":true}')
    monkeypatch.setattr(subprocess, 'run', completed)
    assert LocalMLflowArchive(tmp_path).archive(record) == {'status':'archived','study_saved':True}
