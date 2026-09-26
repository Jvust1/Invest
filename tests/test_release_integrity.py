"""Regression cases for capacity, round-trip backup limits and import side effects."""
from contextlib import closing
import importlib.util
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from invest import backup
from invest.workspace import Workspace, canonical, digest

ROOT=Path(__file__).resolve().parents[1]

class ReleaseIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def full_workspace(self):
        ws=Workspace(self.root/'events.sqlite')
        event={'reason':'synthetic capacity boundary'}
        previous='0'*64
        rows=[]
        for n in range(1,10001):
            record={'stream':'synthetic','sequence':n,'event_key':f'key-{n}',
                    'event':event,'previous_hash':previous,'recorded_at':'2026-01-01T00:00:00+00:00'}
            h=digest(record)
            rows.append(('synthetic',n,record['event_key'],canonical(event),previous,h,record['recorded_at']))
            previous=h
        with ws.connection() as db:
            db.execute('BEGIN')
            db.executemany('INSERT INTO growth_events VALUES(?,?,?,?,?,?,?)',rows)
            db.commit()
        return ws,event

    def test_capacity_retry_returns_original_without_revalidation(self):
        ws,event=self.full_workspace()
        def fail(_):self.fail('committed retry must not invoke new-event validation')
        result=ws.append('synthetic','key-10000',event,fail)
        self.assertEqual(result['sequence'],10000)
        self.assertEqual(len(ws.events('synthetic')),10000)

    def test_capacity_new_event_rejected(self):
        ws,event=self.full_workspace()
        with self.assertRaisesRegex(ValueError,'10000'):
            ws.append('synthetic','new',event,lambda _:None)
        self.assertEqual(len(ws.events('synthetic')),10000)

    def test_capacity_conflicting_retry_rejected(self):
        ws,_=self.full_workspace()
        with self.assertRaisesRegex(ValueError,'幂等键'):
            ws.append('synthetic','key-10000',{'reason':'changed'},lambda _:None)
        self.assertEqual(len(ws.events('synthetic')),10000)

    def databases(self):
        for name in backup.DATABASES:
            with closing(sqlite3.connect(self.root/name)) as db:
                db.execute('CREATE TABLE fixture(value TEXT)')
                db.execute("INSERT INTO fixture VALUES('synthetic only')")
                db.commit()
        return sum((self.root/n).stat().st_size for n in backup.DATABASES)

    def test_export_rejects_combined_database_limit(self):
        total=self.databases()
        with patch.object(backup,'LIMIT',total-1):
            with self.assertRaisesRegex(ValueError,'总量'):
                backup.export_backup(self.root)

    def test_export_limit_includes_manifest(self):
        total=self.databases()
        with patch.object(backup,'LIMIT',total+1):
            with self.assertRaisesRegex(ValueError,'清单'):
                backup.export_backup(self.root)

    def test_accepted_backup_round_trips_under_same_limit(self):
        total=self.databases()
        with patch.object(backup,'LIMIT',total+1000):
            raw=backup.export_backup(self.root)
            target=backup.restore_backup(raw,self.root/'restored')
        for name in backup.DATABASES:
            with closing(sqlite3.connect(target/name)) as db:
                self.assertEqual(db.execute('SELECT value FROM fixture').fetchall(),[('synthetic only',)])

    def test_build_module_import_does_not_start_process_or_read_cli(self):
        with patch.dict(os.environ,{},clear=True), patch('subprocess.run') as run, patch('subprocess.Popen') as popen:
            spec=importlib.util.spec_from_file_location('build_safe_import',ROOT/'tools/build_windows_delivery.py')
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertTrue(callable(module.main))
            run.assert_not_called();popen.assert_not_called()

    def test_browser_module_import_does_not_start_process_or_read_cli(self):
        with patch.dict(os.environ,{},clear=True), patch('subprocess.Popen') as popen:
            spec=importlib.util.spec_from_file_location('browser_safe_import',ROOT/'tools/desktop_browser_test.py')
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertTrue(callable(module.main))
            popen.assert_not_called()

if __name__=='__main__':unittest.main()
