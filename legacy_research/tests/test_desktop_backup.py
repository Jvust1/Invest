import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from invest.server import InvestServer
from invest.data import demo_dataset
from invest.backup import export_backup, restore_backup


class DesktopBackupTests(unittest.TestCase):
    def test_full_roundtrip_and_preserve_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'source'
            s=InvestServer(('127.0.0.1',0),source)
            try:
                dataset=s.state.save_dataset(demo_dataset())
                account=s.ledger.create_account('test',10000)
                raw=export_backup(source)
            finally: s.server_close()
            restored=restore_backup(raw,root/'restored')
            after=InvestServer(('127.0.0.1',0),restored)
            try:
                self.assertEqual(after.state.dataset(dataset['id'])['id'],dataset['id'])
                self.assertEqual(len(after.ledger.list_accounts()),1)
            finally: after.server_close()
            with self.assertRaises(ValueError): restore_backup(raw,source)

    def test_bad_archive_cannot_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w') as z:z.writestr('../evil.sqlite','x')
            dest=Path(tmp)/'restored'
            with self.assertRaises(ValueError):restore_backup(out.getvalue(),dest)
            self.assertFalse(dest.exists())

    def test_hash_mismatch_cannot_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w') as z:
                z.writestr('state.sqlite',b'bad')
                z.writestr('manifest.json',json.dumps({'schema':'invest-private-backup-v1','files':{'state.sqlite':'0'*64}}))
            dest=Path(tmp)/'restored'
            with self.assertRaises(ValueError):restore_backup(out.getvalue(),dest)
            self.assertFalse(dest.exists())
