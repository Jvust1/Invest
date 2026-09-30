from pathlib import Path
import importlib.util
import tempfile
import unittest

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('desktop_runtime_tests',root/'desktop_runtime.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)


class DesktopRuntimeTests(unittest.TestCase):
    def test_single_instance_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock=runtime.InstanceLock(Path(tmp))
            try:
                with self.assertRaises(RuntimeError):runtime.InstanceLock(Path(tmp))
            finally:lock.close()
            second=runtime.InstanceLock(Path(tmp));second.close()

    def test_browser_rejects_remote_url(self):
        with self.assertRaises(ValueError):runtime.open_app('https://external.invalid/')


if __name__=='__main__':unittest.main()
