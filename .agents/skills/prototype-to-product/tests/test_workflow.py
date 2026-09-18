"""Synthetic workflow tests; assertions and logs do NOT certify a real application."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'version_flow.py'
SPEC = importlib.util.spec_from_file_location('workflow_current', SCRIPT)
assert SPEC and SPEC.loader
vf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vf)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.f = vf.Flow(self.root)
        self.v = 'v1.0.0'
        self.f.init(self.v, 'SYNTHETIC workflow project')
        self.r = f'.project-flow/versions/{self.v}'

    def write(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, dict):
            vf.write_json(target, value)
        else:
            target.write_text(value, encoding='utf-8')
        return path

    def spec(self):
        tree = self.f.draft(self.v)
        scope = vf.obj(tree / 'scope.json')
        scope['readiness_reviewed'] = True
        scope['change_summary'] = 'SYNTHETIC: a fullstack action.'
        vf.write_json(tree / 'scope.json', scope)
        for name in scope['documents'].values():
            path = tree / name.split('#')[0]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# Synthetic specification\nNot a real product approval.\n', encoding='utf-8')
        vf.write_json(tree / 'traceability.json', {
            'schema_version': 4, 'requirements': [{
                'id': 'REQ-001', 'title': 'Synthetic action', 'since': self.v,
                'change': 'added', 'status': 'active', 'spec_refs': ['spec/01-requirements.md'],
                'acceptance_ids': ['AC-B', 'AC-F', 'AC-I'],
            }],
            'acceptance': [
                {'id': cid, 'status': 'active', 'required': True, 'phase': phase,
                 'requirement_ids': ['REQ-001'], 'spec_refs': ['spec/05-acceptance.md']}
                for cid, phase in [('AC-B', 'backend'), ('AC-F', 'frontend'), ('AC-I', 'integration')]]
        })
        vf.write_json(tree / 'quality-gates.json', {
            'schema_version': 4,
            'gates': [{'id': 'GATE-I', 'required': True, 'phase': 'integration',
                       'description': 'Synthetic integrated gate'}],
        })
        self.write(f'docs/releases/{self.v}/draft/contracts/openapi.yaml',
                   'openapi: 3.1.0\ninfo: {title: Synthetic, version: "1.0"}\npaths: {}\n')
        self.write('backend/app.py', '# synthetic backend fixture\n')
        self.write('frontend/app.ts', '// synthetic frontend fixture\n')
        return self.f.seal(self.v)['ref']

    def backend(self, ref=None):
        ref = ref or self.spec()
        self.f.approve(ref, 'baseline', 'SYNTHETIC baseline approval', 'synthetic:test')
        self.f.approve(ref, 'backend', 'SYNTHETIC backend only', 'synthetic:test', code_ref='synthetic:b-start')
        self.tasks(ref)
        return ref

    def tasks(self, ref, *, backend='done', frontend='pending', integration='pending'):
        self.write(self.r + '/tasks.json', {
            'schema_version': 4, 'version': self.v,
            'tasks': [
                {'id': 'T-B', 'phase': 'backend', 'baseline_ref': ref, 'status': backend, 'depends_on': []},
                {'id': 'T-F', 'phase': 'frontend', 'baseline_ref': ref, 'status': frontend, 'depends_on': ['T-B']},
                {'id': 'T-I', 'phase': 'integration', 'baseline_ref': ref, 'status': integration, 'depends_on': ['T-F']},
            ],
        })

    def phase_report(self, phase, ref=None):
        state = self.f.state(self.v)
        ref = ref or f'{self.v}/{state["active_baseline"]}'
        log = self.write(self.r + f'/evidence/{phase}.log',
                         'SYNTHETIC log fixture; no application test executed.\n')
        required, _ = self.f.phase_checks(ref, phase)
        report = {
            'schema_version': 4, 'version': self.v, 'baseline_ref': ref,
            'manifest_sha256': self.f.check(ref)['manifest_sha256'], 'phase': phase,
            'code_ref': f'synthetic:{phase}', 'open_blockers': [],
            'source_fingerprint': self.f.source_identity(self.v, phase, frozen=True)['fingerprint'],
            'checks': [{'id': cid, 'status': 'passed', 'code_ref': f'synthetic:{phase}',
                        'evidence': [log]} for cid in sorted(required)],
        }
        if phase == 'frontend':
            handoff = self.f.check_backend(self.v)
            report.update({'backend_handoff': handoff['handoff_id'],
                           'backend_handoff_sha256': handoff['sha256']})
        path = self.write(self.r + f'/{phase}-verification.json', report)
        return path, report

    def handoff(self, ref):
        record = {'schema_version': 4, 'version': self.v, 'baseline_ref': ref,
                  'code_ref': 'synthetic:backend', 'known_limitations': [], 'open_blockers': []}
        for key in ('runbook', 'endpoint_inventory', 'environment_template', 'smoke_instructions'):
            record[key] = self.write(self.r + f'/handoff-input/{key}.md', f'# {key}\nSYNTHETIC fixture.\n')
        path = self.write(self.r + '/handoff-input/handoff.json', record)
        return path, record

    def accepted_backend(self, ref=None):
        ref = ref or self.backend()
        self.f.stage(self.v, 'BACKEND_VERIFY')
        report, _ = self.phase_report('backend', ref)
        handoff, _ = self.handoff(ref)
        result = self.f.accept_backend(self.v, report, handoff)
        return ref, result

    def frontend(self, ref=None):
        ref, _ = self.accepted_backend(ref)
        self.f.approve(ref, 'frontend', 'SYNTHETIC start frontend', 'synthetic:new-session', code_ref='synthetic:f-start')
        self.tasks(ref, frontend='done')
        return ref

    def integration(self):
        ref = self.frontend()
        self.f.stage(self.v, 'FRONTEND_VERIFY')
        report, _ = self.phase_report('frontend', ref)
        self.f.stage(self.v, 'INTEGRATION_VERIFY', report_name=report)
        self.tasks(ref, frontend='done', integration='done')
        handoff = self.f.check_backend(self.v)
        log = self.write(self.r + '/evidence/final.log', 'SYNTHETIC integrated results.\n')
        record = {
            'schema_version': 4, 'version': self.v, 'baseline_ref': ref, 'phase': 'integration',
            'manifest_sha256': self.f.check(ref)['manifest_sha256'],
            'code_ref': 'synthetic:release', 'open_blockers': [],
            'backend_handoff': handoff['handoff_id'], 'backend_handoff_sha256': handoff['sha256'],
            'source_fingerprints': {p: self.f.source_identity(self.v, p, frozen=True)['fingerprint']
                                    for p in ('backend', 'frontend')},
            'checks': [{'id': cid, 'status': 'passed', 'code_ref': 'synthetic:release', 'evidence': [log]}
                       for cid in ['AC-B', 'AC-F', 'AC-I', 'GATE-I']],
        }
        path = self.write(self.r + '/verification.json', record)
        return ref, path, record

    def cp(self, next_action='Continue the current approved task.', expected=None):
        notes = self.write(self.r + '/session-notes.md', '# Synthetic session\nDecisions and actual state recorded.\n')
        return self.f.checkpoint(self.v, notes, next_action, expected_previous=expected)

    def test_initial_state_uses_current_workflow(self):
        self.assertEqual(self.f.state(self.v)['workflow_version'], 4)
        self.assertTrue((self.root / self.r / 'RESUME.md').is_file())

    def test_snapshot_uses_current_schema(self):
        ref = self.spec()
        self.assertEqual(vf.obj(self.f.snapshot(ref).parent / 'manifest.json')['schema_version'], 4)

    def test_checkpoint_does_not_advance_discovery(self):
        self.cp()
        self.assertEqual(self.f.state(self.v)['stage'], 'DISCOVER')
        self.assertTrue(self.f.resume(self.v)['ready_to_continue'])

    def test_new_process_resumes_same_version_and_stage(self):
        self.cp()
        run = subprocess.run([sys.executable, str(SCRIPT), 'resume', '--root', str(self.root),
                              '--version', self.v], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        data = json.loads(run.stdout)
        self.assertEqual(data['version'], self.v)
        self.assertTrue(data['ready_to_continue'])
        self.assertFalse(data['files_modified'])

    def test_resume_without_checkpoint_does_not_invent_state(self):
        result = self.f.resume(self.v)
        self.assertFalse(result['ready_to_continue'])
        self.assertTrue(result['warnings'])
        self.assertEqual(result['stage'], 'DISCOVER')

    def test_checkpoint_all_planning_stages(self):
        for stage in ('DISCOVER', 'SCOPE', 'ITERATE', 'SPECIFY', 'READY'):
            with self.subTest(stage=stage):
                state = self.f.state(self.v)
                state['stage'] = stage
                self.f.save_state(state)
                self.cp()
                self.assertEqual(self.f.resume(self.v)['stage'], stage)

    def test_backend_build_checkpoint_preserves_authorization(self):
        ref = self.backend()
        self.cp()
        result = vf.Flow(self.root).resume(self.v)
        self.assertTrue(result['ready_to_continue'])
        self.assertEqual(result['stage'], 'BACKEND_BUILD')
        self.assertTrue(self.f.check(ref, for_build=True)['ok'])

    def test_backend_verify_checkpoint_resumes_without_frontend(self):
        self.backend()
        self.f.stage(self.v, 'BACKEND_VERIFY')
        self.cp()
        self.assertEqual(self.f.resume(self.v)['stage'], 'BACKEND_VERIFY')

    def test_frontend_ready_checkpoint_survives_new_session(self):
        self.accepted_backend()
        self.cp()
        result = vf.Flow(self.root).resume(self.v)
        self.assertTrue(result['ready_to_continue'])
        self.assertEqual(result['stage'], 'FRONTEND_READY')

    def test_frontend_build_and_verify_checkpoint(self):
        self.frontend()
        for stage in ('FRONTEND_BUILD', 'FRONTEND_VERIFY'):
            if stage != self.f.state(self.v)['stage']:
                self.f.stage(self.v, stage)
            self.cp()
            self.assertTrue(self.f.resume(self.v)['ready_to_continue'])

    def test_integration_checkpoint_preserves_stage(self):
        self.integration()
        self.cp()
        self.assertEqual(self.f.resume(self.v)['stage'], 'INTEGRATION_VERIFY')

    def test_blocked_session_stays_blocked(self):
        self.backend()
        self.f.stage(self.v, 'BLOCKED', 'SYNTHETIC missing service')
        self.cp()
        result = self.f.resume(self.v)
        self.assertFalse(result['ready_to_continue'])
        self.assertEqual(result['stage'], 'BLOCKED')
        self.assertEqual(self.f.state(self.v)['resume_stage'], 'BACKEND_BUILD')

    def test_delivered_checkpoint_is_read_only_continuation(self):
        _, path, _ = self.integration()
        self.f.deliver(self.v, path)
        self.cp()
        self.assertFalse(self.f.resume(self.v)['ready_to_continue'])
        self.assertEqual(self.f.resume(self.v)['stage'], 'DELIVERED')

    def test_checkpoint_notes_are_immutable(self):
        result = self.cp()
        self.write(self.r + f'/checkpoints/{result["checkpoint"]}/notes.md', 'tampered')
        with self.assertRaisesRegex(vf.FlowError, 'drift'):
            self.f.resume(self.v)

    def test_stale_checkpoint_does_not_overwrite_current_draft(self):
        self.cp()
        path = self.write(f'docs/releases/{self.v}/draft/new.md', 'new design')
        result = self.f.resume(self.v)
        self.assertIn('draft', result['drift'])
        self.assertEqual((self.root / path).read_text(), 'new design')
        self.assertFalse(result['ready_to_continue'])

    def test_task_and_state_drift_are_reported(self):
        self.cp()
        self.write(self.r + '/tasks.json', {'schema_version': 4, 'version': self.v, 'tasks': [] , 'note': 'changed'})
        state = self.f.state(self.v)
        state['next_action'] = 'Another session changed this.'
        self.f.save_state(state)
        result = self.f.resume(self.v)
        self.assertIn('runtime_files', result['drift'])
        self.assertIn('state', result['drift'])

    def test_source_drift_is_reported_on_resume(self):
        self.backend()
        self.cp()
        self.write('backend/extra.py', '# changed')
        self.assertIn('sources', self.f.resume(self.v)['drift'])

    def test_historical_checkpoint_is_not_a_restore_command(self):
        first = self.cp()['checkpoint']
        self.cp('Second session action.')
        result = self.f.resume(self.v, identifier=first)
        self.assertTrue(result['historical_read_only'])
        self.assertEqual(self.f.state(self.v)['next_action'], 'Second session action.')

    def test_expected_previous_rejects_stale_writer(self):
        self.cp()
        with self.assertRaisesRegex(vf.FlowError, 'pointer changed'):
            self.cp(expected='none')

    def test_unscoped_build_approval_is_rejected(self):
        ref = self.spec()
        with self.assertRaisesRegex(vf.FlowError, 'unscoped'):
            self.f.approve(ref, 'build', 'synthetic', 'test', code_ref='synthetic')

    def test_backend_needs_exact_baseline_approval(self):
        ref = self.spec()
        with self.assertRaisesRegex(vf.FlowError, 'Approve the exact baseline'):
            self.f.approve(ref, 'backend', 'synthetic', 'test', code_ref='synthetic')

    def test_frontend_cannot_start_while_backend_is_building(self):
        ref = self.backend()
        with self.assertRaisesRegex(vf.FlowError, 'FRONTEND_READY'):
            self.f.approve(ref, 'frontend', 'synthetic', 'test', code_ref='synthetic')

    def test_no_stage_shortcut_to_frontend_or_delivered(self):
        self.backend()
        for target in ('FRONTEND_READY', 'FRONTEND_BUILD', 'INTEGRATION_VERIFY', 'DELIVERED', 'VERIFY'):
            with self.subTest(target=target):
                with self.assertRaises(vf.FlowError):
                    self.f.stage(self.v, target)

    def test_backend_acceptance_archives_and_pauses(self):
        _, result = self.accepted_backend()
        self.assertFalse(result['frontend_started'])
        self.assertEqual(self.f.state(self.v)['stage'], 'FRONTEND_READY')
        folder = (self.root / result['manifest']).parent
        self.assertTrue((folder / 'contracts/openapi.yaml').is_file())
        self.assertTrue((folder / 'attachments/runbook.md').is_file())
        self.assertTrue((folder / 'evidence/backend.log').is_file())
        self.assertIsNone(self.f.entry(self.v)['delivery'])

    def test_backend_acceptance_rejects_incomplete_tasks(self):
        ref = self.backend()
        self.f.stage(self.v, 'BACKEND_VERIFY')
        report, _ = self.phase_report('backend')
        handoff, _ = self.handoff(ref)
        self.tasks(ref, backend='pending')
        with self.assertRaisesRegex(vf.FlowError, 'Incomplete'):
            self.f.accept_backend(self.v, report, handoff)

    def test_backend_acceptance_rejects_failed_check(self):
        ref = self.backend()
        self.f.stage(self.v, 'BACKEND_VERIFY')
        path, report = self.phase_report('backend')
        report['checks'][0]['status'] = 'failed'
        self.write(path, report)
        handoff, _ = self.handoff(ref)
        with self.assertRaisesRegex(vf.FlowError, 'did not pass'):
            self.f.accept_backend(self.v, path, handoff)

    def test_backend_report_cannot_contain_frontend_results(self):
        ref = self.backend()
        self.f.stage(self.v, 'BACKEND_VERIFY')
        path, report = self.phase_report('backend')
        report['checks'][0]['id'] = 'AC-F'
        self.write(path, report)
        handoff, _ = self.handoff(ref)
        with self.assertRaisesRegex(vf.FlowError, 'cross-phase'):
            self.f.accept_backend(self.v, path, handoff)

    def test_backend_report_fingerprint_must_match_files(self):
        ref = self.backend()
        self.f.stage(self.v, 'BACKEND_VERIFY')
        path, _ = self.phase_report('backend')
        handoff, _ = self.handoff(ref)
        self.write('backend/app.py', '# edited after report')
        with self.assertRaisesRegex(vf.FlowError, 'fingerprint'):
            self.f.accept_backend(self.v, path, handoff)

    def test_handoff_identity_must_match_backend(self):
        ref = self.backend()
        self.f.stage(self.v, 'BACKEND_VERIFY')
        path, _ = self.phase_report('backend')
        handoff, data = self.handoff(ref)
        data['code_ref'] = 'wrong'
        self.write(handoff, data)
        with self.assertRaisesRegex(vf.FlowError, 'identity'):
            self.f.accept_backend(self.v, path, handoff)

    def test_handoff_rejects_secrets(self):
        ref = self.backend()
        self.f.stage(self.v, 'BACKEND_VERIFY')
        path, _ = self.phase_report('backend')
        handoff, data = self.handoff(ref)
        data['environment_template'] = self.write(self.r + '/handoff-input/.env', 'SYNTHETIC=not-a-secret')
        self.write(handoff, data)
        with self.assertRaisesRegex(vf.FlowError, 'secret'):
            self.f.accept_backend(self.v, path, handoff)

    def test_handoff_body_drift_rejected(self):
        _, result = self.accepted_backend()
        path = (self.root / result['manifest']).parent / 'attachments/runbook.md'
        path.write_text('tampered')
        with self.assertRaisesRegex(vf.FlowError, 'file drift'):
            self.f.check_backend(self.v)

    def test_original_logs_can_change_without_changing_handoff_archive(self):
        self.accepted_backend()
        self.write(self.r + '/evidence/backend.log', 'new runtime log')
        self.assertTrue(self.f.check_backend(self.v)['ok'])

    def test_frontend_new_session_needs_correct_handoff(self):
        ref, _ = self.accepted_backend()
        self.cp()
        other = vf.Flow(self.root)
        self.assertEqual(other.resume(self.v)['stage'], 'FRONTEND_READY')
        other.approve(ref, 'frontend', 'SYNTHETIC continue frontend', 'synthetic:new', code_ref='synthetic:f')
        self.assertTrue(other.check(ref, for_build=True)['ok'])

    def test_changed_backend_blocks_frontend_start(self):
        ref, _ = self.accepted_backend()
        self.write('backend/app.py', '# changed')
        with self.assertRaisesRegex(vf.FlowError, 'Backend source changed'):
            self.f.approve(ref, 'frontend', 'synthetic', 'test', code_ref='synthetic')

    def test_backend_drift_blocks_frontend_continuation(self):
        ref = self.frontend()
        self.write('backend/app.py', '# changed')
        with self.assertRaisesRegex(vf.FlowError, 'Backend source changed'):
            self.f.check(ref, for_build=True)

    def test_frontend_changes_do_not_invalidate_backend_fingerprint(self):
        self.frontend()
        self.write('frontend/app.ts', '// frontend-only change')
        self.assertTrue(self.f.check_backend(self.v)['ok'])

    def test_reopen_backend_keeps_history_and_invalidates_frontend_binding(self):
        ref = self.frontend()
        old = self.f.state(self.v)['active_backend_handoff']
        self.f.reopen_backend(self.v, 'SYNTHETIC bug, same public behavior')
        self.assertIsNone(self.f.state(self.v)['active_backend_handoff'])
        self.assertIn(old, self.f.state(self.v)['backend_handoffs'])
        self.assertEqual(self.f.state(self.v)['stage'], 'BACKEND_BUILD')
        self.tasks(ref)
        _, new = self.accepted_backend(ref)
        self.assertNotEqual(new['handoff_id'], old)
        state = self.f.state(self.v)
        self.assertFalse(self.f.frontend_approved(state, ref, self.f.check(ref)['manifest_sha256'],
                                                  self.f.check_backend(self.v)))

    def test_spec_revision_invalidates_both_implementation_gates(self):
        ref = self.frontend()
        self.f.revise(self.v, 'SYNTHETIC changed product rule')
        state = self.f.state(self.v)
        self.assertEqual(state['stage'], 'ITERATE')
        self.assertIsNone(state['active_backend_handoff'])
        self.assertIsNone(state['active_baseline'])
        self.assertTrue(self.f.check(ref)['ok'])
        self.assertTrue(state['backend_handoffs'])

    def test_frontend_to_integration_requires_report(self):
        self.frontend()
        self.f.stage(self.v, 'FRONTEND_VERIFY')
        with self.assertRaises(vf.FlowError):
            self.f.stage(self.v, 'INTEGRATION_VERIFY')

    def test_frontend_report_needs_exact_backend_binding(self):
        self.frontend()
        self.f.stage(self.v, 'FRONTEND_VERIFY')
        path, report = self.phase_report('frontend')
        report['backend_handoff_sha256'] = '0' * 64
        self.write(path, report)
        with self.assertRaisesRegex(vf.FlowError, 'bind the accepted backend'):
            self.f.stage(self.v, 'INTEGRATION_VERIFY', report_name=path)

    def test_full_pipeline_delivers_without_claiming_deployment(self):
        _, path, _ = self.integration()
        result = self.f.deliver(self.v, path)
        self.assertEqual(self.f.state(self.v)['stage'], 'DELIVERED')
        self.assertFalse(result['production_deployed'])
        self.assertFalse(result['tests_executed_by_this_command'])
        self.assertTrue(self.f.check_delivery(self.v)['ok'])

    def test_backend_completion_cannot_deliver_entire_system(self):
        self.accepted_backend()
        with self.assertRaisesRegex(vf.FlowError, 'INTEGRATION_VERIFY'):
            self.f.deliver(self.v, 'missing.json')

    def test_final_report_needs_current_component_fingerprints(self):
        _, path, data = self.integration()
        data['source_fingerprints']['frontend'] = '0' * 64
        self.write(path, data)
        with self.assertRaisesRegex(vf.FlowError, 'stale frontend'):
            self.f.deliver(self.v, path)

    def test_final_verification_requires_all_phases(self):
        _, path, data = self.integration()
        data['checks'] = [item for item in data['checks'] if item['id'] != 'AC-B']
        self.write(path, data)
        with self.assertRaisesRegex(vf.FlowError, 'Missing required'):
            self.f.deliver(self.v, path)

    def test_final_report_cannot_mutate_prior_frontend_validation(self):
        _, path, _ = self.integration()
        front = self.f.state(self.v)['frontend_verification']['report']
        self.write(front, {'changed': True})
        with self.assertRaisesRegex(vf.FlowError, 'missing or changed'):
            self.f.deliver(self.v, path)

    def test_new_product_version_inherits_spec_not_execution(self):
        ref, path, _ = self.integration()
        self.f.deliver(self.v, path)
        self.cp()
        self.f.new('v1.1.0', ref)
        state = self.f.state('v1.1.0')
        self.assertEqual(state['workflow_version'], 4)
        self.assertIsNone(state['last_checkpoint'])
        self.assertEqual(state['backend_handoffs'], {})
        self.assertEqual(state['approvals'], [])
        self.assertEqual(state['stage'], 'SCOPE')

    def test_source_scan_excludes_env_dependencies_and_outputs(self):
        self.backend()
        original = self.f.source_identity(self.v, 'backend')
        self.write('backend/.env', 'SYNTHETIC=only-fixture')
        self.write('backend/node_modules/x.js', 'generated')
        self.write('backend/target/output', 'generated')
        self.assertEqual(original, self.f.source_identity(self.v, 'backend'))

    def test_backend_new_source_file_changes_fingerprint(self):
        self.backend()
        old = self.f.source_identity(self.v, 'backend')['fingerprint']
        self.write('backend/new.py', '# new')
        self.assertNotEqual(old, self.f.source_identity(self.v, 'backend')['fingerprint'])

    def test_backend_deleted_source_file_changes_fingerprint(self):
        self.backend()
        self.write('backend/keep.py', '# keep')
        old = self.f.source_identity(self.v, 'backend')['fingerprint']
        (self.root / 'backend/app.py').unlink()
        self.assertNotEqual(old, self.f.source_identity(self.v, 'backend')['fingerprint'])

    def test_source_symlink_rejected(self):
        self.backend()
        link = self.root / 'backend/link.py'
        try:
            link.symlink_to(self.root / 'frontend/app.ts')
        except OSError:
            self.skipTest('Symlinks unavailable')
        with self.assertRaisesRegex(vf.FlowError, 'Symlink'):
            self.f.source_identity(self.v, 'backend')

    def test_plan_path_traversal_rejected(self):
        plan = self.f.plan_default()
        plan['source_roots']['backend'] = ['../other']
        vf.write_json(self.f.draft(self.v) / 'execution-plan.json', plan)
        with self.assertRaises(vf.FlowError):
            self.f.plan(self.v)

    def test_required_phase_assignments_are_enforced(self):
        ref = self.spec()
        self.f.revise(self.v, 'synthetic')
        path = self.f.draft(self.v) / 'traceability.json'
        value = vf.obj(path)
        value['acceptance'][0].pop('phase')
        vf.write_json(path, value)
        with self.assertRaisesRegex(vf.FlowError, 'Assign check'):
            self.f.seal(self.v)
        self.assertTrue(self.f.check(ref)['ok'])



    def test_doctor_reports_orphaned_handoff(self):
        self.accepted_backend()
        (self.root / f'docs/releases/{self.v}/implementation/backend/h999').mkdir()
        self.assertFalse(self.f.doctor()['ok'])

    def test_doctor_reports_corrupt_checkpoint(self):
        result = self.cp()
        self.write(self.r + f'/checkpoints/{result["checkpoint"]}/RESUME.md', 'tampered')
        self.assertFalse(self.f.doctor()['ok'])

    def test_no_automatic_git_checkout_on_resume_or_switch(self):
        self.cp()
        self.assertFalse(self.f.resume(self.v)['files_modified'])
        self.assertFalse(self.f.switch(self.v)['code_checkout_performed'])

    def test_cli_source_id_and_controlled_error(self):
        self.backend()
        run = subprocess.run([sys.executable, str(SCRIPT), 'source-id', '--root', str(self.root),
                              '--version', self.v, '--component', 'backend'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('fingerprint', json.loads(run.stdout))
        run = subprocess.run([sys.executable, str(SCRIPT), 'check-backend', '--root', str(self.root),
                              '--version', self.v], capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        self.assertFalse(json.loads(run.stderr)['ok'])


    def test_backend_task_cannot_depend_on_frontend_task(self):
        self.backend()
        path = self.r + '/tasks.json'
        data = vf.obj(self.root / path)
        data['tasks'][0]['depends_on'] = ['T-F']
        self.write(path, data)
        with self.assertRaisesRegex(vf.FlowError, 'later-phase'):
            self.f.check_tasks(self.v, 'backend')

    def test_same_phase_dependency_cycle_is_rejected(self):
        self.backend()
        path = self.r + '/tasks.json'
        data = vf.obj(self.root / path)
        first = data['tasks'][0]
        first['depends_on'] = ['T-B2']
        second = dict(first, id='T-B2', depends_on=['T-B'])
        data['tasks'].append(second)
        self.write(path, data)
        with self.assertRaisesRegex(vf.FlowError, 'Cyclic'):
            self.f.check_tasks(self.v, 'backend')

    def test_frontend_evidence_cannot_change_before_final_delivery(self):
        _, path, _ = self.integration()
        self.write(self.r + '/evidence/frontend.log', 'SYNTHETIC changed evidence.\n')
        with self.assertRaisesRegex(vf.FlowError, 'evidence changed'):
            self.f.deliver(self.v, path)

    def test_shared_configuration_changes_backend_fingerprint(self):
        self.write('backend/app.py', '# synthetic backend')
        self.write('shared/config.json', {'synthetic': 1})
        plan = self.f.plan_default()
        plan['source_roots']['backend'] = ['backend', 'shared/config.json']
        vf.write_json(self.f.draft(self.v) / 'execution-plan.json', plan)
        original = self.f.source_identity(self.v, 'backend')['fingerprint']
        self.write('shared/config.json', {'synthetic': 2})
        self.assertNotEqual(original, self.f.source_identity(self.v, 'backend')['fingerprint'])

    def test_backend_acceptance_does_not_require_production_frontend(self):
        ref = self.backend()
        (self.root / 'frontend/app.ts').unlink()
        (self.root / 'frontend').rmdir()
        _, result = self.accepted_backend(ref)
        self.assertTrue(result['ok'])
        self.assertEqual(self.f.state(self.v)['stage'], 'FRONTEND_READY')
        self.assertTrue(self.f.check_backend(self.v)['ok'])

    def test_handoff_archives_backend_tasks(self):
        self.accepted_backend()
        archived = self.root / f'docs/releases/{self.v}/implementation/backend/h001/backend-tasks.json'
        data = vf.obj(archived)
        self.assertEqual(len(data['tasks']), 1)
        self.assertEqual(data['tasks'][0]['phase'], 'backend')
        self.assertEqual(data['tasks'][0]['status'], 'done')

    def test_public_cli_runs_backend_handoff_and_frontend_gate(self):
        ref = self.backend()
        def cli(*args):
            run = subprocess.run([sys.executable, str(SCRIPT), args[0], '--root', str(self.root),
                                  *args[1:]], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            return json.loads(run.stdout)
        cli('stage', '--version', self.v, '--to', 'BACKEND_VERIFY')
        report, _ = self.phase_report('backend', ref)
        handoff, _ = self.handoff(ref)
        accepted = cli('accept-backend', '--version', self.v, '--report', report, '--handoff', handoff)
        self.assertTrue(accepted['ok'])
        cli('check-backend', '--version', self.v)
        cli('approve', '--ref', ref, '--kind', 'frontend', '--quote', 'SYNTHETIC frontend approval',
            '--context', 'synthetic:fresh-cli', '--code-ref', 'synthetic:f-start')
        self.tasks(ref, frontend='done')
        cli('stage', '--version', self.v, '--to', 'FRONTEND_VERIFY')
        report, _ = self.phase_report('frontend', ref)
        cli('stage', '--version', self.v, '--to', 'INTEGRATION_VERIFY', '--report', report)
        self.assertEqual(self.f.state(self.v)['stage'], 'INTEGRATION_VERIFY')


if __name__ == '__main__':
    unittest.main()
