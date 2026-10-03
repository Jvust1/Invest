"""Bounded connection diagnostics; configuration is never connection evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
from urllib.error import HTTPError, URLError

from .connectors import ConnectorError, DriveClient, GitHubClient, REPOSITORY, REPOSITORY_ID

MAX_CATALOG_BYTES = 64 * 1024 * 1024
MAX_SQLITE_STEPS = 2_000_000
RESOURCE_COLUMNS = {'id', 'title', 'content', 'source', 'url', 'sha256', 'provenance', 'license_note'}
_PASS_STATUSES = {'not_configured', 'not_checked', 'healthy', 'connected'}


def _failure(exc: Exception) -> str:
    """Only classify known failure signals; never render an exception or its payload."""
    code = exc.code if isinstance(exc, HTTPError) else None
    if isinstance(exc, ConnectorError):
        args = BaseException.args.__get__(exc)
        message = args[0] if args and type(args[0]) is str else ''
        match = re.fullmatch(r'provider HTTP ([0-9]{3}); no provider response body or credentials logged', message)
        if match:
            code = int(match.group(1))
        elif message == 'provider connection failed or timed out; no implicit fallback':
            return 'network_error_or_timeout'
        elif message == 'provider response exceeds configured size limit':
            return 'response_too_large'
        elif message == 'repository identity changed; refresh configuration explicitly':
            return 'repository_identity_mismatch'
        elif message == 'Drive OAuth token refresh failed':
            return 'authentication_failed'
    if type(code) is int:
        if code == 401:
            return 'authentication_failed'
        if code == 403:
            return 'permission_denied'
        if code == 404:
            return 'resource_not_found'
        if code == 429:
            return 'rate_limited'
        if 500 <= code <= 599:
            return 'provider_unavailable'
        return 'provider_http_error'
    if isinstance(exc, TimeoutError):
        return 'timeout'
    if isinstance(exc, (URLError, ConnectionError, OSError)):
        return 'network_error'
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return 'invalid_response'
    return 'provider_error'


def _signature(value):
    return value.st_size, value.st_mtime_ns, value.st_ino, value.st_dev


def _active_journal(path):
    return any(sidecar.exists() and sidecar.stat().st_size
               for sidecar in (Path(str(path) + suffix) for suffix in ('-wal', '-journal')))


def _catalog_check(catalog) -> dict:
    result = {'configured': catalog is not None, 'status': 'not_configured',
              'network_attempted': False, 'read_only': True,
              'freshness_verified': False, 'content_truth_verified': False,
              'metadata_note': 'File hash and filesystem mtime identify a storage snapshot, not source-data freshness.'}
    if catalog is None:
        return result
    try:
        path = Path(catalog.path)
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            result['status'] = 'invalid_file'
            return result
        result.update(size_bytes=before.st_size,
                      modified_time_utc=datetime.fromtimestamp(before.st_mtime, timezone.utc).isoformat())
        if before.st_size == 0:
            result['status'] = 'empty_file'
            return result
        if before.st_size > MAX_CATALOG_BYTES:
            result['status'] = 'size_limit_exceeded'
            return result
        # An active WAL/journal is not covered by the main-file digest. Do not claim
        # integrity of that snapshot or create SQLite sidecars during this check.
        if _active_journal(path):
            result['status'] = 'active_database_unsupported'
            return result
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            if stream.read(16) != b'SQLite format 3\x00':
                result['status'] = 'corrupt'
                return result
            stream.seek(0)
            remaining = MAX_CATALOG_BYTES + 1
            while remaining:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                digest.update(chunk)
                remaining -= len(chunk)
            if remaining == 0:
                result['status'] = 'size_limit_exceeded'
                return result
        result['sha256'] = digest.hexdigest()
        db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True, timeout=1)
        steps = 0

        def bounded_work():
            nonlocal steps
            steps += 1000
            return int(steps > MAX_SQLITE_STEPS)

        try:
            db.set_progress_handler(bounded_work, 1000)
            db.execute('PRAGMA query_only=ON')
            db.execute('PRAGMA trusted_schema=OFF')
            if db.execute('PRAGMA quick_check(1)').fetchall() != [('ok',)]:
                result['status'] = 'corrupt'
                return result
            if db.execute("SELECT type FROM sqlite_master WHERE name='resources'").fetchall() != [('table',)]:
                result['status'] = 'invalid_schema'
                return result
            columns = db.execute('PRAGMA table_xinfo(resources)').fetchall()
            if (len(columns) != len(RESOURCE_COLUMNS)
                    or {row[1] for row in columns} != RESOURCE_COLUMNS
                    or any(row[2].upper() != 'TEXT' or row[6] != 0 for row in columns)
                    or any(row[5] != (1 if row[1] == 'id' else 0) for row in columns)):
                result['status'] = 'invalid_schema'
                return result
            total, github, drive = db.execute(
                "SELECT count(*), coalesce(sum(source COLLATE BINARY='github'),0), "
                "coalesce(sum(source COLLATE BINARY='drive'),0) FROM resources").fetchone()
            result.update(quick_check='ok', schema='resources-v1',
                          counts={'total': total, 'github': github, 'drive': drive,
                                  'unsupported_source': total - github - drive},
                          empty=total == 0)
            result['status'] = 'healthy' if total == github + drive else 'invalid_source_metadata'
        finally:
            db.close()
        if _signature(before) != _signature(path.stat()) or _active_journal(path):
            result['status'] = 'changed_during_check'
            result.pop('sha256', None)
        return result
    except FileNotFoundError:
        result['status'] = 'missing'
    except PermissionError:
        result['status'] = 'unreadable'
    except sqlite3.DatabaseError as exc:
        # sqlite_errorcode is numeric metadata, unlike provider-controlled messages.
        result['status'] = 'work_limit_exceeded' if getattr(exc, 'sqlite_errorcode', None) == sqlite3.SQLITE_INTERRUPT else 'corrupt'
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        result['status'] = 'invalid_file'
    return result


def _github_check(client, include_network: bool) -> dict:
    result = {'configured': True, 'status': 'not_checked', 'network_attempted': False,
              'repository': REPOSITORY, 'repository_id': REPOSITORY_ID,
              'authentication_configured': bool(os.environ.get('INVEST_GITHUB_TOKEN'))}
    if not include_network:
        return result
    result['network_attempted'] = True
    try:
        sha = client.resolve()
        if type(sha) is not str or not re.fullmatch('[a-f0-9]{40}', sha):
            raise ValueError('invalid commit')
        result.update(status='connected', commit=sha, connection_scope='bound repository metadata and configured ref only')
    except Exception as exc:
        result.update(status='failed', error_category=_failure(exc))
    return result


def _drive_check(client, include_network: bool) -> dict:
    result = {'configured': False, 'status': 'not_configured', 'network_attempted': False,
              'complete_drive_scan': False}
    try:
        configured = client.configured
        if type(configured) is not bool:
            raise ValueError('invalid configured flag')
        result['configured'] = configured
        if not configured:
            return result
        folders = client.folders
        if (not isinstance(folders, (tuple, list)) or not 1 <= len(folders) <= 10
                or any(type(folder) is not str or not re.fullmatch('[A-Za-z0-9_-]{10,100}', folder) for folder in folders)):
            raise ValueError('invalid configured folders')
        result.update(status='not_checked', configured_folder_count=len(folders))
        if not include_network:
            return result
        errors, succeeded = [], 0
        for index, folder in enumerate(folders):
            result['network_attempted'] = True
            try:
                listing = client.list_files(folder, limit=1)
                if (type(listing) is not dict or listing.get('folder_id') != folder
                        or type(listing.get('files')) is not list or len(listing['files']) > 1
                        or any(type(item) is not dict for item in listing['files'])
                        or (listing.get('next_page_token') is not None
                            and (type(listing['next_page_token']) is not str or len(listing['next_page_token']) > 2000))):
                    raise ValueError('invalid listing')
                succeeded += 1
            except Exception as exc:
                errors.append({'folder_index': index, 'error_category': _failure(exc)})
        result.update(status='connected' if not errors else ('partial' if succeeded else 'failed'),
                      checked_folder_count=len(folders), accessible_folder_count=succeeded,
                      connection_scope='allowlisted root metadata and one listing page per root only')
        if errors:
            result['errors'] = errors
    except Exception:
        result.update(status='configuration_error', error_category='invalid_configuration')
    return result


def connection_check(*, catalog=None, github=None, drive=None, include_network=False) -> dict:
    """Check current configured clients; false is strictly offline and paths stay private.

    Pass the service's Catalog/GitHubClient/DriveClient instances. ``checks_passed``
    means executed diagnostics were healthy, not that optional sources are configured
    or that ordinary Chat, current market prices, or investment outcomes are verified.
    """
    if type(include_network) is not bool:
        raise ValueError('include_network must be boolean')
    components = {'catalog': _catalog_check(catalog)}
    try:
        components['github'] = _github_check(github if github is not None else GitHubClient(), include_network)
    except Exception:
        components['github'] = {'configured': False, 'status': 'configuration_error',
                                'network_attempted': False, 'error_category': 'invalid_configuration'}
    try:
        components['drive'] = _drive_check(drive if drive is not None else DriveClient(), include_network)
    except Exception:
        components['drive'] = {'configured': False, 'status': 'configuration_error',
                               'network_attempted': False, 'error_category': 'invalid_configuration'}
    passed = all(item['status'] in _PASS_STATUSES for item in components.values())
    both_connected = all(components[name]['status'] == 'connected' for name in ('github', 'drive'))
    any_connected = any(components[name]['status'] in {'connected', 'partial'} for name in ('github', 'drive'))
    overall = ('connected' if both_connected and passed else 'partial' if any_connected
               else 'check_failed' if not passed else 'offline_only' if not include_network else 'not_connected')
    return {'schema': 'invest-connection-check-v1', 'include_network': include_network,
            'network_attempted': any(item['network_attempted'] for item in components.values()),
            'overall_status': overall, 'checks_passed': passed, 'components': components,
            'checked_at_utc': datetime.now(timezone.utc).isoformat(),
            'credentials_exposed': False, 'private_paths_exposed': False,
            'chat_acceptance_verified': False, 'live_market_data_verified': False,
            'broker_connected': False, 'automatic_orders_supported': False,
            'note': 'Healthy checks do not imply untested sources are connected; file mtime is not data freshness.'}
