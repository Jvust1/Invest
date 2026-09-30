"""Safety and isolation contracts for the real installed-wheel smoke runner."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile


def load_smoke():
    path = Path(__file__).resolve().parents[1] / 'tools' / 'wheel_smoke.py'
    spec = importlib.util.spec_from_file_location('wheel_smoke_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WheelSmokeTests(unittest.TestCase):
    def test_import_does_not_install_or_start_server(self):
        with patch('subprocess.run') as run:
            module = load_smoke()
        self.assertTrue(callable(module.main))
        run.assert_not_called()

    def test_missing_assets_fail_before_installation(self):
        module = load_smoke()
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / 'invest-0.1-py3-none-any.whl'
            with ZipFile(wheel, 'w') as archive:
                archive.writestr('invest/__init__.py', '')
            with patch('subprocess.run') as run, self.assertRaisesRegex(ValueError, 'runtime assets'):
                module.main([str(wheel)])
            run.assert_not_called()

    def test_ambiguous_distribution_directory_fails_before_installation(self):
        module = load_smoke()
        with tempfile.TemporaryDirectory() as directory:
            for name in ('invest-0.1.whl', 'invest-0.2.whl'):
                (Path(directory) / name).touch()
            with patch('subprocess.run') as run, self.assertRaises(SystemExit):
                module.main([directory])
            run.assert_not_called()

    def test_installer_and_child_are_isolated_without_dependency_downloads(self):
        module = load_smoke()
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / 'invest-0.1-py3-none-any.whl'
            with ZipFile(wheel, 'w') as archive:
                for name in module.REQUIRED_ASSETS:
                    archive.writestr(name, '')
            result = subprocess.CompletedProcess([], 0, json.dumps({'contract_test': True}), '')
            with patch('subprocess.run', return_value=result) as run:
                module.main([str(wheel)])
            install, child = [call.args[0] for call in run.call_args_list]
            self.assertIn('--no-index', install)
            self.assertIn('--no-deps', install)
            self.assertIn('--target', install)
            self.assertEqual(child[1:3], ['-I', '-c'])
            self.assertTrue(all(call.kwargs['timeout'] == 90 for call in run.call_args_list))


if __name__ == '__main__':
    unittest.main()
