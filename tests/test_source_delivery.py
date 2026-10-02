"""Adversarial tests for the separate, stdlib-only source delivery boundary."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import stat
import subprocess
import sys
from zipfile import ZIP_STORED, ZipFile

import pytest

SPEC = importlib.util.spec_from_file_location('invest_source_delivery',
    Path(__file__).resolve().parents[1] / 'tools' / 'build_source_delivery.py')
delivery = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = delivery
SPEC.loader.exec_module(delivery)


def git(repo, *args, data=None):
    return subprocess.check_output(['git', '-C', str(repo), *args], input=data,
                                   stderr=subprocess.PIPE).decode().strip()


def commit(repo):
    git(repo, 'add', '-A')
    git(repo, '-c', 'user.name=Source Test', '-c', 'user.email=source@example.invalid',
        'commit', '-qm', 'synthetic source fixture')
    return git(repo, 'rev-parse', 'HEAD')


@pytest.fixture
def repository(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    git(repo, 'init', '-q')
    content = {'README.md': b'Synthetic source fixture\n',
               'pyproject.toml': b'[project]\nname="synthetic-fixture"\n',
               'invest/__init__.py': b'VALUE = 1\n',
               'invest/web/app.js': b'const synthetic = true;\n',
               'tests/test_example.py': b'def test_synthetic(): assert True\n',
               'docs/example.md': b'Documentation\n',
               'governance/example.json': b'{"synthetic":true}\n',
               'third_party/example/LICENSE': b'Example license\n',
               'third_party/example/NOTICE': b'Example attribution\n',
               'third_party/example/source-lock.json': b'{"source":"fixture"}\n',
               'examples/SYNTHETIC_DEMO_prices.csv': b'date,close\n2000-01-01,1\n',
               'legacy_app/chunk.bin': b'\x00\xffnative-code',
               'legacy_research/chunk.bin': b'\x00\xffnative-code',
               '.env': b'NEVER_PACKAGE=synthetic\n',
               '.invest/private.json': b'{"private":"synthetic"}',
               'build/generated.py': b'# generated\n'}
    for name, data in content.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return repo, commit(repo)


def inject(repo, name, mode='100644', content=b'text\n', oid=None):
    """Construct raw trees: adversaries must also work on Windows Git/NTFS.

    No unsafe test name is written to disk or passed through Git's index path
    checks. The builder must reject the actual committed object itself.
    """
    if oid is None:
        oid = git(repo, 'hash-object', '-w', '--stdin', data=content)
    def replace_entry(tree_oid, parts):
        raw = subprocess.check_output(['git', '-C', str(repo), 'cat-file', 'tree', tree_oid]) if tree_oid else b''
        entries, offset = {}, 0
        while offset < len(raw):
            space = raw.index(b' ', offset)
            nul = raw.index(b'\0', space)
            entry_mode = raw[offset:space]
            entry_name = raw[space + 1:nul]
            entry_oid = raw[nul + 1:nul + 21].hex()
            entries[entry_name] = (entry_mode, entry_oid)
            offset = nul + 21
        leaf = parts[0].encode('utf-8')
        if len(parts) == 1:
            entries[leaf] = (mode.encode('ascii'), oid)
        else:
            prior = entries.get(leaf)
            child = replace_entry(prior[1] if prior else None, parts[1:])
            entries[leaf] = (b'40000', child)
        ordered = sorted(entries, key=lambda entry: entry + (b'/' if entries[entry][0] == b'40000' else b''))
        payload = b''.join(entries[entry][0] + b' ' + entry + b'\0' + bytes.fromhex(entries[entry][1]) for entry in ordered)
        return git(repo, 'hash-object', '-w', '-t', 'tree', '--stdin', data=payload)
    tree = replace_entry(git(repo, 'rev-parse', 'HEAD^{tree}'), name.split('/'))
    return git(repo, '-c', 'user.name=Source Test', '-c', 'user.email=source@example.invalid',
               'commit-tree', tree, '-p', git(repo, 'rev-parse', 'HEAD'), '-m', 'synthetic adversary')


def rewrite_zip(path, mutate):
    with ZipFile(path) as original:
        members = [(info, original.read(info)) for info in original.infolist()]
    target = BytesIO()
    with ZipFile(target, 'w', compression=ZIP_STORED) as modified:
        for info, data in members:
            info, data = mutate(info, data)
            modified.writestr(info, data)
    path.write_bytes(target.getvalue())


def test_committed_only_deterministic_manifest_and_safe_extraction(repository, tmp_path):
    repo, oid = repository
    first, second = tmp_path/'first.zip', tmp_path/'second.zip'
    report = delivery.build(repo, oid, first)
    (repo/'README.md').write_text('dirty worktree MUST NOT be delivered')
    (repo/'invest'/'private.json').write_text('{"private":"untracked"}')
    delivery.build(repo, oid, second)
    assert first.read_bytes() == second.read_bytes()
    assert report['archive_sha256'] == hashlib.sha256(first.read_bytes()).hexdigest()
    assert not report['windows_exe_verified'] and not report['browser_layout_verified']
    assert not report['user_device_verified'] and report['source_only']
    extracted = tmp_path/'extracted'
    assert delivery.verify(repo, oid, first, extract=extracted) == report
    root = extracted/'invest-source'
    assert (root/'README.md').read_bytes() == b'Synthetic source fixture\n'
    assert not (root/'legacy_app').exists() and not (root/'legacy_research').exists()
    assert not (root/'.env').exists() and not (root/'.invest').exists()
    assert not (root/'build').exists() and not (root/'invest'/'private.json').exists()
    assert (root/'third_party/example/LICENSE').exists()
    assert (root/'third_party/example/NOTICE').exists()
    assert (root/'third_party/example/source-lock.json').exists()
    assert (root/'examples/SYNTHETIC_DEMO_prices.csv').exists()
    manifest = json.loads((root/delivery.MANIFEST).read_bytes())
    assert manifest['source_commit'] == oid
    assert manifest['source_tree'] == git(repo, 'rev-parse', oid+'^{tree}')
    assert manifest['file_count'] == len(manifest['files']) == 11
    names = [item['path'] for item in manifest['files']]
    assert names == sorted(names)
    for item in manifest['files']:
        data = (root/item['path']).read_bytes()
        assert item['sha256'] == hashlib.sha256(data).hexdigest()
        assert item['bytes'] == len(data)
        assert item['git_mode'] == item['archive_mode'] == '100644'
    with ZipFile(first) as archive:
        assert archive.namelist() == sorted(archive.namelist())
        assert not archive.comment
        for info in archive.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.compress_type == ZIP_STORED
            assert info.external_attr >> 16 == stat.S_IFREG | 0o644
            assert not info.extra and not info.comment


@pytest.mark.parametrize('revision', ['HEAD', 'main', 'v1', 'a'*7, 'A'*40, 'HEAD^{tree}', '--help'])
def test_requires_immutable_full_commit(repository, tmp_path, revision):
    repo, _ = repository
    with pytest.raises(delivery.DeliveryError, match='full lowercase immutable'):
        delivery.build(repo, revision, tmp_path/'out.zip')
    assert not (tmp_path/'out.zip').exists()


def test_wrong_git_type_missing_object_and_replacement_ref(repository, tmp_path, monkeypatch):
    repo, oid = repository
    original = delivery.snapshot(repo, oid)
    tree = git(repo, 'rev-parse', oid+'^{tree}')
    for wrong in (tree, '0'*40):
        with pytest.raises(delivery.DeliveryError, match='missing or wrong-type'):
            delivery.snapshot(repo, wrong)
    (repo/'README.md').write_text('Replacement must not be used\n')
    other = commit(repo)
    git(repo, 'replace', oid, other)
    monkeypatch.setenv('GIT_DIR', str(tmp_path/'nonexistent'))
    monkeypatch.setenv('GIT_WORK_TREE', str(tmp_path/'nonexistent'))
    assert delivery.snapshot(repo, oid) == original


@pytest.mark.parametrize('name,mode', [('invest/link.py', '120000'), ('invest/submodule', '160000')])
def test_rejects_git_links_and_submodules(repository, name, mode):
    repo, head = repository
    oid = inject(repo, name, mode, oid=head if mode == '160000' else None)
    with pytest.raises(delivery.DeliveryError, match='symlink/submodule/special'):
        delivery.snapshot(repo, oid)


@pytest.mark.parametrize('name', ['invest/a\\b.py', 'invest/a:b.py', 'invest/CON.py',
                                  'invest/LPT1.txt', 'invest/CON .py', 'invest/LPT1 .txt',
                                  'invest/COM¹.py', 'invest/LPT².py', 'invest/trailing. /a.py',
                                  'invest/newline\n.py', 'invest/'+'a'*230+'.py',
                                  'invest/e\u0301.py'])
def test_rejects_unsafe_and_nonportable_paths(repository, name):
    repo, _ = repository
    oid = inject(repo, name)
    with pytest.raises(delivery.DeliveryError, match='unsafe source path'):
        delivery.snapshot(repo, oid)


@pytest.mark.parametrize('name', ['../escape.py', '/absolute.py', 'invest//a.py', 'invest/./a.py',
                                  'invest/../a.py', 'C:/a.py', 'invest/a\x00.py'])
def test_rejects_traversal_paths_before_extraction(name):
    with pytest.raises(delivery.DeliveryError, match='unsafe source path'):
        delivery._path(name, delivery.Limits())


def test_case_collision_and_reserved_manifest(repository):
    repo, _ = repository
    for name in ('readme.md', delivery.MANIFEST):
        oid = inject(repo, name)
        with pytest.raises(delivery.DeliveryError, match='case-colliding|reserved'):
            delivery.snapshot(repo, oid)
        git(repo, 'reset', '-q', 'HEAD')


@pytest.mark.parametrize('name,content', [('invest/native.bin', b'compiled'),
    ('invest/pretend.py', b'\x00ELF'), ('invest/pretend.py', b'\xff\xfe'),
    ('examples/customer_prices.csv', b'account,balance\n'),
    ('credentials.pem', b'private'), ('unknown/file.py', b'text')])
def test_rejects_non_source_and_binary_payload(repository, name, content):
    repo, _ = repository
    oid = inject(repo, name, content=content)
    with pytest.raises(delivery.DeliveryError, match='admitted source|binary|non-UTF-8'):
        delivery.snapshot(repo, oid)


def test_source_script_mode_is_recorded_but_not_executable(repository, tmp_path):
    repo, _ = repository
    oid = inject(repo, 'tools/example.sh', mode='100755', content=b'#!/bin/sh\necho synthetic\n')
    archive = tmp_path/'source.zip'
    delivery.build(repo, oid, archive)
    with ZipFile(archive) as package:
        manifest = json.loads(package.read(delivery.PREFIX+delivery.MANIFEST))
        entry = next(item for item in manifest['files'] if item['path'] == 'tools/example.sh')
        assert entry['git_mode'] == '100755' and entry['archive_mode'] == '100644'
        assert package.getinfo(delivery.PREFIX+'tools/example.sh').external_attr >> 16 == stat.S_IFREG | 0o644


@pytest.mark.parametrize('limits', [replace(delivery.Limits(), files=1),
    replace(delivery.Limits(), bytes=1), replace(delivery.Limits(), blob=1),
    replace(delivery.Limits(), tree_bytes=1), replace(delivery.Limits(), archive=1)])
def test_resource_bounds_leave_no_output(repository, tmp_path, limits):
    repo, oid = repository
    with pytest.raises(delivery.DeliveryError, match='limit'):
        delivery.build(repo, oid, tmp_path/'out.zip', limits)
    assert not (tmp_path/'out.zip').exists()


@pytest.mark.parametrize('limits', [replace(delivery.Limits(), files=0),
    replace(delivery.Limits(), bytes=10**20), replace(delivery.Limits(), blob=True)])
def test_resource_bounds_cannot_be_disabled(repository, limits):
    with pytest.raises(delivery.DeliveryError, match='limit'):
        delivery.snapshot(*repository, limits)


def test_exclusive_outputs_and_destination(repository, tmp_path):
    repo, oid = repository
    archive = tmp_path/'source.zip'
    delivery.build(repo, oid, archive)
    original = archive.read_bytes()
    with pytest.raises(FileExistsError):
        delivery.build(repo, oid, archive)
    assert archive.read_bytes() == original
    destination = tmp_path/'existing'
    destination.mkdir()
    (destination/'keep.txt').write_text('keep')
    with pytest.raises(FileExistsError):
        delivery.verify(repo, oid, archive, extract=destination)
    assert (destination/'keep.txt').read_text() == 'keep'


def test_output_and_archive_symlinks_rejected(repository, tmp_path):
    repo, oid = repository
    target = tmp_path/'target'
    target.write_bytes(b'keep')
    link = tmp_path/'link.zip'
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip('platform does not permit creating test symlinks')
    with pytest.raises(FileExistsError):
        delivery.build(repo, oid, link)
    with pytest.raises(delivery.DeliveryError, match='regular file'):
        delivery.verify(repo, oid, link)
    assert target.read_bytes() == b'keep'


@pytest.mark.parametrize('attack', ['payload', 'manifest', 'timestamp', 'symlink', 'traversal', 'foreign_schema'])
def test_corrupt_metadata_and_manifest_rejected_before_extraction(repository, tmp_path, attack):
    repo, oid = repository
    archive = tmp_path/'source.zip'
    delivery.build(repo, oid, archive)
    def mutate(info, data):
        if info.filename == delivery.PREFIX+delivery.MANIFEST:
            if attack == 'manifest':
                manifest = json.loads(data)
                manifest['source_commit'] = '0'*40
                data = json.dumps(manifest).encode()
            elif attack == 'foreign_schema':
                data = b'{"schema":"foreign","files":[]}'
        elif info.filename == delivery.PREFIX+'README.md':
            if attack == 'payload':
                data = b'changed\n'
            elif attack == 'timestamp':
                info.date_time = (2000, 1, 1, 0, 0, 0)
            elif attack == 'symlink':
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                data = b'/tmp/escape'
            elif attack == 'traversal':
                info.filename = '../escape'
        return info, data
    rewrite_zip(archive, mutate)
    with pytest.raises(delivery.DeliveryError, match='canonical source commit/manifest'):
        delivery.verify(repo, oid, archive, extract=tmp_path/'never-created')
    assert not (tmp_path/'never-created').exists()


def test_foreign_self_consistent_archive_and_trailing_bytes_rejected(repository, tmp_path):
    repo, oid = repository
    (repo/'README.md').write_text('Different immutable source\n')
    foreign = commit(repo)
    archive = tmp_path/'foreign.zip'
    delivery.build(repo, foreign, archive)
    with pytest.raises(delivery.DeliveryError, match='canonical source commit/manifest'):
        delivery.verify(repo, oid, archive)
    with archive.open('ab') as stream:
        stream.write(b'extraneous trailing bytes')
    with pytest.raises(delivery.DeliveryError, match='canonical source commit/manifest'):
        delivery.verify(repo, foreign, archive)


def test_archive_read_is_bounded(repository, tmp_path):
    repo, oid = repository
    archive = tmp_path/'oversized.zip'
    with archive.open('wb') as stream:
        stream.truncate(delivery.Limits().archive + 1)
    with pytest.raises(delivery.DeliveryError, match='archive byte limit'):
        delivery.verify(repo, oid, archive)


def test_cli_build_verify_and_fail_closed(repository, tmp_path):
    repo, oid = repository
    tool = str(Path(delivery.__file__))
    archive = tmp_path/'cli.zip'
    for command in [['build', '--output', str(archive)], ['verify', '--archive', str(archive)]]:
        result = subprocess.run([sys.executable, tool, *command, '--repo', str(repo), '--commit', oid],
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['source_commit'] == oid
    result = subprocess.run([sys.executable, tool, 'build', '--repo', str(repo), '--commit', 'HEAD',
                             '--output', str(tmp_path/'never.zip')], capture_output=True, text=True)
    assert result.returncode == 1 and 'immutable' in result.stderr
    assert not (tmp_path/'never.zip').exists()


def test_duplicate_zip_members_are_rejected(repository, tmp_path):
    repo, oid = repository
    archive = tmp_path/'duplicate.zip'
    delivery.build(repo, oid, archive)
    with ZipFile(archive, 'a') as package, pytest.warns(UserWarning, match='Duplicate name'):
        package.writestr(delivery.PREFIX+'README.md', b'Synthetic source fixture\n')
    with pytest.raises(delivery.DeliveryError, match='canonical source commit/manifest'):
        delivery.verify(repo, oid, archive, extract=tmp_path/'never-created')
    assert not (tmp_path/'never-created').exists()


def test_extraction_failure_rolls_back_only_new_destination(repository, tmp_path, monkeypatch):
    repo, oid = repository
    archive = tmp_path/'source.zip'
    delivery.build(repo, oid, archive)
    destination = tmp_path/'extract'
    original = ZipFile.read
    def fail_read(self, name, *args, **kwargs):
        if getattr(name, 'filename', name) == delivery.PREFIX+'invest/__init__.py':
            raise OSError('synthetic disk/read failure')
        return original(self, name, *args, **kwargs)
    monkeypatch.setattr(ZipFile, 'read', fail_read)
    with pytest.raises(OSError, match='synthetic'):
        delivery.verify(repo, oid, archive, extract=destination)
    assert not destination.exists()
    assert archive.exists()


def test_build_failure_removes_its_partial_output(repository, tmp_path, monkeypatch):
    repo, oid = repository
    output = tmp_path/'partial.zip'
    def fail_fsync(*args):
        raise OSError('synthetic fsync failure')
    monkeypatch.setattr(delivery.os, 'fsync', fail_fsync)
    with pytest.raises(OSError, match='synthetic fsync'):
        delivery.build(repo, oid, output)
    assert not output.exists()


def test_git_reads_disable_network_and_do_not_inherit_credentials(repository, monkeypatch):
    calls = []
    original = subprocess.Popen
    def checked(command, *args, **kwargs):
        calls.append(command)
        assert command[1:3] == ['--no-replace-objects', '--no-optional-locks']
        assert 'protocol.allow=never' in command
        env = kwargs['env']
        assert env['GIT_NO_LAZY_FETCH'] == '1' and env['GIT_TERMINAL_PROMPT'] == '0'
        assert env['GIT_ALLOW_PROTOCOL'] == ''
        assert 'GITHUB_TOKEN' not in env and 'GIT_ASKPASS' not in env
        return original(command, *args, **kwargs)
    monkeypatch.setenv('GITHUB_TOKEN', 'synthetic-token-do-not-pass')
    monkeypatch.setenv('GIT_ASKPASS', '/never/run/this')
    monkeypatch.setattr(subprocess, 'Popen', checked)
    delivery.snapshot(*repository)
    assert len(calls) == 1


@pytest.mark.parametrize('fail_write', [True, False])
def test_build_write_and_close_failure_removes_partial_output(repository, tmp_path, monkeypatch, fail_write):
    repo, oid = repository
    output = tmp_path/'close-failure.zip'
    original_open = Path.open
    class FailingWriter:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.close()
        def write(self, data):
            if fail_write:
                self.stream.write(data[:1])
                self.stream.flush()
                raise OSError('synthetic write failure')
            return self.stream.write(data)
        def flush(self):
            return self.stream.flush()
        def fileno(self):
            return self.stream.fileno()
        def close(self):
            self.stream.close()
            raise OSError('synthetic close failure')
    def open_file(path, mode='r', *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        return FailingWriter(stream) if path == output and mode == 'xb' else stream
    monkeypatch.setattr(Path, 'open', open_file)
    with pytest.raises(OSError, match='synthetic close failure'):
        delivery.build(repo, oid, output)
    assert not output.exists()
