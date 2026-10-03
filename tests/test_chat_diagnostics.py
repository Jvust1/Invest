import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from invest.chat.catalog import Catalog
from invest.chat.connectors import ConnectorError
from invest.chat.diagnostics import connection_check


FOLDERS = ('15ypjgfIv3Xl0BWlxcEVm4OvP9XoyK30u', '1oU0O8bQDy6yaIZoQdblf1goui8laOi1I')
SHA = 'ab' * 20
SECRET = 'TOP_SECRET_TOKEN_or_private_document_body'


class DangerousError(RuntimeError):
    def __str__(self):
        raise AssertionError('Never stringify untrusted exceptions')


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog = Catalog(self.root / 'private.sqlite')
        self.github = Mock()
        self.github.resolve.return_value = SHA
        self.drive = Mock()
        self.drive.configured = True
        self.drive.folders = FOLDERS
        self.drive.list_files.side_effect = lambda folder, limit: {
            'files': [], 'folder_id': folder, 'next_page_token': None}
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def check(self, **kwargs):
        return connection_check(github=self.github, drive=self.drive, **kwargs)

    def seed(self):
        self.catalog.add(title='private-title', content=SECRET, source='drive',
                         url='https://drive.google.com/file/d/example/view')
        self.catalog.add(title='public-code', content='source', source='github',
                         url='https://github.com/Jvust1/Invest/blob/main/README.md')

    def component(self, result, name):
        return result['components'][name]

    def assert_private(self, result):
        raw = json.dumps(result)
        self.assertNotIn(SECRET, raw)
        self.assertNotIn('private-title', raw)
        self.assertNotIn(str(self.root), raw)
        self.assertNotIn('private.sqlite', raw)

    def test_default_is_completely_offline(self):
        with patch('invest.chat.connectors.request_bytes', side_effect=AssertionError('network forbidden')):
            result = self.check()
        self.github.resolve.assert_not_called()
        self.drive.list_files.assert_not_called()
        self.assertFalse(result['network_attempted'])
        self.assertEqual(result['overall_status'], 'offline_only')
        self.assertTrue(result['checks_passed'])
        self.assertEqual(self.component(result, 'github')['status'], 'not_checked')
        self.assertEqual(self.component(result, 'drive')['status'], 'not_checked')

    def test_default_clients_do_not_network(self):
        with patch('invest.chat.connectors.request_bytes', side_effect=AssertionError('network forbidden')):
            result = connection_check()
        self.assertEqual(self.component(result, 'drive')['status'], 'not_configured')
        self.assertTrue(result['checks_passed'])

    def test_bool_flag_requires_literal_boolean_before_any_work(self):
        for value in (0, 1, None, 'false', 'true', [], {}, 0.0):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'must be boolean'):
                self.check(include_network=value)
        self.github.resolve.assert_not_called()
        self.drive.list_files.assert_not_called()

    def test_healthy_catalog_read_only_hash_counts_and_no_private_leak(self):
        self.seed()
        before = self.catalog.path.read_bytes()
        listing = sorted(path.name for path in self.root.iterdir())
        result = self.check(catalog=self.catalog)
        item = self.component(result, 'catalog')
        self.assertEqual(item['status'], 'healthy')
        self.assertEqual(item['counts'], {'total': 2, 'github': 1, 'drive': 1, 'unsupported_source': 0})
        self.assertEqual(item['sha256'], hashlib.sha256(before).hexdigest())
        self.assertTrue(item['modified_time_utc'].endswith('+00:00'))
        self.assertEqual(item['quick_check'], 'ok')
        self.assertTrue(item['read_only'])
        self.assertFalse(item['freshness_verified'])
        self.assertFalse(item['content_truth_verified'])
        self.assertFalse(item['empty'])
        self.assertIn('not source-data freshness', item['metadata_note'])
        self.assertEqual(self.catalog.path.read_bytes(), before)
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), listing)
        self.assert_private(result)

    def test_missing_catalog_not_created(self):
        result = self.check(catalog=self.catalog)
        self.assertEqual(self.component(result, 'catalog')['status'], 'missing')
        self.assertFalse(self.catalog.path.exists())
        self.assertFalse(result['checks_passed'])
        self.assert_private(result)

    def test_permission_error_is_sanitized(self):
        with patch('invest.chat.diagnostics.Path.stat', side_effect=PermissionError(SECRET)):
            result = self.check(catalog=self.catalog)
        self.assertEqual(self.component(result, 'catalog')['status'], 'unreadable')
        self.assertFalse(result['checks_passed'])
        self.assert_private(result)

    def test_changed_catalog_snapshot_cannot_retain_validated_digest(self):
        self.seed()
        with patch('invest.chat.diagnostics._signature', side_effect=[(1, 2), (3, 4)]):
            result = self.check(catalog=self.catalog)
        item = self.component(result, 'catalog')
        self.assertEqual(item['status'], 'changed_during_check')
        self.assertNotIn('sha256', item)
        self.assertFalse(result['checks_passed'])

    def test_new_journal_after_inspection_cannot_retain_validated_digest(self):
        self.seed()
        with patch('invest.chat.diagnostics._active_journal', side_effect=[False, True]):
            result = self.check(catalog=self.catalog)
        self.assertEqual(self.component(result, 'catalog')['status'], 'changed_during_check')
        self.assertNotIn('sha256', self.component(result, 'catalog'))

    def test_no_catalog_configuration_is_not_an_error(self):
        result = self.check()
        self.assertEqual(self.component(result, 'catalog')['status'], 'not_configured')
        self.assertTrue(result['checks_passed'])

    def test_directory_is_not_catalog(self):
        self.catalog.path.mkdir()
        result = self.check(catalog=self.catalog)
        self.assertEqual(self.component(result, 'catalog')['status'], 'invalid_file')
        self.assertFalse(result['checks_passed'])

    def test_empty_file(self):
        self.catalog.path.touch()
        result = self.check(catalog=self.catalog)
        self.assertEqual(self.component(result, 'catalog')['status'], 'empty_file')
        self.assertFalse(result['checks_passed'])

    def test_empty_valid_resources_table_is_healthy_but_identified_empty(self):
        self.seed()
        with self.catalog.connection(writable=True) as db:
            db.execute('DELETE FROM resources')
        result = self.check(catalog=self.catalog)
        item = self.component(result, 'catalog')
        self.assertEqual(item['status'], 'healthy')
        self.assertEqual(item['counts']['total'], 0)
        self.assertTrue(item['empty'])

    def test_non_sqlite_and_corrupt_sqlite_do_not_leak(self):
        for raw in (SECRET.encode(), b'SQLite format 3\x00' + SECRET.encode() * 100):
            with self.subTest(raw=raw[:16]):
                self.catalog.path.write_bytes(raw)
                result = self.check(catalog=self.catalog)
                self.assertEqual(self.component(result, 'catalog')['status'], 'corrupt')
                self.assertFalse(result['checks_passed'])
                self.assert_private(result)

    def test_oversized_file_is_rejected_before_open_or_sqlite(self):
        self.catalog.path.write_bytes(b'a' * 16)
        with patch('invest.chat.diagnostics.MAX_CATALOG_BYTES', 10), patch('invest.chat.diagnostics.sqlite3.connect') as connect:
            result = self.check(catalog=self.catalog)
        self.assertEqual(self.component(result, 'catalog')['status'], 'size_limit_exceeded')
        connect.assert_not_called()

    def test_missing_schema(self):
        with closing(sqlite3.connect(self.catalog.path)) as db:
            db.execute('CREATE TABLE unrelated (a TEXT)')
        result = self.check(catalog=self.catalog)
        self.assertEqual(self.component(result, 'catalog')['status'], 'invalid_schema')

    def test_missing_columns_wrong_types_and_views_rejected(self):
        schemas = ['CREATE TABLE resources(id TEXT PRIMARY KEY, content TEXT)',
                   'CREATE TABLE resources(id INTEGER PRIMARY KEY,title TEXT,content TEXT,source TEXT,url TEXT,sha256 TEXT,provenance TEXT,license_note TEXT)',
                   'CREATE VIEW resources AS SELECT 1 AS id']
        for index, statement in enumerate(schemas):
            catalog = Catalog(self.root / ('schema' + str(index) + '.sqlite'))
            with closing(sqlite3.connect(catalog.path)) as db:
                db.execute(statement)
            result = self.check(catalog=catalog)
            self.assertEqual(self.component(result, 'catalog')['status'], 'invalid_schema')

    def test_unknown_source_metadata_does_not_return_malicious_source_value(self):
        self.seed()
        with self.catalog.connection(writable=True) as db:
            db.execute('UPDATE resources SET source=? WHERE source=?', (SECRET, 'drive'))
        result = self.check(catalog=self.catalog)
        item = self.component(result, 'catalog')
        self.assertEqual(item['status'], 'invalid_source_metadata')
        self.assertEqual(item['counts']['unsupported_source'], 1)
        self.assertFalse(result['checks_passed'])
        self.assert_private(result)

    def test_active_sidecars_fail_closed_without_modification(self):
        self.seed()
        for suffix in ('-wal', '-journal'):
            with self.subTest(suffix=suffix):
                sidecar = Path(str(self.catalog.path) + suffix)
                sidecar.write_bytes(SECRET.encode())
                before = self.catalog.path.read_bytes()
                result = self.check(catalog=self.catalog)
                self.assertEqual(self.component(result, 'catalog')['status'], 'active_database_unsupported')
                self.assertEqual(self.catalog.path.read_bytes(), before)
                self.assertEqual(sidecar.read_bytes(), SECRET.encode())
                self.assert_private(result)
                sidecar.unlink()

    def test_sqlite_connection_is_read_only_immutable(self):
        self.seed()
        real_connect = sqlite3.connect
        with patch('invest.chat.diagnostics.sqlite3.connect', wraps=real_connect) as connect:
            self.check(catalog=self.catalog)
        self.assertTrue(connect.call_args.args[0].endswith('?mode=ro&immutable=1'))
        self.assertTrue(connect.call_args.kwargs['uri'])

    def test_sqlite_work_is_bounded(self):
        self.seed()
        with self.catalog.connection(writable=True) as db:
            db.executemany('INSERT INTO resources VALUES(?,?,?,?,?,?,?,?)',
                           [(str(i), 't', 'c', 'github', 'u', 'h', '{}', 'x') for i in range(500)])
        with patch('invest.chat.diagnostics.MAX_SQLITE_STEPS', 0):
            result = self.check(catalog=self.catalog)
        self.assertEqual(self.component(result, 'catalog')['status'], 'work_limit_exceeded')

    def test_both_network_checks_connected_are_not_chat_or_market_acceptance(self):
        result = self.check(include_network=True)
        self.github.resolve.assert_called_once_with()
        self.assertEqual(self.drive.list_files.call_count, 2)
        for call in self.drive.list_files.call_args_list:
            self.assertEqual(call.kwargs, {'limit': 1})
        self.assertEqual(result['overall_status'], 'connected')
        self.assertTrue(result['checks_passed'])
        self.assertTrue(result['network_attempted'])
        self.assertFalse(result['chat_acceptance_verified'])
        self.assertFalse(result['live_market_data_verified'])
        self.assertFalse(result['broker_connected'])
        self.assertFalse(result['automatic_orders_supported'])
        self.assertFalse(self.component(result, 'drive')['complete_drive_scan'])

    def test_unconfigured_drive_is_not_called_and_not_connected(self):
        self.drive.configured = False
        result = self.check(include_network=True)
        self.drive.list_files.assert_not_called()
        self.assertEqual(self.component(result, 'drive')['status'], 'not_configured')
        self.assertEqual(result['overall_status'], 'partial')
        self.assertTrue(result['checks_passed'])

    def test_partial_network_access_never_claims_overall_connected(self):
        self.drive.list_files.side_effect = [{'files': [], 'folder_id': FOLDERS[0]}, ConnectorError(SECRET)]
        result = self.check(include_network=True)
        item = self.component(result, 'drive')
        self.assertEqual(item['status'], 'partial')
        self.assertEqual(item['accessible_folder_count'], 1)
        self.assertEqual(result['overall_status'], 'partial')
        self.assertFalse(result['checks_passed'])
        self.assert_private(result)

    def test_bad_catalog_prevents_overall_connected(self):
        result = self.check(catalog=self.catalog, include_network=True)
        self.assertEqual(result['overall_status'], 'partial')
        self.assertFalse(result['checks_passed'])

    def test_provider_failures_are_safely_classified(self):
        cases = [(401, 'authentication_failed'), (403, 'permission_denied'), (404, 'resource_not_found'),
                 (429, 'rate_limited'), (503, 'provider_unavailable'), (418, 'provider_http_error')]
        for code, expected in cases:
            with self.subTest(code=code):
                self.github.resolve.side_effect = ConnectorError(
                    f'provider HTTP {code}; no provider response body or credentials logged')
                result = self.check(include_network=True)
                self.assertEqual(self.component(result, 'github')['error_category'], expected)
                self.assertFalse(result['checks_passed'])

    def test_fixed_connector_failure_categories(self):
        cases = [
            ('provider connection failed or timed out; no implicit fallback', 'network_error_or_timeout'),
            ('provider response exceeds configured size limit', 'response_too_large'),
            ('repository identity changed; refresh configuration explicitly', 'repository_identity_mismatch'),
            ('Drive OAuth token refresh failed', 'authentication_failed'),
        ]
        for message, expected in cases:
            self.github.resolve.side_effect = ConnectorError(message)
            result = self.check(include_network=True)
            self.assertEqual(self.component(result, 'github')['error_category'], expected)

    def test_complete_network_failure_is_not_partial_or_connected(self):
        self.github.resolve.side_effect = DangerousError(SECRET)
        self.drive.list_files.side_effect = DangerousError(SECRET)
        result = self.check(include_network=True)
        self.assertEqual(result['overall_status'], 'check_failed')
        self.assertFalse(result['checks_passed'])
        self.assert_private(result)

    def test_raw_exceptions_do_not_leak_messages_or_urls(self):
        cases = [(TimeoutError(SECRET), 'timeout'), (URLError(SECRET), 'network_error'),
                 (HTTPError('https://example.test/' + SECRET, 401, SECRET, {}, None), 'authentication_failed'),
                 (DangerousError(SECRET), 'provider_error'), (ValueError(SECRET), 'invalid_response')]
        for error, expected in cases:
            with self.subTest(type=type(error).__name__):
                self.github.resolve.side_effect = error
                result = self.check(include_network=True)
                self.assertEqual(self.component(result, 'github')['error_category'], expected)
                self.assert_private(result)

    def test_malformed_github_commit_is_not_echoed(self):
        for value in (SECRET, None, {'token': SECRET}, 123, 'Z' * 40):
            self.github.resolve.return_value = value
            result = self.check(include_network=True)
            self.assertEqual(self.component(result, 'github')['status'], 'failed')
            self.assert_private(result)

    def test_malformed_drive_listing_is_not_echoed(self):
        for value in (SECRET, None, {}, {'files': SECRET, 'folder_id': FOLDERS[0]},
                      {'files': [], 'folder_id': SECRET},
                      {'files': [], 'folder_id': FOLDERS[0], 'next_page_token': {'token': SECRET}}):
            self.drive.list_files.side_effect = None
            self.drive.list_files.return_value = value
            result = self.check(include_network=True)
            self.assertEqual(self.component(result, 'drive')['status'], 'failed')
            self.assert_private(result)

    def test_provider_listing_body_is_never_returned(self):
        self.drive.list_files.side_effect = lambda folder, limit: {
            'files': [{'title': SECRET, 'content': SECRET}], 'folder_id': folder, 'next_page_token': SECRET}
        result = self.check(include_network=True)
        self.assertEqual(self.component(result, 'drive')['status'], 'connected')
        self.assert_private(result)

    def test_invalid_drive_configuration_does_not_attempt_network(self):
        for configured, folders in [(1, FOLDERS), (True, [SECRET + '/']), (True, []), (True, FOLDERS * 6)]:
            self.drive.configured = configured
            self.drive.folders = folders
            result = self.check(include_network=True)
            self.assertEqual(self.component(result, 'drive')['status'], 'configuration_error')
            self.assertFalse(result['checks_passed'])
        self.drive.list_files.assert_not_called()

    def test_constructor_configuration_error_is_sanitized(self):
        with patch.dict(os.environ, {'INVEST_GITHUB_REF': SECRET + ':'}):
            result = connection_check(drive=self.drive)
        self.assertEqual(self.component(result, 'github')['status'], 'configuration_error')
        self.assert_private(result)

    def test_configured_token_is_not_exposed_and_does_not_imply_connection(self):
        with patch.dict(os.environ, {'INVEST_GITHUB_TOKEN': SECRET, 'INVEST_GOOGLE_ACCESS_TOKEN': SECRET}):
            result = connection_check()
        self.assertTrue(self.component(result, 'github')['authentication_configured'])
        self.assertTrue(self.component(result, 'drive')['configured'])
        self.assertEqual(result['overall_status'], 'offline_only')
        self.assert_private(result)


if __name__ == '__main__':
    unittest.main()
