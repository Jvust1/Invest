"""Versioned source identity for source and frozen builds.

The embedded manifest is a build declaration checked against source and packaged
HTTP output in CI. It is not a signature of live bytecode, a third-party
attestation, or evidence of data validity. The portable manifest separately
covers the EXE, assets and dependencies actually distributed.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sys
from .workspace import digest

SCHEME = 'invest-python-core-source-v2'
NORMALIZATION = 'UTF-8; universal newlines normalized to LF'
MANIFEST_NAME = 'build_identity.json'
MAX_MANIFEST_BYTES = 1024 * 1024
REQUIRED = frozenset({'__init__.py', 'data.py', 'engine.py', 'experiments.py',
    'provenance.py', 'workspace.py', 'review.py', 'fundamentals.py', 'backup.py',
    'server.py', 'workbench_api.py', 'portfolio.py', 'evaluation.py', 'opening.py',
    'provider_validation.py'})
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
HEX40 = re.compile(r'[0-9a-f]{40}\Z')


def source_manifest(root: Path | None = None, source_commit: str | None = None) -> dict:
    """Hash all package Python sources with cross-platform text normalization."""
    root = Path(__file__).resolve().parent if root is None else Path(root)
    files = {}
    try:
        for path in sorted(root.rglob('*.py')):
            relative = path.relative_to(root).as_posix()
            if '__pycache__' in path.parts:
                continue
            if path.is_symlink():
                raise ValueError('代码身份不接受符号链接')
            if path.stat().st_size > 10 * 1024 * 1024:
                raise ValueError('源码文件超出身份校验限制')
            files[relative] = hashlib.sha256(path.read_text(encoding='utf-8').encode('utf-8')).hexdigest()
    except (OSError, UnicodeError) as exc:
        raise ValueError('无法读取完整源码身份') from exc
    result = {'schema': SCHEME, 'normalization': NORMALIZATION, 'files': files,
              'code_identity': digest({'schema': SCHEME, 'files': files}),
              'source_commit': source_commit}
    return validate_manifest(result)


def validate_manifest(value: object, *, require_commit: bool = False) -> dict:
    """Reject empty, incomplete or corrupted declarations instead of hashing {}."""
    if not isinstance(value, dict) or set(value) != {'schema', 'normalization', 'files', 'code_identity', 'source_commit'}:
        raise ValueError('代码身份清单格式错误')
    if value['schema'] != SCHEME or value['normalization'] != NORMALIZATION:
        raise ValueError('代码身份方案或换行口径不匹配')
    files = value['files']
    if not isinstance(files, dict) or not 1 <= len(files) <= 1000 or not REQUIRED.issubset(files):
        raise ValueError('代码身份清单为空或缺少核心模块')
    for name, sha in files.items():
        if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*(?:/[A-Za-z_][A-Za-z_0-9]*)*\.py', name)
                or not isinstance(sha, str) or not HEX64.fullmatch(sha)):
            raise ValueError('代码身份路径或哈希非法')
    if value['code_identity'] != digest({'schema': SCHEME, 'files': files}):
        raise ValueError('代码身份清单校验失败')
    commit = value['source_commit']
    if commit is not None and (not isinstance(commit, str) or not HEX40.fullmatch(commit)):
        raise ValueError('源码提交身份格式错误')
    if require_commit and commit is None:
        raise ValueError('打包版本缺少源码提交身份')
    return value


def runtime_manifest() -> dict:
    if not getattr(sys, 'frozen', False):
        return source_manifest()
    path = Path(__file__).resolve().parent / MANIFEST_NAME
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError('打包源码身份清单过大')
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('打包源码身份缺失或不可读；请使用完整的新版便携包') from exc
    return validate_manifest(value, require_commit=True)


def code_identity() -> str:
    return runtime_manifest()['code_identity']
