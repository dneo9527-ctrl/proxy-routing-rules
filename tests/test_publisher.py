"""Exercise rejection, rollback and crash recovery without network or VPS writes."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('publisher', Path(__file__).parents[1] / 'deploy/publisher.py')
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.base = self.root / 'web'
        self.bundle = self.root / 'bundle'
        (self.bundle / 'rules').mkdir(parents=True)
        self.base.mkdir(parents=True)
        self.state = self.root / 'state.json'
        self.data = self.root / 'data'
        self.releases = self.data / 'releases'
        self.state_patch = patch.object(publisher, 'STATE', self.state)
        self.state_patch.start()
        self.base_patch = patch.object(publisher, 'BASE', self.base)
        self.base_patch.start()
        self.data_patch = patch.object(publisher, 'DATA', self.data)
        self.data_patch.start()
        self.releases_patch = patch.object(publisher, 'RELEASES', self.releases)
        self.releases_patch.start()
        self.sha = 'a' * 40
        self.old = {}
        for kind in publisher.KINDS:
            value = ('DOMAIN,%s.invalid\n' % kind).encode()
            self.old[kind] = value
            (self.base / (kind + '.list')).write_bytes(value)
            (self.bundle / 'rules' / (kind + '.list')).write_bytes(value)
        with (self.bundle / 'rules/direct.list').open('ab') as f:
            f.write(b'DOMAIN,example.com\n')
        self.manifest()
        (self.bundle / 'publication.json').write_text(json.dumps({
            'schema': 1, 'source_commit': 'b' * 40, 'workflow_run': 123}))

    def tearDown(self):
        self.state_patch.stop()
        self.base_patch.stop()
        self.data_patch.stop()
        self.releases_patch.stop()
        self.tmp.cleanup()

    def manifest(self):
        rules = {}
        for kind in publisher.KINDS:
            data = (self.bundle / 'rules' / (kind + '.list')).read_bytes()
            rules[kind] = {'path': 'rules/' + kind + '.list',
                           'count': len(data.splitlines()), 'sha256': hashlib.sha256(data).hexdigest()}
        (self.bundle / 'manifest.json').write_text(json.dumps({'schema': 1, 'rules': rules}))

    def publish(self, **kwargs):
        return publisher.publish(self.bundle, self.sha, base=self.base,
                                 verify=kwargs.get('verify', lambda data: None),
                                 ci=kwargs.get('ci', lambda data: None))

    def assert_old(self):
        self.assertFalse(self.state.exists())
        self.assertEqual({k: (self.base / (k + '.list')).read_bytes()
                          for k in publisher.KINDS}, self.old)

    def test_valid_bundle_activates_and_verifies_hashes(self):
        state = self.publish()
        self.assertEqual(state['release_commit'], self.sha)
        self.assertEqual(publisher.verify_current(self.base)['release_commit'], self.sha)
        self.assertTrue(any(p.name.startswith('bootstrap-') for p in self.releases.iterdir()))

    def test_missing_file_never_switches(self):
        (self.bundle / 'rules/reject.list').unlink()
        with self.assertRaises(FileNotFoundError):
            self.publish()
        self.assert_old()

    def test_cross_list_overlap_never_switches(self):
        (self.bundle / 'rules/reject.list').write_text('DOMAIN-SUFFIX,example.com\n')
        self.manifest()
        with self.assertRaisesRegex(ValueError, 'Cross-list'):
            self.publish()
        self.assert_old()

    def test_manifest_mismatch_never_switches(self):
        with (self.bundle / 'rules/direct.list').open('ab') as f:
            f.write(b'DOMAIN,other.example\n')
        with self.assertRaisesRegex(ValueError, 'Manifest mismatch'):
            self.publish()
        self.assert_old()

    def test_symlink_data_rejected(self):
        p = self.bundle / 'rules/direct.list'
        p.unlink()
        p.symlink_to(self.base / 'direct.list')
        with self.assertRaises(OSError):
            self.publish()
        self.assert_old()

    def test_ci_rejection_keeps_old_version(self):
        def fail(_):
            raise ValueError('CI failed')
        with self.assertRaisesRegex(ValueError, 'CI failed'):
            self.publish(ci=fail)
        self.assert_old()

    def test_http_failure_rolls_back(self):
        def fail(_):
            raise ValueError('HTTP mismatch')
        with self.assertRaisesRegex(ValueError, 'HTTP mismatch'):
            self.publish(verify=fail)
        self.assert_old()
        self.assertFalse(self.state.with_name('pending.json').exists())

    def test_incomplete_previous_transaction_is_recovered(self):
        stage = self.root / '.routing-next-interrupted'
        stage.mkdir()
        old_hashes = publisher.hashes(self.base)
        for kind in publisher.KINDS:
            (stage / (kind + '.list')).write_bytes((self.bundle / 'rules' / (kind + '.list')).read_bytes())
        new_hashes = publisher.hashes(stage)
        publisher.exchange(self.base, stage)
        pending = {'stage': str(stage), 'state_before': {}, 'old_hashes': old_hashes, 'new_hashes': new_hashes}
        self.state.with_name('pending.json').write_text(json.dumps(pending))
        publisher.recover(self.base)
        self.assert_old()

    def test_external_rule_edit_is_detected(self):
        self.publish()
        (self.base / 'direct.list').write_text('DOMAIN,altered.example\n')
        with self.assertRaisesRegex(ValueError, 'changed outside GitHub'):
            publisher.verify_current(self.base)

    def test_next_release_preserves_previous(self):
        self.publish()
        self.sha = 'c' * 40
        (self.bundle / 'rules/direct.list').write_text('DOMAIN,direct.invalid\nDOMAIN,new.example\n')
        self.manifest()
        state = self.publish()
        self.assertEqual(state['previous'], 'a' * 40)
        self.assertTrue((self.releases / state['previous'] / 'direct.list').is_file())


if __name__ == '__main__':
    unittest.main()
