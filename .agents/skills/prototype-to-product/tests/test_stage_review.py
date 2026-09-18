"""Synthetic stage-review records; no model interaction or real project is certified."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
import test_workflow as fixture

vf = fixture.vf
SCRIPT = fixture.SCRIPT


class StageReviewTests(unittest.TestCase):
    setUp = fixture.WorkflowTests.setUp
    write = fixture.WorkflowTests.write
    spec = fixture.WorkflowTests.spec
    backend = fixture.WorkflowTests.backend
    tasks = fixture.WorkflowTests.tasks
    phase_report = fixture.WorkflowTests.phase_report
    handoff = fixture.WorkflowTests.handoff
    accepted_backend = fixture.WorkflowTests.accepted_backend
    frontend = fixture.WorkflowTests.frontend
    integration = fixture.WorkflowTests.integration
    cp = fixture.WorkflowTests.cp

    def review(self, target='ITERATE', **kwargs):
        return self.f.review_stage(self.v, target, 'SYNTHETIC review summary.', **kwargs)['review']

    def answer(self, review, decision='advance'):
        return self.f.answer_review(self.v, review['id'], decision,
                                    f'SYNTHETIC user {decision}', 'synthetic:stage-review')

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args, '--root', str(self.root)],
                              text=True, capture_output=True)

    def test_current_state_has_no_pending_review_at_creation(self):
        self.assertIsNone(self.f.state(self.v)['pending_stage_review'])

    def test_prepare_keeps_stage_and_creates_choice(self):
        review = self.review()
        self.assertEqual(self.f.state(self.v)['stage'], 'DISCOVER')
        self.assertEqual(review['status'], 'awaiting_user')
        self.assertIn('继续修改', review['question'])
        self.assertEqual(self.f.state(self.v)['approvals'], [])

    def test_same_question_and_content_reuse_identifier(self):
        first = self.review(); second = self.review()
        self.assertEqual(first['id'], second['id'])
        events = [x for x in self.f.state(self.v)['history'] if x['event'] == 'stage-review-requested']
        self.assertEqual(len(events), 1)

    def test_empty_summary_rejected(self):
        with self.assertRaises(vf.FlowError): self.f.review_stage(self.v, 'ITERATE', ' ')

    def test_wrong_next_stage_rejected(self):
        with self.assertRaises(vf.FlowError): self.review('BACKEND_BUILD')

    def test_blocked_does_not_look_like_completion(self):
        self.f.stage(self.v, 'BLOCKED', 'SYNTHETIC missing required input')
        with self.assertRaises(vf.FlowError): self.review()

    def test_open_blocker_prevents_prepare(self):
        state = self.f.state(self.v); state['blockers'] = [{'id': 'B-1', 'reason': 'Synthetic'}]
        self.f.save_state(state)
        with self.assertRaises(vf.FlowError): self.review()

    def test_specify_requires_actual_candidate(self):
        self.f.stage(self.v, 'SPECIFY')
        with self.assertRaisesRegex(vf.FlowError, 'candidate'): self.review('READY')

    def test_specify_question_names_baseline_and_scope(self):
        ref = self.spec(); review = self.review('READY')
        self.assertIn(ref, review['question'])
        self.assertIn('不授权正式实现', review['question'])
        self.assertEqual(self.f.state(self.v)['stage'], 'SPECIFY')

    def test_pending_question_blocks_forward_stage(self):
        self.review()
        with self.assertRaisesRegex(vf.FlowError, 'Pending stage review'):
            self.f.stage(self.v, 'ITERATE')
        self.assertEqual(self.f.state(self.v)['stage'], 'DISCOVER')

    def test_answer_records_choice_but_does_not_advance(self):
        review = self.review(); result = self.answer(review)
        self.assertFalse(result['stage_advanced'])
        self.assertFalse(result['authorization_authenticated'])
        self.assertEqual(self.f.state(self.v)['stage'], 'DISCOVER')
        self.assertEqual(self.f.state(self.v)['approvals'], [])

    def test_advance_then_formal_stage_clears_pending_preserves_history(self):
        review = self.review(); self.answer(review); self.f.stage(self.v, 'ITERATE')
        state = self.f.state(self.v)
        self.assertEqual(state['stage'], 'ITERATE')
        self.assertIsNone(state['pending_stage_review'])
        self.assertTrue(any(x['event'] == 'stage-review-completed' for x in state['history']))

    def test_specify_answer_does_not_replace_baseline_approval(self):
        ref = self.spec(); review = self.review('READY'); self.answer(review)
        self.assertIsNone(self.f.state(self.v)['approved'])
        self.f.approve(ref, 'baseline', 'SYNTHETIC exact baseline approved', 'synthetic:review')
        self.assertEqual(self.f.state(self.v)['stage'], 'READY')
        self.assertIsNone(self.f.state(self.v)['pending_stage_review'])

    def test_approve_cannot_skip_pending_answer(self):
        ref = self.spec(); self.review('READY')
        with self.assertRaisesRegex(vf.FlowError, 'Pending stage review'):
            self.f.approve(ref, 'baseline', 'SYNTHETIC not answered', 'synthetic:review')
        self.assertEqual(self.f.state(self.v)['stage'], 'SPECIFY')

    def test_modify_keeps_stage_and_blocks_next(self):
        review = self.review(); self.answer(review, 'modify')
        self.assertEqual(self.f.state(self.v)['stage'], 'DISCOVER')
        self.assertEqual(self.f.state(self.v)['pending_stage_review']['status'], 'changes_requested')
        with self.assertRaises(vf.FlowError): self.f.stage(self.v, 'ITERATE')

    def test_modify_requires_new_question_before_later_advance(self):
        review = self.review(); self.answer(review, 'modify')
        with self.assertRaisesRegex(vf.FlowError, 'Changes were requested'): self.answer(review)
        new = self.review()
        self.assertNotEqual(review['id'], new['id'])
        self.answer(new); self.f.stage(self.v, 'ITERATE')

    def test_pause_is_not_a_new_stage(self):
        review = self.review(); self.answer(review, 'pause'); self.cp()
        restored = self.f.resume(self.v)
        self.assertEqual(restored['stage'], 'DISCOVER')
        self.assertTrue(restored['awaiting_stage_decision'])
        self.assertFalse(restored['ready_to_continue'])
        self.assertEqual(restored['pending_stage_review']['status'], 'paused')

    def test_paused_review_can_be_explicitly_confirmed_when_fresh(self):
        review = self.review(); self.answer(review, 'pause'); self.cp()
        self.answer(review); self.f.stage(self.v, 'ITERATE')
        self.assertEqual(self.f.state(self.v)['stage'], 'ITERATE')

    def test_wrong_review_id_rejected(self):
        self.review()
        with self.assertRaisesRegex(vf.FlowError, 'matching pending'):
            self.f.answer_review(self.v, 'q9999', 'advance', 'SYNTHETIC', 'synthetic:test')

    def test_answer_needs_real_source_fields(self):
        review = self.review()
        for quote, context in [('', 'synthetic:test'), ('SYNTHETIC', '')]:
            with self.subTest(quote=quote, context=context), self.assertRaises(vf.FlowError):
                self.f.answer_review(self.v, review['id'], 'advance', quote, context)

    def test_unknown_decision_rejected(self):
        review = self.review()
        with self.assertRaises(vf.FlowError):
            self.f.answer_review(self.v, review['id'], 'yes', 'SYNTHETIC', 'synthetic:test')

    def test_missing_or_secret_or_self_artifact_rejected(self):
        self.write('backend/.env', 'SYNTHETIC_NOT_A_SECRET=1')
        for name in ['missing.md', 'backend/.env', self.r + '/state.json', self.r + '/RESUME.md']:
            with self.subTest(name=name), self.assertRaises(vf.FlowError): self.review(artifacts=[name])

    def test_draft_change_invalidates_unanswered_question(self):
        review = self.review()
        self.write(f'docs/releases/{self.v}/draft/spec/new.md', '# New synthetic detail')
        with self.assertRaisesRegex(vf.FlowError, 'stale'): self.answer(review)
        self.assertFalse(self.f.resume(self.v)['stage_review_fresh'])

    def test_source_change_invalidates_previously_confirmed_question(self):
        review = self.review(); self.answer(review)
        self.write('backend/app.py', '# Changed synthetic source')
        with self.assertRaisesRegex(vf.FlowError, 'stale'): self.f.stage(self.v, 'ITERATE')
        self.assertEqual(self.f.state(self.v)['stage'], 'DISCOVER')

    def test_artifact_change_invalidates_review(self):
        name = self.write(self.r + '/evidence/review.log', 'SYNTHETIC original')
        review = self.review(artifacts=[name])
        self.write(name, 'SYNTHETIC changed')
        with self.assertRaisesRegex(vf.FlowError, 'stale'): self.answer(review)

    def test_task_change_invalidates_review(self):
        review = self.review()
        path = self.root / self.r / 'tasks.json'
        tasks = vf.obj(path); tasks['synthetic_progress_note'] = 'changed'; vf.write_json(path, tasks)
        with self.assertRaisesRegex(vf.FlowError, 'stale'): self.answer(review)

    def test_checkpoint_and_notes_do_not_invalidate_review(self):
        review = self.review(); self.cp()
        self.assertTrue(self.f.review_fresh(self.v, review))
        self.answer(review); self.cp(expected='c0001')
        self.assertTrue(self.f.resume(self.v)['ready_to_continue'])
        self.f.stage(self.v, 'ITERATE')

    def test_new_session_restores_question_and_does_not_mutate_files(self):
        review = self.review(); self.cp()
        before = (self.root / self.r / 'state.json').read_bytes()
        run = self.cli('resume', '--version', self.v)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result['pending_stage_review']['id'], review['id'])
        self.assertTrue(result['awaiting_stage_decision'])
        self.assertFalse(result['ready_to_continue'])
        self.assertFalse(result['stage_advanced'])
        self.assertEqual(before, (self.root / self.r / 'state.json').read_bytes())

    def test_resume_entry_and_checkpoint_include_pending_choice(self):
        review = self.review(); self.cp()
        text = (self.root / self.r / 'RESUME.md').read_text()
        self.assertIn(review['question'], text)
        self.assertEqual(self.f.read_checkpoint(self.v)['pending_stage_review']['id'], review['id'])

    def test_new_candidate_invalidates_old_question(self):
        self.spec(); old = self.review('READY')
        self.f.seal(self.v)
        self.assertIsNone(self.f.state(self.v)['pending_stage_review'])
        new = self.review('READY')
        self.assertNotEqual(old['id'], new['id'])
        self.assertNotEqual(old['baseline_ref'], new['baseline_ref'])

    def test_freeze_cannot_bypass_iterate_confirmation(self):
        self.f.stage(self.v, 'ITERATE'); self.review('SPECIFY')
        with self.assertRaisesRegex(vf.FlowError, 'Pending stage review'):
            self.f.seal(self.v)
        self.assertEqual(self.f.state(self.v)['stage'], 'ITERATE')

    def test_revise_clears_choice_instead_of_reusing_it(self):
        self.spec(); review = self.review('READY'); self.answer(review, 'modify')
        self.f.revise(self.v, 'SYNTHETIC requested specification change')
        self.assertIsNone(self.f.state(self.v)['pending_stage_review'])
        self.assertTrue(any(x['event'] == 'stage-review-invalidated' for x in self.f.state(self.v)['history']))

    def test_backend_acceptance_requires_answer_and_all_existing_gates(self):
        ref = self.backend(); self.f.stage(self.v, 'BACKEND_VERIFY')
        report, _ = self.phase_report('backend', ref); handoff, _ = self.handoff(ref)
        review = self.review('FRONTEND_READY', artifacts=[report, handoff])
        with self.assertRaisesRegex(vf.FlowError, 'Pending stage review'):
            self.f.accept_backend(self.v, report, handoff)
        self.answer(review)
        result = self.f.accept_backend(self.v, report, handoff)
        self.assertEqual(result['stage'], 'FRONTEND_READY')
        self.assertIsNone(self.f.state(self.v)['pending_stage_review'])

    def test_user_confirmation_does_not_waive_required_acceptance(self):
        ref = self.backend(); self.f.stage(self.v, 'BACKEND_VERIFY')
        report, data = self.phase_report('backend', ref); handoff, _ = self.handoff(ref)
        data['checks'][0]['status'] = 'failed'; self.write(report, data)
        review = self.review('FRONTEND_READY', artifacts=[report, handoff]); self.answer(review)
        with self.assertRaises(vf.FlowError): self.f.accept_backend(self.v, report, handoff)
        self.assertEqual(self.f.state(self.v)['stage'], 'BACKEND_VERIFY')
        self.assertEqual(self.f.state(self.v)['pending_stage_review']['status'], 'advance_confirmed')

    def test_ready_review_requires_matching_backend_approval(self):
        ref = self.spec(); self.f.approve(ref, 'baseline', 'SYNTHETIC baseline', 'synthetic:test')
        review = self.review('BACKEND_BUILD'); self.answer(review)
        with self.assertRaises(vf.FlowError):
            self.f.approve(ref, 'backend', 'SYNTHETIC backend', 'synthetic:test')
        self.f.approve(ref, 'backend', 'SYNTHETIC backend', 'synthetic:test', code_ref='synthetic:code')
        self.assertEqual(self.f.state(self.v)['stage'], 'BACKEND_BUILD')
        self.assertIsNone(self.f.state(self.v)['pending_stage_review'])

    def test_frontend_start_binds_handoff_after_choice(self):
        ref, package = self.accepted_backend()
        review = self.review('FRONTEND_BUILD')
        self.assertEqual(review['backend_handoff'], package['handoff_id'])
        with self.assertRaises(vf.FlowError):
            self.f.approve(ref, 'frontend', 'SYNTHETIC front', 'synthetic:test', code_ref='synthetic:front')
        self.answer(review)
        self.f.approve(ref, 'frontend', 'SYNTHETIC front', 'synthetic:test', code_ref='synthetic:front')
        self.assertEqual(self.f.state(self.v)['stage'], 'FRONTEND_BUILD')

    def test_repair_return_does_not_require_forward_question(self):
        self.backend(); self.f.stage(self.v, 'BACKEND_VERIFY')
        self.review('FRONTEND_READY')
        self.f.stage(self.v, 'BACKEND_BUILD', 'SYNTHETIC repair required')
        self.assertEqual(self.f.state(self.v)['stage'], 'BACKEND_BUILD')
        self.assertIsNone(self.f.state(self.v)['pending_stage_review'])

    def test_delivery_needs_choice_and_does_not_mean_production(self):
        _, report, _ = self.integration()
        review = self.review('DELIVERED', artifacts=[report])
        self.assertIn('不执行生产部署', review['question'])
        with self.assertRaisesRegex(vf.FlowError, 'Pending stage review'): self.f.deliver(self.v, report)
        self.answer(review); self.f.deliver(self.v, report)
        self.assertEqual(self.f.state(self.v)['stage'], 'DELIVERED')
        self.assertIsNone(self.f.state(self.v)['pending_stage_review'])
        self.assertTrue(self.f.check_delivery(self.v)['ok'])
        with self.assertRaises(vf.FlowError): self.review('ITERATE')

    def test_cli_review_and_answer_roundtrip(self):
        run = self.cli('review-stage', '--version', self.v, '--to', 'ITERATE',
                       '--summary', 'SYNTHETIC CLI review')
        self.assertEqual(run.returncode, 0, run.stderr)
        review = json.loads(run.stdout)['review']
        answered = self.cli('answer-review', '--version', self.v, '--review-id', review['id'],
                            '--decision', 'advance', '--quote', 'SYNTHETIC advance', '--context', 'synthetic:cli')
        self.assertEqual(answered.returncode, 0, answered.stderr)
        advanced = self.cli('stage', '--version', self.v, '--to', 'ITERATE')
        self.assertEqual(advanced.returncode, 0, advanced.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
