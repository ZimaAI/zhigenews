"""Current-format and stage-control tests using synthetic inputs only."""
from pathlib import Path
import argparse
import json
import subprocess
import sys
import unittest
import test_workflow as fixture

vf = fixture.vf
SCRIPT = fixture.SCRIPT


class StageControlTests(unittest.TestCase):
    setUp = fixture.WorkflowTests.setUp
    write = fixture.WorkflowTests.write
    spec = fixture.WorkflowTests.spec
    cp = fixture.WorkflowTests.cp

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args, '--root', str(self.root)],
                              text=True, capture_output=True)

    def approve(self, ref):
        return self.f.approve(ref, 'baseline', 'SYNTHETIC approve this baseline only; no implementation',
                              'synthetic:test')

    def test_all_created_records_use_one_current_format(self):
        ref = self.spec()
        for relative in ('.project-flow/project.json', self.r + '/state.json', self.r + '/tasks.json',
                         f'docs/releases/{self.v}/draft/scope.json',
                         f'docs/releases/{self.v}/draft/traceability.json',
                         f'docs/releases/{self.v}/draft/quality-gates.json',
                         f'docs/releases/{self.v}/baselines/b001/manifest.json'):
            with self.subTest(path=relative):
                self.assertEqual(vf.obj(self.root / relative)['schema_version'], 4)
        self.assertEqual(self.f.state(self.v)['workflow_version'], 4)
        self.assertEqual(self.f.plan(self.v)['workflow_version'], 4)

    def test_unsupported_registry_rejected_without_conversion(self):
        p = self.root / '.project-flow/project.json'
        record = vf.obj(p); record['schema_version'] = 999
        vf.write_json(p, record); before = p.read_bytes()
        run = self.cli('status')
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('Unsupported', run.stderr)
        self.assertEqual(p.read_bytes(), before)

    def test_unsupported_workflow_rejected_without_conversion(self):
        p = self.root / self.r / 'state.json'
        record = vf.obj(p); record['workflow_version'] = 999
        vf.write_json(p, record); before = p.read_bytes()
        run = self.cli('resume', '--version', self.v)
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(p.read_bytes(), before)

    def test_only_current_commands_are_exposed(self):
        parser = vf.parser()
        action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        expected = {'init','new','status','switch','seal','check','approve','revise','stage','diff',
                    'history','deliver','check-delivery','promote','doctor','index','export',
                    'checkpoint','resume','source-id','accept-backend','check-backend','reopen-backend',
                    'review-stage','answer-review'}
        self.assertEqual(set(action.choices), expected)
        init_flags = {flag for a in action.choices['init']._actions for flag in a.option_strings}
        self.assertEqual(init_flags, {'-h','--help','--root','--version','--name'})

    def test_init_refuses_occupied_managed_directory(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            control = workspace / '.project-flow'; control.mkdir()
            original = control / 'unknown-record.json'; original.write_text('{"keep":true}')
            run = subprocess.run([sys.executable, str(SCRIPT), 'init', '--root', temp,
                                  '--version', 'v1.0.0'], text=True, capture_output=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(original.read_text(), '{"keep":true}')
            self.assertFalse((control / 'project.json').exists())

    def test_incomplete_spec_cannot_be_approved(self):
        self.f.stage(self.v, 'SPECIFY')
        with self.assertRaises(vf.FlowError): self.approve(self.v + '/b001')
        self.assertEqual(self.f.state(self.v)['stage'], 'SPECIFY')
        self.assertEqual(self.f.state(self.v)['approvals'], [])

    def test_seal_is_not_approval(self):
        self.spec()
        state = self.f.state(self.v)
        self.assertEqual(state['stage'], 'SPECIFY')
        self.assertIsNone(state['approved'])
        self.assertEqual(state['approvals'], [])

    def test_specify_resume_remains_unapproved(self):
        self.spec(); self.cp()
        run = self.cli('resume', '--version', self.v)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['stage'], 'SPECIFY')
        self.assertIsNone(self.f.state(self.v)['approved'])

    def test_public_cli_specify_to_ready_does_not_start_backend(self):
        ref = self.spec()
        run = self.cli('approve', '--ref', ref, '--kind', 'baseline',
                       '--quote', 'SYNTHETIC approve this precise candidate; do not implement',
                       '--context', 'synthetic:cli')
        self.assertEqual(run.returncode, 0, run.stderr)
        state = self.f.state(self.v)
        self.assertEqual(state['stage'], 'READY')
        self.assertEqual(state['approved'], 'b001')
        self.assertIsNone(state['active_baseline'])
        self.assertEqual([a['kind'] for a in state['approvals']], ['baseline'])
        self.assertEqual(len(self.f.entry(self.v)['baselines']), 1)

    def test_ready_checkpoint_new_session_does_not_start_backend(self):
        ref = self.spec(); self.approve(ref); self.cp()
        run = self.cli('resume', '--version', self.v)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['stage'], 'READY')
        self.assertFalse(json.loads(run.stdout)['stage_advanced'])
        self.assertEqual(self.f.state(self.v)['stage'], 'READY')

    def test_stage_command_cannot_skip_baseline_approval(self):
        self.spec()
        run = self.cli('stage', '--version', self.v, '--to', 'READY')
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(self.f.state(self.v)['stage'], 'SPECIFY')

    def test_blocking_question_prevents_ready(self):
        ref = self.spec(); state = self.f.state(self.v)
        state['open_questions'] = [{'id': 'Q-001', 'blocking': True, 'question': 'Synthetic undecided behavior'}]
        self.f.save_state(state)
        with self.assertRaisesRegex(vf.FlowError, 'blocking'): self.approve(ref)
        self.assertEqual(self.f.state(self.v)['stage'], 'SPECIFY')

    def test_changed_draft_prevents_ready(self):
        ref = self.spec()
        p = self.f.draft(self.v) / 'spec/01-requirements.md'
        p.write_text('Changed synthetic behavior')
        with self.assertRaisesRegex(vf.FlowError, 'Draft differs'): self.approve(ref)
        self.assertEqual(self.f.state(self.v)['stage'], 'SPECIFY')

    def test_older_candidate_cannot_be_approved_as_current(self):
        first = self.spec()
        second = self.f.seal(self.v)['ref']
        with self.assertRaisesRegex(vf.FlowError, 'current candidate'): self.approve(first)
        self.approve(second)
        self.assertEqual(self.f.state(self.v)['approved'], 'b002')

    def test_explicit_backend_authorization_advances_ready(self):
        ref = self.spec(); self.approve(ref)
        run = self.cli('approve', '--ref', ref, '--kind', 'backend',
                       '--quote', 'SYNTHETIC authorize backend only', '--context', 'synthetic:cli',
                       '--code-ref', 'synthetic:backend-start')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.f.state(self.v)['stage'], 'BACKEND_BUILD')
        self.assertEqual([a['kind'] for a in self.f.state(self.v)['approvals']], ['baseline','backend'])

    def test_stage_next_action_matches_specify(self):
        self.f.stage(self.v, 'SPECIFY')
        self.assertIn('规范', self.f.state(self.v)['next_action'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
