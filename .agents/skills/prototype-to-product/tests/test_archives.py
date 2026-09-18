"""Synthetic filesystem/record tests. These do not run or certify a real application."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'version_flow.py'
SPEC = importlib.util.spec_from_file_location('archive_current', SCRIPT)
assert SPEC and SPEC.loader
vf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vf)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.f = vf.Flow(self.root)
        self.f.init('v1.0.0', 'Synthetic Test Project')


    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path


    def json(self, relative, value):
        return self.write(relative, json.dumps(value, ensure_ascii=False))


    def spec(self, version='v1.0.0'):
        draft = self.f.draft(version)
        scope = vf.obj(draft / 'scope.json')
        scope.update({'readiness_reviewed': True, 'change_summary': 'Synthetic fixture, not a real product acceptance.'})
        vf.write_json(draft / 'scope.json', scope)
        for meaning, relative in scope['documents'].items():
            p = draft / relative
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f'# {meaning}\n\nSynthetic deterministic test fixture.\n', encoding='utf-8')
        trace = vf.obj(draft / 'traceability.json')
        if not trace['requirements']:
            trace = {'schema_version': 4, 'requirements': [
                {'id': 'REQ-001', 'title': 'Synthetic action', 'since': version, 'change': 'added',
                 'status': 'active', 'spec_refs': ['spec/01-requirements.md'], 'acceptance_ids': ['AC-001']}
            ], 'acceptance': [
                {'id': 'AC-001', 'status': 'active', 'required': True,
                 'requirement_ids': ['REQ-001'], 'spec_refs': ['spec/05-acceptance.md']}
            ]}
        for case in trace['acceptance']:
            case.setdefault('phase', 'backend')
        if not any(case['id'] == 'AC-FIXTURE-F' for case in trace['acceptance']):
            trace['acceptance'].append({
                'id': 'AC-FIXTURE-F', 'status': 'active', 'required': True, 'phase': 'frontend',
                'requirement_ids': ['REQ-001'], 'spec_refs': ['spec/05-acceptance.md']})
            trace['requirements'][0]['acceptance_ids'].append('AC-FIXTURE-F')
        vf.write_json(draft / 'traceability.json', trace)
        vf.write_json(draft / 'quality-gates.json', {'schema_version': 4, 'gates': [
            {'id': 'GATE-REGRESSION', 'required': True, 'phase': 'integration', 'description': 'Synthetic regression gate'}]})
        self.write(f'docs/releases/{version}/draft/contracts/contract.json', '{}')
        return self.f.seal(version)


    def promote(self, version, expected='none', **kwargs):
        return self.f.promote(version, expected, 'SYNTHETIC set current pointer', 'synthetic:test', **kwargs)

    def test_initialization_has_no_approvals_or_release(self):
        s = self.f.state('v1.0.0')
        self.assertEqual(s['stage'], 'DISCOVER')
        self.assertEqual(s['approvals'], [])
        self.assertIsNone(self.f.registry()['current_delivered'])


    def test_cannot_reinitialize(self):
        with self.assertRaises(vf.FlowError): self.f.init('v2.0.0', 'No overwrite')


    def test_unreviewed_draft_cannot_seal(self):
        with self.assertRaisesRegex(vf.FlowError, 'Readiness'): self.f.seal('v1.0.0')


    def test_seal_copies_actual_bytes_without_approval(self):
        r = self.spec()
        self.assertFalse(r['approval_created'])
        self.assertEqual((self.f.snapshot(r['ref']) / 'spec/01-requirements.md').read_bytes(),
                         (self.f.draft('v1.0.0') / 'spec/01-requirements.md').read_bytes())
        self.assertEqual(self.f.state('v1.0.0')['stage'], 'SPECIFY')


    def test_draft_edits_do_not_destroy_history(self):
        r = self.spec()
        (self.f.draft('v1.0.0') / 'spec/01-requirements.md').write_text('new content')
        self.assertTrue(self.f.check(r['ref'])['ok'])
        with self.assertRaisesRegex(vf.FlowError, 'Draft differs'): self.f.check(r['ref'], against_draft=True)


    def test_added_draft_document_detected(self):
        r = self.spec()
        (self.f.draft('v1.0.0') / 'extra.md').write_text('new')
        with self.assertRaisesRegex(vf.FlowError, 'added'): self.f.check(r['ref'], against_draft=True)


    def test_deleted_draft_document_detected(self):
        r = self.spec()
        (self.f.draft('v1.0.0') / 'spec/01-requirements.md').unlink()
        with self.assertRaisesRegex(vf.FlowError, 'deleted'): self.f.check(r['ref'], against_draft=True)


    def test_snapshot_tampering_detected(self):
        r = self.spec()
        (self.f.snapshot(r['ref']) / 'spec/01-requirements.md').write_text('tampered')
        with self.assertRaisesRegex(vf.FlowError, 'Snapshot drift'): self.f.check(r['ref'])


    def test_extra_snapshot_file_detected(self):
        r = self.spec()
        (self.f.snapshot(r['ref']) / 'extra.md').write_text('tampered')
        with self.assertRaisesRegex(vf.FlowError, 'Snapshot drift'): self.f.check(r['ref'])


    def test_manifest_tampering_detected(self):
        r = self.spec()
        p = self.f.snapshot(r['ref']).parent / 'manifest.json'
        p.write_text(p.read_text() + '\n')
        with self.assertRaisesRegex(vf.FlowError, 'Manifest hash'): self.f.check(r['ref'])


    def test_runtime_dependencies_excluded_from_draft_snapshot(self):
        d = self.f.draft('v1.0.0') / 'prototype/node_modules'
        d.mkdir(parents=True)
        (d / '.env').write_text('synthetic only')
        r = self.spec()
        self.assertFalse((self.f.snapshot(r['ref']) / 'prototype/node_modules').exists())


    def test_secret_file_rejected(self):
        (self.f.draft('v1.0.0') / '.env.local').write_text('SYNTHETIC=not-a-real-secret')
        with self.assertRaisesRegex(vf.FlowError, 'secret'): self.spec()


    def test_env_example_allowed(self):
        (self.f.draft('v1.0.0') / '.env.example').write_text('TOKEN=')
        self.assertTrue(self.spec()['ok'])


    def test_symlink_in_authoritative_tree_rejected(self):
        link = self.f.draft('v1.0.0') / 'alias'
        try: link.symlink_to(self.f.draft('v1.0.0') / 'scope.json')
        except OSError: self.skipTest('Symlinks unavailable')
        with self.assertRaisesRegex(vf.FlowError, 'Symlink'): self.spec()


    def test_path_traversal_and_unsafe_labels_rejected(self):
        for name in ('../x', '/tmp/x', 'x/y', 'C:x', 'a\\b', 'CON'):
            with self.subTest(name=name):
                with self.assertRaises(vf.FlowError): self.f.new(name, None)


    def test_new_version_requires_explicit_parent(self):
        with self.assertRaisesRegex(vf.FlowError, 'explicit parent'): self.f.new('v1.1.0', None)


    def test_baseline_approval_does_not_start_build(self):
        r = self.spec()
        self.f.approve(r['ref'], 'baseline', 'SYNTHETIC approve', 'test')
        self.assertEqual(self.f.state('v1.0.0')['stage'], 'READY')
        with self.assertRaises(vf.FlowError): self.f.check(r['ref'], for_build=True)


    def test_blank_approval_quote_rejected(self):
        r = self.spec()
        with self.assertRaises(vf.FlowError): self.f.approve(r['ref'], 'baseline', ' ', 'test')


    def test_new_from_unreleased_rejected_by_default(self):
        r = self.spec()
        with self.assertRaisesRegex(vf.FlowError, 'Parent must be delivered'): self.f.new('v1.1.0', r['ref'])


    def test_switch_does_not_claim_code_checkout(self):
        self.assertFalse(self.f.switch('v1.0.0')['code_checkout_performed'])


    def test_traceability_duplicate_id_rejected(self):
        self.spec()
        trace = vf.obj(self.f.draft('v1.0.0') / 'traceability.json')
        trace['requirements'] *= 2
        vf.write_json(self.f.draft('v1.0.0') / 'traceability.json', trace)
        with self.assertRaisesRegex(vf.FlowError, 'Duplicate'): self.f.seal('v1.0.0')


    def test_traceability_unknown_reference_rejected(self):
        self.spec()
        trace = vf.obj(self.f.draft('v1.0.0') / 'traceability.json')
        trace['requirements'][0]['acceptance_ids'] = ['AC-MISSING']
        vf.write_json(self.f.draft('v1.0.0') / 'traceability.json', trace)
        with self.assertRaises(vf.FlowError): self.f.seal('v1.0.0')


    def test_freeze_rejects_document_path_escape(self):
        self.spec()
        scope = vf.obj(self.f.draft('v1.0.0') / 'scope.json')
        scope['documents']['index'] = '../other.md'
        vf.write_json(self.f.draft('v1.0.0') / 'scope.json', scope)
        with self.assertRaisesRegex(vf.FlowError, 'relative'): self.f.seal('v1.0.0')


    def test_promote_requires_actual_delivery(self):
        self.spec()
        with self.assertRaisesRegex(vf.FlowError, 'no delivery'): self.promote('v1.0.0')


    def test_stage_cannot_bypass_approval_or_delivery(self):
        for target in ('BUILD', 'READY', 'DELIVERED'):
            with self.subTest(target=target):
                with self.assertRaisesRegex(vf.FlowError, 'Invalid stage'): self.f.stage('v1.0.0', target)


    def test_doctor_reports_orphaned_snapshot(self):
        self.spec()
        (self.root / 'docs/releases/v1.0.0/baselines/b099').mkdir()
        d = self.f.doctor()
        self.assertFalse(d['ok'])
        self.assertIn('unregistered baseline', '\n'.join(d['problems']))


    def test_writer_lock_prevents_second_writer(self):
        with vf.writer_lock(self.f):
            with self.assertRaisesRegex(vf.FlowError, 'writer'):
                with vf.writer_lock(self.f): pass
        self.assertFalse((self.root / '.project-flow/.version-flow.lock').exists())


    def test_cli_status_and_controlled_json_error(self):
        p = subprocess.run([sys.executable, str(SCRIPT), 'status', '--root', str(self.root)], text=True, capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)['active_version'], 'v1.0.0')
        self.write('.project-flow/project.json', 'broken-json')
        p = subprocess.run([sys.executable, str(SCRIPT), 'status', '--root', str(self.root)], text=True, capture_output=True)
        self.assertEqual(p.returncode, 1)
        self.assertFalse(json.loads(p.stderr)['ok'])


    def test_index_is_generated_without_new_authoritative_spec(self):
        self.spec()
        result = self.f.index()
        self.assertFalse(result['authoritative'])
        text = (self.root / result['index']).read_text(encoding='utf-8')
        self.assertIn('v1.0.0', text)
        self.assertIn('b001', text)
        self.assertTrue(self.f.index()['ok'])


    def test_index_refuses_overwriting_user_content(self):
        self.write('docs/releases/INDEX.md', 'User-maintained document')
        with self.assertRaisesRegex(vf.FlowError, 'overwrite user content'): self.f.index()
        self.assertEqual((self.root / 'docs/releases/INDEX.md').read_text(), 'User-maintained document')


    def test_export_contains_complete_snapshot_and_manifest(self):
        from zipfile import ZipFile
        ref = self.spec()['ref']
        r = self.f.export(ref, 'exports/spec.zip')
        with ZipFile(self.root / r['output']) as z:
            self.assertIn('v1.0.0-b001/manifest.json', z.namelist())
            self.assertIn('v1.0.0-b001/snapshot/spec/01-requirements.md', z.namelist())
        self.assertFalse(r['production_source_included'])


    def test_export_never_overwrites_existing_file(self):
        ref = self.spec()['ref']
        self.write('exports/existing.zip', 'User content')
        with self.assertRaises(vf.FlowError): self.f.export(ref, 'exports/existing.zip')
        self.assertEqual((self.root / 'exports/existing.zip').read_text(), 'User content')


    def test_export_rejects_snapshot_tree_destination(self):
        ref = self.spec()['ref']
        with self.assertRaises(vf.FlowError): self.f.export(ref, 'docs/releases/v1.0.0/draft/output.zip')


    def test_export_path_traversal_rejected(self):
        ref = self.spec()['ref']
        with self.assertRaises(vf.FlowError): self.f.export(ref, '../export.zip')


    def test_unregistered_incorporated_ref_rejected(self):
        self.spec()
        scope = vf.obj(self.f.draft('v1.0.0') / 'scope.json')
        scope['incorporated_refs'] = ['v9.0.0/b001']
        vf.write_json(self.f.draft('v1.0.0') / 'scope.json', scope)
        with self.assertRaises(vf.FlowError): self.f.seal('v1.0.0')


    def test_doctor_detects_unknown_current_pointer(self):
        registry = self.f.registry()
        registry['current_delivered'] = 'v9.0.0/b001'
        vf.write_json(self.root / '.project-flow/project.json', registry)
        self.assertFalse(self.f.doctor()['ok'])


    def test_id_must_not_disappear_within_same_product_revision(self):
        self.spec()
        trace = vf.obj(self.f.draft('v1.0.0') / 'traceability.json')
        trace['requirements'][0]['id'] = 'REQ-NEW'
        for case in trace['acceptance']:
            case['requirement_ids'] = ['REQ-NEW']
        vf.write_json(self.f.draft('v1.0.0') / 'traceability.json', trace)
        with self.assertRaisesRegex(vf.FlowError, 'Historical IDs'): self.f.seal('v1.0.0')



if __name__ == '__main__':
    unittest.main(verbosity=2)
