import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('images_validate', ROOT / 'scripts/images/validate.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class Images(unittest.TestCase):
    def setUp(self):
        self.release = json.loads((ROOT / 'release.json').read_text())

    def test_historical_evidence_is_not_recovery(self):
        self.assertEqual([], v.validate_manifest(self.release))
        self.assertTrue(v.validate_manifest(self.release, True))

    def test_registry_config_id_cannot_masquerade_as_digest_reference(self):
        image = self.release['production']['images']['web']
        image['provenance']['registry'] = {'digest': image['local_image_id'], 'reference': image['reference']}
        self.assertTrue(v.validate_manifest(self.release))

    def test_synthetic_archive_and_corruption(self):
        image = copy.deepcopy(self.release['production']['images']['web'])
        config = json.dumps({'os': 'linux', 'architecture': 'amd64'}).encode()
        image['local_image_id'] = 'sha256:' + hashlib.sha256(config).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.tar'
            with tarfile.open(path, 'w') as tar:
                for name, data in [('config.json', config), ('layer.tar', b'fixture'), ('manifest.json', json.dumps([{'Config': 'config.json', 'Layers': ['layer.tar']}]).encode())]:
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))
            image['provenance']['archive'] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'platform': 'linux/amd64'}
            v.validate_archive(path, image)
            with path.open('ab') as stream:
                stream.write(b'changed')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                v.validate_archive(path, image)

    def test_registry_evidence_must_match_platform_and_source(self):
        for role, image in self.release['production']['images'].items():
            p = image['provenance']
            p['platform'] = 'linux/amd64'
            digest = 'sha256:' + '1' * 64
            p['registry'] = {'reference': 'ghcr.io/example/' + ('app' if role == 'scheduler' else role) + '@' + digest, 'digest': digest, 'platform': p['platform'], 'source_revision': p['source_revision'], 'verification': 'retrieved-and-tested'}
        self.assertEqual([], v.validate_manifest(self.release, True))
        self.release['production']['images']['web']['provenance']['registry']['platform'] = 'linux/arm64'
        self.assertTrue(v.validate_manifest(self.release, True))


if __name__ == '__main__':
    unittest.main()
