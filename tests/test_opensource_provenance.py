"""Cross-file evidence references must survive Git's platform newline policy."""
import hashlib
import json
from pathlib import Path
import unittest


class EvidenceProvenanceTests(unittest.TestCase):
    def test_runtime_evidence_binds_published_upstream_evidence_bytes(self):
        root = Path(__file__).resolve().parents[1]
        runtime = json.loads((root / 'docs/OPEN_SOURCE_RUNTIME_20261003.json').read_text('utf-8'))
        upstream = (root / runtime['upstream_evidence_file']).read_bytes()
        canonical = upstream.replace(b'\r\n', b'\n')
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), runtime['upstream_evidence_sha256'])
        self.assertEqual(hashlib.sha256(canonical.replace(b'\n', b'\r\n')).hexdigest(),
                         runtime['upstream_evidence_observed_input_sha256'])
        self.assertIn('LF', runtime['upstream_evidence_hash_mode'])
