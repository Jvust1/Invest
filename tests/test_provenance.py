"""Source/packaged identity contracts; fixtures do not attest live bytecode."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from invest import provenance as p
from invest.workspace import digest

class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for name in p.REQUIRED:
            (self.root/name).write_text('# synthetic source fixture\nx = 1\n',encoding='utf-8')
        self.manifest=p.source_manifest(self.root,source_commit='a'*40)

    def frozen(self):
        return patch.multiple(p, __file__=str(self.root/'provenance.py'))

    def test_identity_nonempty_and_versioned(self):
        self.assertNotEqual(self.manifest['code_identity'],hashlib.sha256(b'{}').hexdigest())
        self.assertEqual(self.manifest['schema'],p.SCHEME)
        self.assertTrue(p.REQUIRED.issubset(self.manifest['files']))

    def test_cross_platform_newlines_have_same_identity(self):
        for path in self.root.glob('*.py'):
            path.write_bytes(path.read_bytes().replace(b'\n',b'\r\n'))
        self.assertEqual(p.source_manifest(self.root)['code_identity'],self.manifest['code_identity'])

    def test_one_source_change_changes_identity(self):
        (self.root/'engine.py').write_text('# different executable source\n',encoding='utf-8')
        self.assertNotEqual(p.source_manifest(self.root)['code_identity'],self.manifest['code_identity'])

    def test_nested_python_module_is_included(self):
        (self.root/'sub').mkdir()
        (self.root/'sub'/'module.py').write_text('x=2\n',encoding='utf-8')
        after=p.source_manifest(self.root)
        self.assertIn('sub/module.py',after['files'])
        self.assertNotEqual(after['code_identity'],self.manifest['code_identity'])

    def test_empty_source_directory_rejected(self):
        empty=self.root/'empty';empty.mkdir()
        with self.assertRaises(ValueError):p.source_manifest(empty)

    def test_missing_required_source_rejected(self):
        (self.root/'engine.py').unlink()
        with self.assertRaises(ValueError):p.source_manifest(self.root)

    def test_malformed_manifest_variants_rejected(self):
        variants=[]
        for field,value in [('schema','old'),('normalization','binary'),('files',{}),
                ('code_identity','0'*64),('source_commit','branch-name')]:
            m=copy.deepcopy(self.manifest);m[field]=value;variants.append(m)
        m=copy.deepcopy(self.manifest);m['files']['../outside.py']='f'*64;variants.append(m)
        m=copy.deepcopy(self.manifest);m['files']['engine.py']='bad';variants.append(m)
        m=copy.deepcopy(self.manifest);del m['files']['engine.py'];variants.append(m)
        m=copy.deepcopy(self.manifest);m['extra']=True;variants.append(m)
        for value in variants+[None,[],True]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):p.validate_manifest(value)

    def test_frozen_build_uses_manifest_without_loose_python_files(self):
        (self.root/p.MANIFEST_NAME).write_text(json.dumps(self.manifest),encoding='utf-8')
        for file in self.root.glob('*.py'):file.unlink()
        with self.frozen(),patch.object(p.sys,'frozen',True,create=True):
            self.assertEqual(p.runtime_manifest(),self.manifest)
            self.assertEqual(p.code_identity(),self.manifest['code_identity'])

    def test_frozen_missing_manifest_is_error_not_empty_hash(self):
        with self.frozen(),patch.object(p.sys,'frozen',True,create=True):
            with self.assertRaisesRegex(ValueError,'缺失'):p.code_identity()

    def test_frozen_missing_source_commit_rejected(self):
        self.manifest['source_commit']=None
        (self.root/p.MANIFEST_NAME).write_text(json.dumps(self.manifest),encoding='utf-8')
        with self.frozen(),patch.object(p.sys,'frozen',True,create=True):
            with self.assertRaisesRegex(ValueError,'提交'):p.code_identity()

    def test_frozen_bad_json_rejected(self):
        (self.root/p.MANIFEST_NAME).write_text('{broken',encoding='utf-8')
        with self.frozen(),patch.object(p.sys,'frozen',True,create=True):
            with self.assertRaises(ValueError):p.code_identity()

    def test_frozen_self_consistent_empty_manifest_rejected(self):
        self.manifest['files']={}
        self.manifest['code_identity']=digest({'schema':p.SCHEME,'files':{}})
        (self.root/p.MANIFEST_NAME).write_text(json.dumps(self.manifest),encoding='utf-8')
        with self.frozen(),patch.object(p.sys,'frozen',True,create=True):
            with self.assertRaisesRegex(ValueError,'为空'):p.code_identity()

    def test_frozen_oversize_manifest_rejected(self):
        (self.root/p.MANIFEST_NAME).write_text(' '*200,encoding='utf-8')
        with self.frozen(),patch.object(p.sys,'frozen',True,create=True),patch.object(p,'MAX_MANIFEST_BYTES',100):
            with self.assertRaisesRegex(ValueError,'过大'):p.code_identity()

    def test_source_mode_does_not_trust_stale_build_manifest(self):
        (self.root/p.MANIFEST_NAME).write_text(json.dumps(self.manifest),encoding='utf-8')
        (self.root/'engine.py').write_text('changed=1\n',encoding='utf-8')
        with self.frozen(),patch.object(p.sys,'frozen',False,create=True):
            self.assertNotEqual(p.code_identity(),self.manifest['code_identity'])

    def test_commit_metadata_not_conflated_with_core_identity(self):
        other=p.source_manifest(self.root,source_commit='b'*40)
        self.assertEqual(other['code_identity'],self.manifest['code_identity'])
        self.assertNotEqual(other['source_commit'],self.manifest['source_commit'])

    def test_non_utf8_source_rejected(self):
        (self.root/'engine.py').write_bytes(b'\xff')
        with self.assertRaises(ValueError):p.source_manifest(self.root)

if __name__=='__main__':unittest.main()
