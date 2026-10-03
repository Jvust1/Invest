import importlib.util
import json
import math
import unittest
from unittest.mock import patch

from invest.opensource import PROFILES, integration_catalog, run_integration
from invest.chat.service import InvestService, TOOL_NAMES

VALUES = [100 + .1*i + math.sin(i*.7) for i in range(64)]
AS_OF = '2026-09-28'


class ResearchContractTests(unittest.TestCase):
    def test_catalog_has_fixed_eleven_no_implicit_execution(self):
        with patch('invest.opensource.common.importlib.import_module') as importer:
            result = integration_catalog()
        importer.assert_not_called()
        self.assertEqual(result['count'], 11)
        self.assertEqual({r['backend'] for r in result['integrations']}, set(PROFILES))
        self.assertTrue(all(r['runtime_execution_verified'] is False for r in result['integrations']))
        self.assertFalse(result['automatic_installation'])

    def test_bad_backend_and_metadata_rejected_before_import(self):
        for name in ['os.system', '../foo', [], None]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                run_integration(name, {'values': VALUES}, source='fixture', as_of=AS_OF)
        for source in ['', ' ', 'x'*301, ' '*301+'x', '\nsecret', None]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                run_integration('scipy', {'values': VALUES}, source=source, as_of=AS_OF)
        for day in ['2099-01-01', '20260928', '2026-09-28T00:00:00', None]:
            with self.subTest(day=day), self.assertRaises(ValueError):
                run_integration('scipy', {'values': VALUES}, source='fixture', as_of=day)

    def test_real_scipy_has_bound_provenance(self):
        service = InvestService()
        result = service.research_run('scipy', VALUES, 'fixture', AS_OF)
        same = service.research_run('scipy', VALUES, 'fixture', AS_OF)
        other = service.research_run('scipy', VALUES, 'different', AS_OF)
        self.assertEqual(result['input_sha256'], same['input_sha256'])
        self.assertNotEqual(result['input_sha256'], other['input_sha256'])
        self.assertEqual(result['status'], 'SCENARIO_ONLY')
        self.assertFalse(result['network_attempted'])
        self.assertFalse(result['execution_authorized'])
        json.dumps(result, allow_nan=False)
        self.assertEqual(len(TOOL_NAMES), 18)

    def test_wrapper_rejects_backend_nonfinite(self):
        with patch('invest.opensource.statistics.run', return_value={'bad': float('nan')}):
            with self.assertRaisesRegex(ValueError, 'non-finite'):
                run_integration('scipy', {'values': VALUES}, source='fixture', as_of=AS_OF)


class ResearchMCPTests(unittest.TestCase):
    def test_actual_http_protocol_and_no_bool_coercion(self):
        from starlette.testclient import TestClient
        from invest.chat.mcp_server import build_server
        with TestClient(build_server().streamable_http_app()) as client:
            headers = {'Accept': 'application/json, text/event-stream'}
            def call(name, arguments):
                response = client.post('/mcp', headers=headers, json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':arguments}})
                self.assertEqual(response.status_code, 200)
                return response.json()['result']
            catalog = call('research_catalog', {})
            self.assertFalse(catalog['isError'])
            self.assertEqual(catalog['structuredContent']['count'], 11)
            arguments = {'backend':'scipy','values':VALUES,'source':'fixture','as_of':AS_OF}
            result = call('research_run', arguments)
            self.assertFalse(result['isError'])
            self.assertTrue(result['structuredContent']['backend_executed'])
            arguments['values'] = [True] + VALUES[1:]
            self.assertTrue(call('research_run', arguments)['isError'])
            arguments['values'] = ['100'] + VALUES[1:]
            self.assertTrue(call('research_run', arguments)['isError'])
            arguments['backend'] = 'eval'
            self.assertTrue(call('research_run', arguments)['isError'])
