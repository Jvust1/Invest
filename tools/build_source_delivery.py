"""Build/verify a bounded, reproducible source ZIP from local committed Git objects.

No checkout files, Git filters, SDKs, credentials, network, or native bundlers are
used. Verification requires the independently selected full commit ID and its
local Git objects; an archive's own manifest is never its trust anchor.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
from typing import Iterator
import unicodedata
from zipfile import ZIP_STORED, ZipFile, ZipInfo

SCHEMA = 'invest-source-delivery-v1'
PREFIX = 'invest-source/'
MANIFEST = 'SOURCE_MANIFEST.json'
EXCLUDED_ROOTS = ('legacy_app', 'legacy_research')
SOURCE_ROOTS = frozenset({'.github', 'assistant_jobs', 'docs', 'examples', 'governance',
                          'integrations', 'invest', 'tests', 'third_party', 'tools'})
ROOT_FILES = frozenset({'.gitattributes', '.gitignore', 'AGENTS.md', 'README.md',
                        'THIRD_PARTY.md', 'LICENSE', 'NOTICE', 'COPYING', 'AUTHORS',
                        'desktop.py', 'desktop_adapter.py', 'desktop_runtime.py',
                        'pyproject.toml', 'start.bat'})
TEXT_SUFFIXES = frozenset({'.py', '.js', '.cjs', '.mjs', '.ts', '.tsx', '.jsx', '.json',
                           '.md', '.rst', '.txt', '.yaml', '.yml', '.toml', '.ini',
                           '.cfg', '.css', '.html', '.bat', '.sh', '.ps1'})
SYNTHETIC_CSV = frozenset({'examples/SYNTHETIC_DEMO_calendar.csv',
                           'examples/SYNTHETIC_DEMO_prices.csv'})
EXCLUDED_PARTS = frozenset({'.git', '.venv', 'venv', '__pycache__', '.pytest_cache',
                            '.mypy_cache', '.ruff_cache', 'node_modules', 'build',
                            'dist', 'delivery', '.invest', '.aws', '.ssh', '.codex',
                            'private', 'secrets', 'credentials', 'data', 'datasets'})
EXCLUDED_SUFFIXES = ('.pyc', '.pyo', '.sqlite', '.sqlite-wal', '.sqlite-shm', '.db',
                     '.db-wal', '.db-shm', '.duckdb', '.duckdb.wal', '.egg-info')
WINDOWS_RESERVED = frozenset({'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$',
                              *(f'COM{i}' for i in range(1, 10)),
                              *(f'LPT{i}' for i in range(1, 10)),
                              *(f'{name}{i}' for name in ('COM', 'LPT') for i in '¹²³')})
OID = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')


class DeliveryError(ValueError):
    """Input cannot be delivered as a bounded source-only archive."""


@dataclass(frozen=True)
class Limits:
    files: int = 5_000
    bytes: int = 64 * 1024 * 1024
    blob: int = 4 * 1024 * 1024
    tree_bytes: int = 4 * 1024 * 1024
    archive: int = 80 * 1024 * 1024
    path: int = 240


@dataclass(frozen=True)
class SourceFile:
    path: str
    git_mode: str
    oid: str
    content: bytes


@dataclass(frozen=True)
class Snapshot:
    commit: str
    tree: str
    files: tuple[SourceFile, ...]
    manifest: bytes


def _limits(limits: Limits) -> None:
    for name, maximum in vars(Limits()).items():
        value = getattr(limits, name)
        if type(value) is not int or not 0 < value <= maximum:
            raise DeliveryError(f'{name} limit must be positive and at most {maximum}')


def _path(path: str, limits: Limits) -> None:
    if (not path or len((PREFIX + path).encode('utf-8')) > limits.path
            or unicodedata.normalize('NFC', path) != path
            or any(ord(c) < 32 or ord(c) == 127 or c in '\\:<>"|?*' for c in path)):
        raise DeliveryError(f'unsafe source path: {path!r}')
    for part in path.split('/'):
        if (part in {'', '.', '..'} or part.endswith((' ', '.'))
                or part.split('.')[0].rstrip(' ').upper() in WINDOWS_RESERVED):
            raise DeliveryError(f'unsafe source path: {path!r}')


def _excluded(path: str) -> bool:
    parts = path.casefold().split('/')
    return (parts[0] in EXCLUDED_ROOTS or any(
        part in EXCLUDED_PARTS or part == '.env' or part.startswith('.env.')
        or part.endswith(EXCLUDED_SUFFIXES)
        or part in {'credentials.json', 'secrets.json'} for part in parts))


def _admit(path: str, content: bytes) -> None:
    parts = path.split('/')
    if len(parts) == 1:
        allowed = path in ROOT_FILES
    else:
        allowed = parts[0] in SOURCE_ROOTS and (
            Path(path).suffix.lower() in TEXT_SUFFIXES
            or parts[-1] in {'LICENSE', 'NOTICE', 'COPYING', 'AUTHORS'}
            or path in SYNTHETIC_CSV)
    if not allowed:
        raise DeliveryError(f'not an admitted source/text file: {path}')
    try:
        content.decode('utf-8')
    except UnicodeDecodeError as error:
        raise DeliveryError(f'non-UTF-8 source file: {path}') from error
    if any(b < 32 and b not in {9, 10, 12, 13} for b in content):
        raise DeliveryError(f'binary/control bytes in source file: {path}')


@contextmanager
def _objects(repo: Path) -> Iterator:
    # Use only local Git object reads. Disable replacement refs and lazy/promisor
    # fetches, and deny every transport as a second independent network guard.
    # Do not pass through GIT_* overrides or authentication/credential variables.
    env = {key: os.environ[key] for key in ('PATH', 'SystemRoot', 'SYSTEMROOT',
           'WINDIR', 'TMP', 'TEMP') if key in os.environ}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0', GIT_ALLOW_PROTOCOL='')
    command = ['git', '--no-replace-objects', '--no-optional-locks',
               '-c', 'protocol.allow=never', '-c', 'core.fsmonitor=false',
               '-C', str(repo.resolve(strict=True)), 'cat-file', '--batch']
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, env=env) as process:
        def read(oid: str, kind: str, maximum: int) -> bytes:
            if not OID.fullmatch(oid):
                raise DeliveryError('expected a full lowercase immutable Git object ID')
            try:
                process.stdin.write((oid + '\n').encode('ascii'))
                process.stdin.flush()
                header = process.stdout.readline(256).decode('ascii').strip().split()
            except (BrokenPipeError, UnicodeError) as error:
                raise DeliveryError('local Git object read failed') from error
            if len(header) != 3 or header[:2] != [oid, kind] or not header[2].isdigit():
                raise DeliveryError(f'missing or wrong-type local Git object: {oid}')
            size = int(header[2])
            if size > maximum:
                raise DeliveryError(f'{kind} object exceeds byte limit')
            raw = process.stdout.read(size + 1)
            if len(raw) != size + 1 or raw[-1:] != b'\n':
                raise DeliveryError('truncated Git object')
            raw = raw[:-1]
            digest = hashlib.sha1 if len(oid) == 40 else hashlib.sha256
            if digest(f'{kind} {size}\0'.encode('ascii') + raw).hexdigest() != oid:
                raise DeliveryError('Git object hash mismatch')
            return raw
        try:
            yield read
        finally:
            # Also discard an oversized object's unread payload without blocking.
            process.kill()
            process.communicate(timeout=10)


def snapshot(repo: Path, commit: str, limits: Limits = Limits()) -> Snapshot:
    """Resolve a full commit, walk its bounded trees, and hash admitted blobs."""
    _limits(limits)
    if not OID.fullmatch(commit):
        raise DeliveryError('commit must be a full lowercase immutable Git commit ID, not HEAD/tag/branch')
    files = []
    seen = set()
    total = tree_bytes = entries = excluded = 0
    with _objects(repo) as read:
        raw_commit = read(commit, 'commit', 1024 * 1024)
        first = raw_commit.split(b'\n', 1)[0]
        if not first.startswith(b'tree '):
            raise DeliveryError('commit has no source tree')
        try:
            tree = first[5:].decode('ascii')
        except UnicodeDecodeError as error:
            raise DeliveryError('invalid commit tree ID') from error
        if not OID.fullmatch(tree) or len(tree) != len(commit):
            raise DeliveryError('invalid commit tree ID')

        def walk(oid: str, prefix: str = '') -> None:
            nonlocal total, tree_bytes, entries, excluded
            raw = read(oid, 'tree', limits.tree_bytes - tree_bytes)
            tree_bytes += len(raw)
            offset = 0
            while offset < len(raw):
                space = raw.find(b' ', offset)
                nul = raw.find(b'\0', space + 1)
                width = len(commit) // 2
                if space < offset or nul < space or nul + 1 + width > len(raw):
                    raise DeliveryError('malformed Git tree')
                mode = raw[offset:space].decode('ascii')
                try:
                    name = raw[space + 1:nul].decode('utf-8')
                except UnicodeDecodeError as error:
                    raise DeliveryError('non-UTF-8 Git path') from error
                if '/' in name:
                    raise DeliveryError('slash in Git tree entry')
                child = raw[nul + 1:nul + 1 + width].hex()
                offset = nul + 1 + width
                path = prefix + name
                _path(path, limits)
                entries += 1
                if entries > limits.files * 2:
                    raise DeliveryError('tree entry limit exceeded')
                key = path.casefold()
                if key in seen or key == MANIFEST.casefold():
                    raise DeliveryError(f'duplicate, case-colliding, or reserved path: {path}')
                seen.add(key)
                if mode not in {'40000', '100644', '100755'}:
                    raise DeliveryError(f'symlink/submodule/special Git mode rejected: {path} ({mode})')
                if _excluded(path):
                    excluded += 1
                    continue
                if mode == '40000':
                    if '/' not in path and path not in SOURCE_ROOTS:
                        raise DeliveryError(f'not an admitted source directory: {path}')
                    walk(child, path + '/')
                else:
                    if len(files) >= limits.files:
                        raise DeliveryError('source file limit exceeded')
                    content = read(child, 'blob', min(limits.blob, limits.bytes - total))
                    _admit(path, content)
                    total += len(content)
                    files.append(SourceFile(path, mode, child, content))
        walk(tree)
    required = {'README.md', 'pyproject.toml', 'invest/__init__.py'}
    if not required.issubset({item.path for item in files}):
        raise DeliveryError('source commit lacks required Invest package files')
    files.sort(key=lambda item: item.path)
    manifest = {
        'schema': SCHEMA, 'source_commit': commit, 'source_tree': tree,
        'object_format': 'sha1' if len(commit) == 40 else 'sha256',
        'policy': {'excluded_roots': list(EXCLUDED_ROOTS),
                   'excluded_entries': excluded, 'archive_mode': '100644',
                   'payload': 'committed-admitted-UTF-8-source-only',
                   'synthetic_csv_paths': sorted(SYNTHETIC_CSV)},
        'file_count': len(files), 'content_bytes': total,
        'files': [{'path': item.path, 'git_mode': item.git_mode,
                   'archive_mode': '100644', 'git_blob': item.oid,
                   'bytes': len(item.content),
                   'sha256': hashlib.sha256(item.content).hexdigest()} for item in files],
    }
    encoded = (json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode('utf-8')
    return Snapshot(commit, tree, tuple(files), encoded)


def archive_bytes(source: Snapshot, limits: Limits = Limits()) -> bytes:
    """ZIP_STORED avoids compressor/version variability; no timestamps leak."""
    _limits(limits)
    members = [(item.path, item.content) for item in source.files] + [(MANIFEST, source.manifest)]
    target = BytesIO()
    with ZipFile(target, 'w', compression=ZIP_STORED, allowZip64=False) as archive:
        for path, content in sorted(members):
            info = ZipInfo(PREFIX + path, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.create_version = info.extract_version = 20
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = ZIP_STORED
            archive.writestr(info, content)
            if target.tell() > limits.archive:
                raise DeliveryError('archive byte limit exceeded')
    result = target.getvalue()
    if len(result) > limits.archive:
        raise DeliveryError('archive byte limit exceeded')
    return result


def _report(source: Snapshot, data: bytes) -> dict:
    return {'schema': SCHEMA, 'source_commit': source.commit, 'source_tree': source.tree,
            'files': len(source.files), 'archive_entries': len(source.files) + 1,
            'content_bytes': sum(len(item.content) for item in source.files),
            'archive_bytes': len(data),
            'archive_sha256': hashlib.sha256(data).hexdigest(),
            'source_only': True, 'windows_exe_verified': False,
            'browser_layout_verified': False, 'user_device_verified': False}


def build(repo: Path, commit: str, output: Path, limits: Limits = Limits()) -> dict:
    source = snapshot(repo, commit, limits)
    data = archive_bytes(source, limits)
    # Exclusive creation rejects files, directories and symlinks without replacing
    # any previous delivery. Validate every source object before opening output.
    stream = output.open('xb')  # Exclusive-open failures must never enter cleanup.
    try:
        with stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        # Include context-manager close/flush failures in rollback (disk full can
        # fail both a write and the subsequent close). Never close before unlink
        # inside this handler, since that could prevent cleanup from running.
        output.unlink()
        raise
    return _report(source, data)


def verify(repo: Path, commit: str, archive: Path, *, extract: Path | None = None,
           limits: Limits = Limits()) -> dict:
    """Compare the entire canonical archive against independently trusted Git.

    No untrusted ZIP parser is needed before verification: extra members,
    changed metadata, corrupt content and a foreign/self-consistent manifest all
    fail the same exact-byte check. Extraction only follows that successful check.
    """
    source = snapshot(repo, commit, limits)
    expected = archive_bytes(source, limits)
    if not stat.S_ISREG(archive.lstat().st_mode):
        raise DeliveryError('archive must be a regular file, not a symlink')
    with archive.open('rb') as stream:
        actual = stream.read(limits.archive + 1)
    if len(actual) > limits.archive:
        raise DeliveryError('archive byte limit exceeded')
    if actual != expected:
        raise DeliveryError('archive differs from the canonical source commit/manifest')
    if extract is not None:
        extract.mkdir()  # Deliberately refuse every pre-existing destination.
        try:
            with ZipFile(BytesIO(actual)) as package:
                for member in package.infolist():
                    destination = extract / member.filename
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open('xb') as stream:
                        stream.write(package.read(member))
                    destination.chmod(0o644)
        except BaseException:
            shutil.rmtree(extract)
            raise
    return _report(source, actual)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('build', 'verify'):
        command = commands.add_parser(name)
        command.add_argument('--repo', required=True, type=Path, help='local Git object database')
        command.add_argument('--commit', required=True, help='independently selected full lowercase commit ID')
        command.add_argument('--output' if name == 'build' else '--archive', required=True, type=Path)
        if name == 'verify':
            command.add_argument('--extract', type=Path, help='new destination directory; never overwritten')
    args = parser.parse_args(argv)
    try:
        result = (build(args.repo, args.commit, args.output) if args.command == 'build'
                  else verify(args.repo, args.commit, args.archive, extract=args.extract))
    except (DeliveryError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f'source delivery failed: {error}\n')
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
