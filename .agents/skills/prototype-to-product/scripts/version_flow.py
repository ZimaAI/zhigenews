#!/usr/bin/env python3
"""Prototype to Product: current-only, resumable, backend-first delivery.

Python 3.10+, standard library only. All managed JSON uses schema/workflow 4.
No project commands, Git operations, network requests or deployments are executed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _storage as store
from _storage import (
    FlowError, changed, differences, local, nonblank, now, obj, ref_parts,
    scan, sha, version_label, write_json, writer_lock,
)

WORKFLOW = 4
SKILL_VERSION = '4.1.0'
PHASES = ('backend', 'frontend', 'integration')
# A review is a decision point, not an alternative lifecycle or user authentication.
REVIEW_NEXT = {
    'DISCOVER': {'ITERATE', 'SPECIFY'}, 'SCOPE': {'ITERATE', 'SPECIFY'},
    'ITERATE': {'SPECIFY'}, 'SPECIFY': {'READY'}, 'READY': {'BACKEND_BUILD'},
    'BACKEND_BUILD': {'BACKEND_VERIFY'}, 'BACKEND_VERIFY': {'FRONTEND_READY'},
    'FRONTEND_READY': {'FRONTEND_BUILD'}, 'FRONTEND_BUILD': {'FRONTEND_VERIFY'},
    'FRONTEND_VERIFY': {'INTEGRATION_VERIFY'}, 'INTEGRATION_VERIFY': {'DELIVERED'},
}

BUILD_STAGES = {
    'BACKEND_BUILD', 'BACKEND_VERIFY', 'FRONTEND_BUILD',
    'FRONTEND_VERIFY', 'INTEGRATION_VERIFY',
}
FRONT_STAGES = {'FRONTEND_BUILD', 'FRONTEND_VERIFY', 'INTEGRATION_VERIFY'}
SOURCE_EXCLUSIONS = store.EXCLUDED_DIRS | {
    '.project-flow', '.idea', '.vscode', '.cache', 'logs', 'tmp', 'target',
}


def digest_json(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def safe_source_name(path: Path) -> bool:
    """Never hash or export local secrets through source observation."""
    name = path.name
    if name.startswith('.env') and name not in {'.env.example', '.env.template'}:
        return False
    return path.suffix not in {'.pem', '.key', '.p12', '.pfx'} and name not in {
        'id_rsa', 'id_ed25519', '.DS_Store',
    } and not name.endswith(('.pyc', '.pyo'))


class Flow(store.Store):
    final_stage = 'INTEGRATION_VERIFY'
    verification_schema = WORKFLOW

    def workflow_state(self, version: str) -> dict[str, Any]:
        state = self.state(version)
        if state.get('workflow_version') != WORKFLOW:
            raise FlowError('Unsupported execution state: workflow_version=4 is required. No conversion is provided.')
        return state

    def runtime(self, version: str) -> str:
        self.entry(version)
        return f'.project-flow/versions/{version}'

    def new(self, version: str, base_ref: str | None, *,
            allow_unreleased: bool = False) -> dict[str, Any]:
        result = super().new(version, base_ref, allow_unreleased=allow_unreleased)
        state = self.state(version)
        state.update(self.execution_defaults())
        self.save_state(state)
        plan = self.draft(version) / 'execution-plan.json'
        if not plan.exists():
            write_json(plan, self.plan_default())
        self.write_resume_entry(version)
        result['workflow_version'] = WORKFLOW
        return result

    @staticmethod
    def execution_defaults() -> dict[str, Any]:
        return {
            'workflow_version': WORKFLOW,
            'backend_handoffs': {},
            'active_backend_handoff': None,
            'frontend_verification': None,
            'last_checkpoint': None,
            'checkpoint_history': [],
            'pending_stage_review': None,
        }

    @staticmethod
    def plan_default() -> dict[str, Any]:
        return {
            'schema_version': WORKFLOW,
            'workflow_version': WORKFLOW,
            'mode': 'backend-first',
            'source_roots': {'backend': ['backend'], 'frontend': ['frontend']},
            'pause_after_backend': True,
        }

    def plan(self, version: str, *, frozen: bool = False) -> dict[str, Any]:
        state = self.workflow_state(version)
        if frozen:
            baseline = state.get('active_baseline') or state.get('candidate')
            if not baseline:
                raise FlowError('No baseline for a frozen execution plan.')
            tree = self.snapshot(f'{version}/{baseline}')
        else:
            tree = self.draft(version)
        plan = obj(local(tree, 'execution-plan.json'))
        if (plan.get('schema_version') != WORKFLOW or plan.get('workflow_version') != WORKFLOW
                or plan.get('mode') != 'backend-first'):
            raise FlowError('execution-plan must use schema_version=4, workflow_version=4 and backend-first.')
        if not isinstance(plan.get('pause_after_backend'), bool):
            raise FlowError('pause_after_backend must be a boolean; false needs explicit user direction.')
        roots = plan.get('source_roots')
        if not isinstance(roots, dict) or set(roots) != {'backend', 'frontend'}:
            raise FlowError('source_roots must identify backend and frontend.')
        for phase in ('backend', 'frontend'):
            paths = roots[phase]
            if not isinstance(paths, list) or not paths or len(set(paths)) != len(paths):
                raise FlowError('Each component needs a nonempty unique source_roots array.')
            for relative in paths:
                path = self.p(nonblank(relative, 'source root'), exists=False)
                if any(part in SOURCE_EXCLUSIONS for part in PurePosixPath(relative).parts):
                    raise FlowError('Runtime/output directories cannot be source roots.')
                if relative.startswith(('docs/releases/', '.agents/skills/')):
                    raise FlowError('Specification/skill directories are not application source roots.')
                if not safe_source_name(path):
                    raise FlowError('A secret file cannot be a source root.')
        return plan

    def source_files(self, roots: list[str], *, allow_missing: bool = False) -> dict[str, str]:
        result: dict[str, str] = {}
        for relative in roots:
            root = self.p(relative, exists=False)
            if not root.exists():
                if allow_missing:
                    result[f'@missing:{relative}'] = 'missing'
                    continue
                raise FlowError(f'Missing source root: {relative}')
            if root.is_file():
                candidates = [root]
            elif root.is_dir():
                candidates = []
                for directory, dirs, files in os.walk(root, followlinks=False):
                    for name in list(dirs):
                        child = Path(directory) / name
                        if name in SOURCE_EXCLUSIONS:
                            dirs.remove(name)
                        elif child.is_symlink():
                            raise FlowError(f'Symlink source directory rejected: {child}')
                    candidates.extend(Path(directory) / name for name in files)
            else:
                raise FlowError(f'Not a source file/directory: {relative}')
            for path in candidates:
                if not safe_source_name(path):
                    continue
                relative_file = path.relative_to(self.root).as_posix()
                self.p(relative_file)
                if not path.is_file():
                    raise FlowError('Source observation requires regular files.')
                result[relative_file] = sha(path)
        if not result and not allow_missing:
            raise FlowError('Source roots contain no observable application files.')
        return dict(sorted(result.items()))

    def source_identity(self, version: str, component: str, *,
                        frozen: bool = False, allow_missing: bool = False) -> dict[str, Any]:
        if component not in {'backend', 'frontend'}:
            raise FlowError('Unknown source component.')
        roots = self.plan(version, frozen=frozen)['source_roots'][component]
        files = self.source_files(roots, allow_missing=allow_missing)
        return {'roots': roots, 'files': files, 'fingerprint': digest_json(files)}

    def review_observation(self, version: str, artifacts: list[str]) -> dict[str, Any]:
        """Observe decision-relevant content, not checkpoint bookkeeping or chat notes."""
        state = self.workflow_state(version)
        observed = self.observation(version)
        keys = ('version', 'stage', 'resume_stage', 'candidate', 'approved',
                'active_baseline', 'active_backend_handoff', 'frontend_verification',
                'code_start_ref', 'approvals', 'open_questions', 'blockers')
        observed['state'] = digest_json({key: state.get(key) for key in keys})
        observed['runtime_files'] = {'tasks.json': observed['runtime_files']['tasks.json']}
        observed['artifacts'] = {}
        for name in artifacts:
            path = self.p(nonblank(name, 'review artifact'))
            if (not safe_source_name(path) or not path.is_file()
                    or not path.stat().st_size):
                raise FlowError('Review artifacts must be nonempty non-secret files.')
            # These files change when a review/checkpoint is saved; never self-hash them.
            if name in {self.state_path(version), '.project-flow/RESUME.md',
                        self.runtime(version) + '/RESUME.md'}:
                raise FlowError('State and generated resume navigation are not review artifacts.')
            observed['artifacts'][name] = sha(path)
        return observed

    def review_stage(self, version: str, target: str, summary: str, *,
                     artifacts: list[str] | None = None, remaining: str = '') -> dict[str, Any]:
        """Save a question without marking a stage complete or granting authorization."""
        state = self.workflow_state(version)
        if self.registry()['active_version'] != version:
            raise FlowError('Review the active version; switching files does not switch code.')
        if target not in REVIEW_NEXT.get(state['stage'], set()):
            raise FlowError('Review target must be an immediate permitted next stage.')
        self.no_blockers(state)
        summary = nonblank(summary, 'stage summary')
        artifacts = sorted(set(artifacts or []))
        if state['stage'] == 'SPECIFY':
            if not state.get('candidate'):
                raise FlowError('Show a frozen candidate before asking for baseline approval.')
            self.validate_spec(version)
            self.check(f'{version}/{state["candidate"]}', against_draft=True)
        observed = self.review_observation(version, artifacts)
        old = state.get('pending_stage_review')
        signature = digest_json(observed)
        if (old and old.get('status') == 'awaiting_user' and old.get('to_stage') == target
                and old.get('summary') == summary and old.get('remaining') == remaining
                and old.get('content_fingerprint') == signature):
            return {'ok': True, 'version': version, 'review': old,
                    'stage_advanced': False, 'reused': True}
        if old:
            state['history'].append({'event': 'stage-review-superseded', 'review': old, 'at': now()})
        number = 1 + sum(item.get('event') == 'stage-review-requested' for item in state['history'])
        identifier = f'q{number:04d}'
        baseline = state.get('candidate') or state.get('active_baseline')
        ref = f'{version}/{baseline}' if baseline else None
        effects = {
            'READY': f'批准已展示的 {ref} 文档基线；不授权正式实现',
            'BACKEND_BUILD': f'授权按 {ref} 开始后端实现；不自动启动正式前端',
            'FRONTEND_READY': '接受并归档后端交接；不授权正式前端',
            'FRONTEND_BUILD': f'授权按 {ref} 和当前后端交接开始正式前端',
            'DELIVERED': '归档当前系统交付；不执行生产部署',
        }
        effect = effects.get(target, f'开始 {target} 的工作；仍遵守原范围与授权')
        review = {
            'id': identifier, 'version': version, 'from_stage': state['stage'],
            'to_stage': target, 'status': 'awaiting_user', 'baseline_ref': ref,
            'backend_handoff': state.get('active_backend_handoff'),
            'summary': summary, 'remaining': remaining, 'artifacts': artifacts,
            'content_fingerprint': signature, 'created_at': now(),
            'question': f'当前 {state["stage"]} 已具备收尾条件。要进入 {target}（{effect}），还是继续修改当前阶段的内容？也可以暂时停在这里。',
        }
        state['pending_stage_review'] = review
        state['history'].append({'event': 'stage-review-requested', 'review': review.copy(), 'at': now()})
        state['next_action'] = f'等待用户选择：进入 {target}、修改 {state["stage"]} 或暂停；确认点 {identifier}。'
        self.save_state(state)
        self.write_resume_entry(version)
        return {'ok': True, 'version': version, 'review': review, 'stage_advanced': False,
                'agent_readiness_assertion_recorded': True, 'readiness_proven_by_tool': False}

    def review_fresh(self, version: str, review: dict[str, Any]) -> bool:
        return digest_json(self.review_observation(version, review['artifacts'])) == review.get('content_fingerprint')

    def answer_review(self, version: str, identifier: str, decision: str,
                      quote: str, context: str) -> dict[str, Any]:
        state = self.workflow_state(version)
        review = state.get('pending_stage_review')
        if not review or review.get('id') != identifier:
            raise FlowError('No matching pending review; do not apply an old answer to a new question.')
        if self.registry()['active_version'] != version:
            raise FlowError('Answer the active version review only.')
        if decision not in {'advance', 'modify', 'pause'}:
            raise FlowError('Review choice must be advance, modify or pause.')
        nonblank(quote, 'actual user quote')
        nonblank(context, 'message context')
        if decision == 'advance':
            self.no_blockers(state)
            if state['stage'] != review['from_stage'] or not self.review_fresh(version, review):
                raise FlowError('Stage review is stale; reconcile changes and show a new review before advancing.')
            if review.get('status') == 'changes_requested':
                raise FlowError('Changes were requested; finish and show a new review, not the old question.')
        status = {'advance': 'advance_confirmed', 'modify': 'changes_requested', 'pause': 'paused'}[decision]
        answer = {'decision': decision, 'user_quote': quote, 'context_reference': context, 'at': now()}
        review['status'] = status
        review['answer'] = answer
        state['history'].append({'event': 'stage-review-answer', 'review_id': identifier, **answer})
        state['next_action'] = {
            'advance': f'用户已选择进入 {review["to_stage"]}；核对门槛后用对应正式命令推进，不跳过授权。',
            'modify': '按用户反馈继续修改；如涉及已冻结规范或已验收后端，先走 revise/reopen-backend。',
            'pause': '保留当前阶段和成果；新会话先恢复此待确认选择，不自动推进。',
        }[decision]
        self.save_state(state)
        self.write_resume_entry(version)
        return {'ok': True, 'version': version, 'review': review,
                'stage_advanced': False, 'authorization_authenticated': False}

    def guard_review(self, version: str, target: str) -> None:
        """A registered decision cannot be bypassed by a normal transition command.

        Unregistered prompts and natural-language intent remain Agent responsibilities.
        Existing phase/acceptance guards are still applied by the transition itself.
        """
        state = self.workflow_state(version)
        review = state.get('pending_stage_review')
        if not review:
            return
        if (review.get('from_stage') != state['stage'] or review.get('to_stage') != target
                or review.get('status') != 'advance_confirmed'):
            raise FlowError('Pending stage review requires a matching user advance decision first.')
        if not self.review_fresh(version, review):
            raise FlowError('Stage review is stale; present current artifacts and ask again.')

    def close_review(self, version: str, reason: str) -> None:
        """Archive a review only after a real transition/change succeeds."""
        state = self.workflow_state(version)
        review = state.get('pending_stage_review')
        if review:
            completed = (review.get('status') == 'advance_confirmed'
                         and review.get('to_stage') == state['stage'])
            state['history'].append({'event': 'stage-review-completed' if completed else 'stage-review-invalidated',
                                     'review': review, 'reason': reason, 'at': now()})
            state['pending_stage_review'] = None
            if not completed and state.get('resume_stage'):
                state['resume_next_action'] = '恢复原阶段后核对成果，重新评估阶段收尾选择，不沿用旧确认。'
            self.save_state(state)

    def validate_spec(self, version: str) -> dict[str, Any]:
        self.workflow_state(version)
        reviewed = super().validate_spec(version)
        self.plan(version)
        files = scan(self.draft(version))
        if not any(name.startswith('contracts/') for name in files):
            raise FlowError('A frozen version needs a language-neutral contract in contracts/.')
        trace = reviewed['traceability']
        gates = obj(self.draft(version) / 'quality-gates.json')['gates']
        assignments: dict[str, list[str]] = {phase: [] for phase in PHASES}
        for item in trace['acceptance'] + gates:
            if item.get('status') == 'retired':
                continue
            if item.get('phase') not in PHASES:
                raise FlowError(f'Assign check {item["id"]} to backend, frontend or integration.')
            if item.get('required'):
                assignments[item['phase']].append(item['id'])
        if any(not values for values in assignments.values()):
            raise FlowError('Each phase needs required checks, including regression-only changes.')
        reviewed['phase_checks'] = assignments
        return reviewed

    def seal(self, version: str) -> dict[str, Any]:
        state = self.workflow_state(version)
        if state['stage'] != 'SPECIFY':
            self.guard_review(version, 'SPECIFY')
        result = super().seal(version)
        state = self.state(version)
        state['next_action'] = '审阅候选完整规范；主动询问批准进入 READY，或继续修改，不自动开工。'
        self.save_state(state)
        self.close_review(version, 'Candidate changed; present the exact new baseline.')
        self.write_resume_entry(version)
        return result

    def phase_checks(self, ref: str, phase: str) -> tuple[set[str], set[str]]:
        if phase not in PHASES:
            raise FlowError('Unknown verification phase.')
        tree = self.snapshot(ref)
        records = obj(tree / 'traceability.json')['acceptance']
        records += obj(tree / 'quality-gates.json')['gates']
        relevant = [item for item in records if item.get('status') != 'retired'
                    and item.get('phase') == phase]
        return {x['id'] for x in relevant if x.get('required')}, {x['id'] for x in relevant}

    def check(self, ref: str, *, against_draft: bool = False,
              for_build: bool = False) -> dict[str, Any]:
        checked = super().check(ref, against_draft=against_draft or for_build)
        if not for_build:
            return checked
        version, baseline = ref_parts(ref)
        state = self.workflow_state(version)
        stage = state.get('resume_stage') if state['stage'] == 'BLOCKED' else state['stage']
        if self.registry()['active_version'] != version:
            raise FlowError('This is not the active version; no code checkout was performed.')
        if stage not in BUILD_STAGES or state.get('active_baseline') != baseline:
            raise FlowError('Version is not building this baseline in an authorized phase.')
        self.no_blockers(state)
        self.parent_delivered(self.entry(version))
        for kind in ('baseline', 'backend'):
            if not self.has_approval(state, kind, ref, checked['manifest_sha256']):
                raise FlowError(f'Missing matching {kind} approval record.')
        nonblank(state.get('code_start_ref'), 'code_start_ref')
        if stage in FRONT_STAGES:
            handoff = self.check_backend(version, live=True)
            if not self.frontend_approved(state, ref, checked['manifest_sha256'], handoff):
                raise FlowError('Missing frontend approval for this exact backend handoff.')
        checked['build_records_checked'] = True
        checked['phase'] = stage
        return checked

    @staticmethod
    def frontend_approved(state: dict[str, Any], ref: str, digest: str,
                          handoff: dict[str, Any]) -> bool:
        return any(
            a.get('kind') == 'frontend' and a.get('ref') == ref
            and a.get('manifest_sha256') == digest
            and a.get('backend_handoff') == handoff['handoff_id']
            and a.get('backend_handoff_sha256') == handoff['sha256']
            and bool(a.get('user_quote', '').strip())
            and bool(a.get('context_reference', '').strip())
            for a in state.get('approvals', []) if isinstance(a, dict)
        )

    def approve(self, ref: str, kind: str, quote: str, context: str, *,
                code_ref: str | None = None) -> dict[str, Any]:
        if kind not in {'baseline', 'backend', 'frontend'}:
            raise FlowError('Use baseline, backend or frontend; unscoped build approval is not supported.')
        nonblank(quote, 'actual user quote')
        nonblank(context, 'message context')
        checked = self.check(ref, against_draft=True)
        version, baseline = ref_parts(ref)
        state = self.workflow_state(version)
        self.no_blockers(state)
        self.guard_review(version, {'baseline': 'READY', 'backend': 'BACKEND_BUILD', 'frontend': 'FRONTEND_BUILD'}[kind])
        record: dict[str, Any] = {
            'kind': kind, 'ref': ref, 'manifest_sha256': checked['manifest_sha256'],
            'user_quote': quote, 'context_reference': context, 'at': now(),
        }
        if kind == 'baseline':
            if state.get('candidate') != baseline or state['stage'] not in {'SPECIFY', 'READY'}:
                raise FlowError('Only the current candidate may be approved.')
            state.update({'approved': baseline, 'stage': 'READY'})
        else:
            if self.registry()['active_version'] != version:
                raise FlowError('Switch to the intended version and reconcile the code workspace first.')
            if state.get('approved') != baseline or not self.has_approval(
                state, 'baseline', ref, checked['manifest_sha256']
            ):
                raise FlowError('Approve the exact baseline first.')
            self.parent_delivered(self.entry(version))
            record['code_ref'] = nonblank(code_ref, 'component code start ref')
            if kind == 'backend':
                if state['stage'] != 'READY':
                    raise FlowError('Backend authorization requires READY.')
                state.update({'stage': 'BACKEND_BUILD', 'active_baseline': baseline,
                              'code_start_ref': code_ref})
            else:
                if state['stage'] != 'FRONTEND_READY':
                    raise FlowError('Frontend authorization requires an accepted backend in FRONTEND_READY.')
                handoff = self.check_backend(version, live=True)
                record.update({'backend_handoff': handoff['handoff_id'],
                               'backend_handoff_sha256': handoff['sha256']})
                state.update({'stage': 'FRONTEND_BUILD', 'frontend_verification': None})
        state['next_action'] = {
            'baseline': '规范已批准；等待明确后端实施授权。',
            'backend': '按批准基线连续实现全部后端任务，不实现正式前端。',
            'frontend': '核对后端交接与运行环境，按批准原型实现真实前端。',
        }[kind]
        state['approvals'].append(record)
        self.save_state(state)
        self.close_review(version, 'Matching phase approval recorded.')
        self.write_resume_entry(version)
        return {'ok': True, 'ref': ref, 'stage': state['stage'],
                'authorization_authenticated': False, 'recorded_only': True}

    def revise(self, version: str, reason: str) -> dict[str, Any]:
        self.workflow_state(version)
        result = super().revise(version, reason)
        state = self.state(version)
        state['active_backend_handoff'] = None
        state['frontend_verification'] = None
        state['next_action'] = '影响分析并调整草稿；重新冻结和批准，不沿用旧阶段验收。'
        self.save_state(state)
        self.close_review(version, 'Specification reopened; old decision does not authorize revised content.')
        self.write_resume_entry(version)
        return result

    def stage(self, version: str, target: str, reason: str = '', *,
              report_name: str | None = None) -> dict[str, Any]:
        state = self.workflow_state(version)
        old = state['stage']
        if target in REVIEW_NEXT.get(old, set()):
            self.guard_review(version, target)
        edges = {
            'DISCOVER': {'ITERATE', 'SPECIFY'}, 'SCOPE': {'ITERATE', 'SPECIFY'},
            'ITERATE': {'SPECIFY'}, 'BACKEND_BUILD': {'BACKEND_VERIFY'},
            'BACKEND_VERIFY': {'BACKEND_BUILD'}, 'FRONTEND_BUILD': {'FRONTEND_VERIFY'},
            'FRONTEND_VERIFY': {'FRONTEND_BUILD', 'INTEGRATION_VERIFY'},
            'INTEGRATION_VERIFY': {'FRONTEND_BUILD'},
        }
        if target == 'BLOCKED' and old not in {'DELIVERED', 'CANCELLED', 'BLOCKED'}:
            nonblank(reason, 'block reason')
            state['resume_stage'] = old
            state['resume_next_action'] = state.get('next_action')
            state['blockers'].append({'id': f'BLOCK-{len(state["history"])+1}', 'reason': reason})
        elif old == 'BLOCKED' and target == state.get('resume_stage'):
            self.no_blockers(state)
            if target in BUILD_STAGES:
                self.check(f'{version}/{state["active_baseline"]}', for_build=True)
            state['resume_stage'] = None
        elif target not in edges.get(old, set()):
            raise FlowError('Invalid stage transition; approval, accept-backend, revise and deliver have dedicated commands.')
        else:
            if target in BUILD_STAGES:
                self.check(f'{version}/{state["active_baseline"]}', for_build=True)
            if target == 'INTEGRATION_VERIFY':
                report = self.verify_phase(version, 'frontend', nonblank(report_name, 'frontend report'))
                self.check_tasks(version, 'frontend')
                required, allowed = self.phase_checks(f'{version}/{state["active_baseline"]}', 'frontend')
                phase_evidence = self.evidence_files(version, report, required, allowed)
                state['frontend_verification'] = {
                    'evidence_sha256': phase_evidence,
                    'report': report_name, 'sha256': sha(self.p(report_name)),
                    'source_fingerprint': report['source_fingerprint'],
                    'backend_handoff': state['active_backend_handoff'],
                }
        actions = {
            'ITERATE': '继续迭代当前版本原型、领域与数据契约。',
            'SPECIFY': '整理完整规范并核查缺口；冻结展示候选后等待用户批准。',
            'BACKEND_BUILD': '继续未完成后端任务或修复，不实现正式前端。',
            'BACKEND_VERIFY': '完成独立后端验收与交接，满足门槛后停在 FRONTEND_READY。',
            'FRONTEND_BUILD': '根据批准原型和已验收后端继续实现前端。',
            'FRONTEND_VERIFY': '完成前端真实接口与交互验收，保留实际证据。',
            'INTEGRATION_VERIFY': '完成本版系统验收，满足门槛后归档，不部署生产。',
            'BLOCKED': '解决已记录阻塞并核对证据，再恢复原阶段。',
        }
        if old == 'BLOCKED':
            state['next_action'] = state.pop('resume_next_action', None) or actions.get(target, state.get('next_action'))
        else:
            state['next_action'] = actions.get(target, state.get('next_action'))
        state['stage'] = target
        state['history'].append({'event': 'stage', 'from': old, 'to': target,
                                 'reason': reason, 'at': now()})
        self.save_state(state)
        self.close_review(version, 'Stage changed; old decision cannot transfer to another stage.')
        self.write_resume_entry(version)
        return {'ok': True, 'version': version, 'stage': target}

    def evidence_files(self, version: str, report: dict[str, Any],
                       required: set[str], allowed: set[str]) -> dict[str, str]:
        checks = self.id_map(report.get('checks'), 'verification checks')
        if not required <= checks.keys() or checks.keys() - allowed:
            raise FlowError('Missing required checks or unknown/cross-phase check IDs.')
        code_ref = nonblank(report.get('code_ref'), 'verified code_ref')
        prefix = self.runtime(version) + '/evidence/'
        files: dict[str, str] = {}
        for cid, check in checks.items():
            if check.get('code_ref') != code_ref:
                raise FlowError(f'Stale code_ref for {cid}.')
            if cid in required and check.get('status') != 'passed':
                raise FlowError(f'Required check did not pass: {cid}')
            if check.get('status') == 'skipped' and cid not in required:
                nonblank(check.get('reason'), 'skip reason')
                continue
            if check.get('status') != 'passed':
                raise FlowError(f'Unresolved check: {cid}')
            paths = check.get('evidence')
            if not isinstance(paths, list) or not paths:
                raise FlowError(f'Passed check has no evidence: {cid}')
            for name in paths:
                if not isinstance(name, str) or not name.startswith(prefix):
                    raise FlowError('Evidence must belong to this version evidence directory.')
                path = self.p(name)
                if not safe_source_name(path) or not path.is_file() or not path.stat().st_size:
                    raise FlowError('Evidence file is missing, secret-like or empty.')
                files[name] = sha(path)
        return files

    def check_tasks(self, version: str, phase: str) -> None:
        state = self.workflow_state(version)
        tasks = obj(self.p(self.runtime(version) + '/tasks.json'))
        if tasks.get('version') != version or tasks.get('schema_version') != WORKFLOW:
            raise FlowError('Task identity mismatch.')
        records = self.id_map(tasks.get('tasks'), 'tasks')
        for item in records.values():
            if item.get('phase') not in PHASES:
                raise FlowError('Every task must declare its phase.')
            deps = item.get('depends_on', [])
            if not isinstance(deps, list) or any(d not in records for d in deps):
                raise FlowError('Task has missing dependencies.')
            order = {phase: index for index, phase in enumerate(PHASES)}
            if any(order.get(records[d].get('phase'), 99) > order[item['phase']] for d in deps):
                raise FlowError('Earlier-phase task cannot depend on a later-phase task.')
        visiting: set[str] = set()
        visited: set[str] = set()
        def visit(identifier: str) -> None:
            if identifier in visiting:
                raise FlowError('Cyclic task dependencies.')
            if identifier in visited:
                return
            visiting.add(identifier)
            for dependency in records[identifier].get('depends_on', []):
                visit(dependency)
            visiting.remove(identifier)
            visited.add(identifier)
        for identifier in records:
            visit(identifier)
        selected = [item for item in records.values() if item.get('phase') == phase]
        if not selected:
            raise FlowError(f'No {phase} tasks; record verification-only work for unchanged components.')
        for item in selected:
            if item.get('status') != 'done' or item.get('baseline_ref') != f'{version}/{state["active_baseline"]}':
                raise FlowError(f'Incomplete or stale {phase} task: {item["id"]}')
            if any(records[d].get('status') != 'done' for d in item.get('depends_on', [])):
                raise FlowError('A completed task has unfinished dependencies.')

    def verify_phase(self, version: str, phase: str, report_name: str) -> dict[str, Any]:
        if phase not in {'backend', 'frontend'}:
            raise FlowError('Use final verification report for integration.')
        state = self.workflow_state(version)
        ref = f'{version}/{state["active_baseline"]}'
        checked = self.check(ref, for_build=True)
        report = obj(self.p(report_name))
        if (report.get('schema_version') != WORKFLOW or report.get('version') != version
            or report.get('phase') != phase or report.get('baseline_ref') != ref
            or report.get('manifest_sha256') != checked['manifest_sha256']):
            raise FlowError('Phase report must bind the exact version, baseline and phase.')
        if report.get('open_blockers') != []:
            raise FlowError('Phase report must explicitly have no open blockers.')
        source = self.source_identity(version, phase, frozen=True)
        if report.get('source_fingerprint') != source['fingerprint']:
            raise FlowError('Phase report source fingerprint is stale or wrong.')
        if phase == 'frontend':
            handoff = self.check_backend(version, live=True)
            if (report.get('backend_handoff') != handoff['handoff_id'] or
                report.get('backend_handoff_sha256') != handoff['sha256']):
                raise FlowError('Frontend report must bind the accepted backend handoff.')
        required, allowed = self.phase_checks(ref, phase)
        self.evidence_files(version, report, required, allowed)
        return report

    def accept_backend(self, version: str, report_name: str, handoff_name: str) -> dict[str, Any]:
        state = self.workflow_state(version)
        if state['stage'] != 'BACKEND_VERIFY':
            raise FlowError('Backend acceptance requires BACKEND_VERIFY.')
        self.guard_review(version, 'FRONTEND_READY')
        report = self.verify_phase(version, 'backend', report_name)
        self.check_tasks(version, 'backend')
        source = self.source_identity(version, 'backend', frozen=True)
        handoff = obj(self.p(handoff_name))
        if (handoff.get('schema_version') != WORKFLOW or handoff.get('version') != version
            or handoff.get('baseline_ref') != report['baseline_ref']
            or handoff.get('code_ref') != report['code_ref']):
            raise FlowError('Handoff identity does not match the verified backend.')
        if handoff.get('open_blockers') != [] or not isinstance(handoff.get('known_limitations'), list):
            raise FlowError('Handoff must list limitations and have no blocking integration gap.')
        keys = ('runbook', 'endpoint_inventory', 'environment_template', 'smoke_instructions')
        attachments: dict[str, str] = {}
        for key in keys:
            path = self.p(nonblank(handoff.get(key), key))
            if not safe_source_name(path) or not path.is_file() or not path.stat().st_size:
                raise FlowError('Handoff attachment is empty or a possible secret.')
            attachments[handoff[key]] = sha(path)
        required, allowed = self.phase_checks(report['baseline_ref'], 'backend')
        evidence = self.evidence_files(version, report, required, allowed)
        packages = state['backend_handoffs']
        number = max([int(key[1:]) for key in packages] + [0]) + 1
        identifier = f'h{number:03d}'
        final = self.p(f'docs/releases/{version}/implementation/backend/{identifier}', exists=False)
        if final.exists():
            raise FlowError('Handoff directory exists; inspect interruption instead of overwriting.')
        final.parent.mkdir(parents=True, exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix='.handoff-', dir=final.parent))
        try:
            archived = json.loads(json.dumps(handoff))
            for key in keys:
                original = handoff[key]
                extension = self.p(original).suffix or '.txt'
                destination = f'attachments/{key}{extension}'
                self.copy_file(original, temp, destination, attachments[original])
                archived[key] = destination
            tree = self.snapshot(report['baseline_ref'])
            for relative, expected in scan(tree, snapshot=True).items():
                if relative.startswith('contracts/'):
                    destination = local(temp, relative, exists=False)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(local(tree, relative), destination)
                    if sha(destination) != expected:
                        raise FlowError('Contract changed during handoff archival.')
            archived_report = json.loads(json.dumps(report))
            for check in archived_report['checks']:
                saved = []
                for relative in (check.get('evidence', []) if check.get('status') == 'passed' else []):
                    destination = 'evidence/' + relative.split('/evidence/', 1)[1]
                    self.copy_file(relative, temp, destination, evidence[relative])
                    saved.append(destination)
                check['evidence'] = saved
            write_json(temp / 'handoff.json', archived, exclusive=True)
            write_json(temp / 'verification.json', archived_report, exclusive=True)
            backend_tasks = obj(self.p(self.runtime(version) + '/tasks.json'))
            backend_tasks['tasks'] = [item for item in backend_tasks['tasks'] if item.get('phase') == 'backend']
            write_json(temp / 'backend-tasks.json', backend_tasks, exclusive=True)
            (temp / 'HANDOFF.md').write_text(
                f'# 后端交接 {version}/{identifier}\n\n'
                f'规范：{report["baseline_ref"]}；代码：{report["code_ref"]}。\n\n'
                '先读 handoff.json 指向的运行、接口、环境与冒烟说明；契约在 contracts/。\n'
                '本包不包含生产密钥，不替代批准规范和原型，不证明远程服务当前在线。\n'
                '新会话应重新启动/探测服务并取得 frontend 阶段授权，不能沿用旧进程句柄。\n',
                encoding='utf-8',
            )
            manifest = {
                'schema_version': WORKFLOW, 'kind': 'backend-handoff', 'version': version,
                'handoff_id': identifier, 'baseline_ref': report['baseline_ref'],
                'manifest_sha256': report['manifest_sha256'], 'code_ref': report['code_ref'],
                'backend_source': source, 'created_at': now(), 'files': scan(temp, snapshot=True),
            }
            write_json(temp / 'manifest.json', manifest, exclusive=True)
            if self.source_identity(version, 'backend', frozen=True) != source:
                raise FlowError('Backend source changed while creating handoff.')
            self.check(report['baseline_ref'], for_build=True)
            temp.rename(final)
        finally:
            if temp.exists():
                shutil.rmtree(temp)
        packages[identifier] = {
            'manifest': (final / 'manifest.json').relative_to(self.root).as_posix(),
            'sha256': sha(final / 'manifest.json'), 'baseline_ref': report['baseline_ref'],
            'code_ref': report['code_ref'],
        }
        state.update({'active_backend_handoff': identifier, 'stage': 'FRONTEND_READY',
                      'frontend_verification': None,
                      'next_action': '后端已验收并归档；询问开始前端、继续调整或先换会话。'})
        self.save_state(state)
        self.close_review(version, 'Backend acceptance archived.')
        self.write_resume_entry(version)
        return {'ok': True, 'version': version, 'stage': 'FRONTEND_READY',
                'handoff_id': identifier, 'manifest': packages[identifier]['manifest'],
                'frontend_started': False, 'tests_executed_by_this_command': False}

    def copy_file(self, name: str, target: Path, relative: str, expected: str) -> None:
        destination = local(target, relative, exists=False)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.p(name), destination)
        if sha(destination) != expected:
            raise FlowError('File changed during archival.')

    def check_backend(self, version: str, identifier: str | None = None, *,
                      live: bool = True) -> dict[str, Any]:
        state = self.workflow_state(version)
        identifier = identifier or state.get('active_backend_handoff')
        record = state['backend_handoffs'].get(identifier)
        if not isinstance(record, dict):
            raise FlowError('No accepted backend handoff; backend completion cannot be inferred.')
        expected = f'docs/releases/{version}/implementation/backend/{identifier}/manifest.json'
        if record.get('manifest') != expected:
            raise FlowError('Noncanonical backend handoff path.')
        path = self.p(expected)
        if sha(path) != record.get('sha256'):
            raise FlowError('Backend handoff manifest drift.')
        manifest = obj(path)
        checked = self.check(record['baseline_ref'])
        if (manifest.get('schema_version') != WORKFLOW or manifest.get('kind') != 'backend-handoff'
            or manifest.get('version') != version or manifest.get('handoff_id') != identifier
            or manifest.get('baseline_ref') != record['baseline_ref']
            or manifest.get('manifest_sha256') != checked['manifest_sha256']
            or manifest.get('code_ref') != record['code_ref']):
            raise FlowError('Backend handoff identity mismatch.')
        files = scan(path.parent, snapshot=True)
        files.pop('manifest.json')
        if changed(differences(manifest['files'], files)):
            raise FlowError('Backend handoff file drift.')
        frozen_contracts = {k: v for k, v in scan(self.snapshot(record['baseline_ref']), snapshot=True).items() if k.startswith('contracts/')}
        packaged_contracts = {k: v for k, v in files.items() if k.startswith('contracts/')}
        if frozen_contracts != packaged_contracts:
            raise FlowError('Handoff contracts differ from the pinned specification.')
        if live:
            if identifier != state.get('active_backend_handoff') or record['baseline_ref'] != f'{version}/{state.get("active_baseline")}':
                raise FlowError('Backend handoff is not active for the current baseline.')
            self.check(record['baseline_ref'], against_draft=True)
            source = self.source_identity(version, 'backend', frozen=True)
            if source != manifest.get('backend_source'):
                raise FlowError('Backend source changed after acceptance; revalidate and create a new handoff.')
        return {'ok': True, 'handoff_id': identifier, 'sha256': record['sha256'],
                'baseline_ref': record['baseline_ref'], 'code_ref': record['code_ref'],
                'manifest': expected, 'live_source_checked': live}

    def reopen_backend(self, version: str, reason: str) -> dict[str, Any]:
        nonblank(reason, 'backend repair reason')
        state = self.workflow_state(version)
        self.no_blockers(state)
        if self.registry()['active_version'] != version:
            raise FlowError('Only the active version may reopen its backend.')
        if state['stage'] not in FRONT_STAGES | {'FRONTEND_READY'}:
            raise FlowError('reopen-backend is for accepted backend code defects, not specification changes.')
        ref = f'{version}/{state["active_baseline"]}'
        checked = self.check(ref, against_draft=True)
        if not self.has_approval(state, 'backend', ref, checked['manifest_sha256']):
            raise FlowError('Missing backend authorization for unchanged specification.')
        state['history'].append({'event': 'backend-reopened', 'reason': reason,
                                 'superseded_handoff': state['active_backend_handoff'], 'at': now()})
        state.update({'stage': 'BACKEND_BUILD', 'active_backend_handoff': None,
                      'frontend_verification': None,
                      'next_action': '按原批准语义修复后端，重新验收并生成新交接；不要擅改契约。'})
        tasks_path = self.p(self.runtime(version) + '/tasks.json')
        tasks = obj(tasks_path)
        for task in tasks['tasks']:
            task['previous_status'] = task.get('status')
            task['status'] = 'needs_revalidation'
        write_json(tasks_path, tasks)
        self.save_state(state)
        self.close_review(version, 'Backend reopened; verify a new handoff before advancing.')
        self.write_resume_entry(version)
        return {'ok': True, 'stage': 'BACKEND_BUILD', 'old_handoffs_preserved': True}

    def deliver(self, version: str, report_name: str) -> dict[str, Any]:
        state = self.workflow_state(version)
        if state['stage'] != 'INTEGRATION_VERIFY':
            raise FlowError('Delivery requires INTEGRATION_VERIFY, not merely backend completion.')
        self.guard_review(version, 'DELIVERED')
        self.check_backend(version, live=True)
        front = state.get('frontend_verification')
        if not front or sha(self.p(front['report'])) != front.get('sha256'):
            raise FlowError('Frontend phase report is missing or changed.')
        self.verify_phase(version, 'frontend', front['report'])
        for name, expected in front.get('evidence_sha256', {}).items():
            if sha(self.p(name)) != expected:
                raise FlowError('Frontend phase evidence changed after phase verification.')
        self.check_tasks(version, 'backend')
        self.check_tasks(version, 'frontend')
        report = obj(self.p(report_name))
        if report.get('phase') != 'integration':
            raise FlowError('Final report phase must be integration.')
        for component in ('backend', 'frontend'):
            identity = self.source_identity(version, component, frozen=True)
            if report.get('source_fingerprints', {}).get(component) != identity['fingerprint']:
                raise FlowError(f'Final report has stale {component} source fingerprint.')
        handoff = self.check_backend(version, live=True)
        if (report.get('backend_handoff') != handoff['handoff_id'] or
            report.get('backend_handoff_sha256') != handoff['sha256']):
            raise FlowError('Final report is bound to another backend handoff.')
        result = super().deliver(version, report_name)
        self.close_review(version, 'System delivery archived; no production deployment performed.')
        self.write_resume_entry(version)
        return result

    def check_delivery(self, version: str) -> dict[str, Any]:
        checked = super().check_delivery(version)
        state = self.state(version)
        self.workflow_state(version)
        report = obj(self.p(f'docs/releases/{version}/delivery/verification.json'))
        if report.get('schema_version') != WORKFLOW:
            raise FlowError('Unsupported delivery report schema.')
        handoff = self.check_backend(version, report.get('backend_handoff'), live=False)
        if handoff['sha256'] != report.get('backend_handoff_sha256'):
            raise FlowError('Delivery backend handoff binding mismatch.')
        return checked

    def state_observation(self, version: str) -> str:
        state = self.state(version).copy()
        # Updating the latest checkpoint pointer does not make that checkpoint stale.
        state.pop('last_checkpoint', None)
        state.pop('checkpoint_history', None)
        return digest_json(state)

    def observation(self, version: str) -> dict[str, Any]:
        state = self.workflow_state(version)
        runtime = self.runtime(version)
        observed: dict[str, Any] = {
            'state': self.state_observation(version),
            'draft': scan(self.draft(version)),
            'runtime_files': {}, 'sources': {},
        }
        for relative in ('tasks.json', 'decisions.md', 'handoff.md'):
            path = self.p(f'{runtime}/{relative}', exists=False)
            observed['runtime_files'][relative] = sha(path) if path.exists() else 'missing'
        for component in ('backend', 'frontend'):
            observed['sources'][component] = self.source_identity(
                version, component, allow_missing=True
            )
        if state.get('candidate'):
            observed['baseline'] = self.check(f'{version}/{state["candidate"]}')['manifest_sha256']
        return observed

    def checkpoint(self, version: str, notes_name: str, next_action: str, *,
                   expected_previous: str | None = None) -> dict[str, Any]:
        state = self.workflow_state(version)
        notes_path = self.p(notes_name)
        if not safe_source_name(notes_path) or not notes_path.is_file() or not notes_path.stat().st_size:
            raise FlowError('Checkpoint notes must be a nonempty non-secret text file.')
        notes_text = notes_path.read_text(encoding='utf-8')
        previous = state.get('last_checkpoint')
        actual_previous = previous['id'] if previous else 'none'
        if expected_previous is not None and expected_previous != actual_previous:
            raise FlowError('Checkpoint pointer changed; reconcile the newer session before writing.')
        state['next_action'] = nonblank(next_action, 'next action')
        self.save_state(state)
        observed = self.observation(version)
        number = len(state['checkpoint_history']) + 1
        identifier = f'c{number:04d}'
        folder = self.p(f'{self.runtime(version)}/checkpoints/{identifier}', exists=False)
        if folder.exists():
            raise FlowError('Checkpoint directory exists; never overwrite session history.')
        folder.parent.mkdir(parents=True, exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix='.checkpoint-', dir=folder.parent))
        try:
            payload = {
                'schema_version': WORKFLOW, 'kind': 'session-checkpoint', 'version': version,
                'id': identifier, 'stage': state['stage'], 'resume_stage': state.get('resume_stage'),
                'baseline_ref': f'{version}/{state["candidate"]}' if state.get('candidate') else None,
                'active_backend_handoff': state.get('active_backend_handoff'),
                'pending_stage_review': state.get('pending_stage_review'),
                'next_action': next_action, 'created_at': now(), 'observed': observed,
                'environment_recheck_required': True,
            }
            write_json(temp / 'checkpoint.json', payload, exclusive=True)
            (temp / 'notes.md').write_text(notes_text, encoding='utf-8')
            (temp / 'RESUME.md').write_text(self.resume_text(version, identifier), encoding='utf-8')
            write_json(temp / 'manifest.json', {
                'schema_version': WORKFLOW, 'kind': 'checkpoint-manifest',
                'version': version, 'id': identifier, 'files': scan(temp, snapshot=True),
            }, exclusive=True)
            if self.observation(version) != observed:
                raise FlowError('Workspace changed during checkpoint; stop concurrent writers and retry.')
            temp.rename(folder)
        finally:
            if temp.exists():
                shutil.rmtree(temp)
        pointer = {'id': identifier,
                   'manifest': (folder / 'manifest.json').relative_to(self.root).as_posix(),
                   'sha256': sha(folder / 'manifest.json')}
        state['last_checkpoint'] = pointer
        state['checkpoint_history'].append(pointer)
        self.save_state(state)
        self.write_resume_entry(version)
        return {'ok': True, 'version': version, 'checkpoint': identifier,
                'stage_advanced': False, 'entry': f'{self.runtime(version)}/RESUME.md'}

    def resume_text(self, version: str, checkpoint: str | None = None) -> str:
        state = self.state(version)
        latest = checkpoint or (state.get('last_checkpoint') or {}).get('id', '尚无检查点')
        review = state.get('pending_stage_review')
        review_text = ('\n## 阶段确认点\n\n' + f'{review["id"]} / {review["status"]}\n\n'
                       + review['question'] + '\n\n先核对当前内容与已记录回答，不把换会话视为同意。\n') if review else ''
        return (
            f'# {version} 新会话续接入口\n\n'
            f'阶段提示：{state["stage"]}；检查点：{latest}。状态主源为 state.json，本文是导航。\n\n'
            '```text\n$prototype-to-product\n'
            f'继续当前工作区的 {version}。先运行 resume 检查并读取当前阶段资料；\n'
            '沿用仍有效的已批准决定，只推进已授权范围，不重新从零规划。\n'
            '若文件或代码已变化，先核对差异，不恢复旧文件覆盖现状。\n```\n\n'
            f'下一步提示：{state.get("next_action", "读取当前状态")}\n\n'
            '新会话必须检查实际工作目录、未提交修改、环境、服务与契约。\n'
            '旧日志、端口号和进程 PID 不代表当前服务可用；不要复制密钥到交接资料。\n'
            '会话切换不等于新产品版本、新基线或新的构建授权。\n'
            'SPECIFY 中继续整理不等于批准；READY 中继续查看不等于授权后端。\n'
            '下一阶段的具体说法见技能包 USAGE.zh-CN.md；基线号以当前 state 为准。\n'
            + review_text
        )

    def write_resume_entry(self, version: str) -> None:
        text = self.resume_text(version)
        self.p(f'{self.runtime(version)}/RESUME.md', exists=False).write_text(text, encoding='utf-8')
        if self.registry()['active_version'] == version:
            self.p('.project-flow/RESUME.md', exists=False).write_text(
                f'# 当前版本续接\n\n当前指针：{version}。\n\n'
                f'读取 `versions/{version}/RESUME.md`，以 project.json 和目标版 state.json 为准。\n',
                encoding='utf-8',
            )

    def read_checkpoint(self, version: str, identifier: str | None = None) -> dict[str, Any]:
        state = self.workflow_state(version)
        if identifier is None:
            record = state.get('last_checkpoint')
        else:
            record = next((item for item in state['checkpoint_history'] if item['id'] == identifier), None)
        if not record:
            raise FlowError('No registered checkpoint.')
        identifier = record['id']
        expected = f'{self.runtime(version)}/checkpoints/{identifier}/manifest.json'
        if record.get('manifest') != expected:
            raise FlowError('Noncanonical checkpoint manifest path.')
        path = self.p(expected)
        if sha(path) != record['sha256']:
            raise FlowError('Checkpoint manifest drift.')
        manifest = obj(path)
        if (manifest.get('schema_version') != WORKFLOW or manifest.get('kind') != 'checkpoint-manifest'
            or manifest.get('version') != version or manifest.get('id') != identifier):
            raise FlowError('Checkpoint identity mismatch.')
        files = scan(path.parent, snapshot=True)
        files.pop('manifest.json')
        if changed(differences(manifest['files'], files)):
            raise FlowError('Checkpoint content drift.')
        payload = obj(path.parent / 'checkpoint.json')
        if (payload.get('schema_version') != WORKFLOW or payload.get('kind') != 'session-checkpoint'
            or payload.get('version') != version or payload.get('id') != identifier):
            raise FlowError('Checkpoint payload identity mismatch.')
        return payload

    def resume(self, version: str | None = None, *,
               identifier: str | None = None) -> dict[str, Any]:
        version = version or self.registry()['active_version']
        state = self.workflow_state(version)
        warnings: list[str] = []
        checkpoint = None
        drift: list[str] = []
        if state.get('last_checkpoint') or identifier:
            checkpoint = self.read_checkpoint(version, identifier)
            current = self.observation(version)
            for key in set(current) | set(checkpoint['observed']):
                if current.get(key) != checkpoint['observed'].get(key):
                    drift.append(key)
        else:
            warnings.append('No checkpoint: reconstruct a minimal handoff from current files; do not replay completed work.')
        if self.registry()['active_version'] != version:
            warnings.append('Requested version is not active; this read did not switch documents or code.')
        effective_stage = state.get('resume_stage') if state['stage'] == 'BLOCKED' else state['stage']
        if effective_stage in BUILD_STAGES or effective_stage == 'FRONTEND_READY':
            try:
                if effective_stage == 'FRONTEND_READY':
                    self.check_backend(version, live=True)
                else:
                    self.check(f'{version}/{state["active_baseline"]}', for_build=True)
            except FlowError as error:
                warnings.append(str(error))
        if state['stage'] == 'BLOCKED':
            warnings.append('BLOCKED stays BLOCKED; a new conversation does not resolve blockers.')
        if drift:
            warnings.append('Files changed since checkpoint: reconcile with current workspace; never restore by overwriting.')
        review = state.get('pending_stage_review')
        review_fresh = None
        if review:
            try:
                review_fresh = self.review_fresh(version, review)
            except (FlowError, OSError, ValueError) as error:
                review_fresh = False
                warnings.append(f'Review artifacts unavailable: {error}')
            if not review_fresh and review.get('status') != 'changes_requested':
                warnings.append('Stage review content changed; reconcile and ask against current artifacts.')
        waiting = bool(review and review.get('status') in {'awaiting_user', 'paused'})
        historical = bool(identifier and identifier != (state.get('last_checkpoint') or {}).get('id'))
        return {
            'ok': True, 'version': version, 'stage': state['stage'],
            'baseline': state.get('active_baseline') or state.get('candidate'),
            'checkpoint': checkpoint['id'] if checkpoint else None,
            'ready_to_continue': bool(checkpoint) and not warnings and not historical
                                 and state['stage'] not in {'DELIVERED', 'CANCELLED'} and not waiting,
            'pending_stage_review': review, 'awaiting_stage_decision': waiting,
            'stage_review_fresh': review_fresh,
            'historical_read_only': historical, 'drift': drift, 'warnings': warnings,
            'next_action': state.get('next_action'),
            'read_first': [self.state_path(version), self.runtime(version) + '/tasks.json',
                           self.runtime(version) + '/decisions.md', self.runtime(version) + '/handoff.md'],
            'checkpoint_notes': (f'{self.runtime(version)}/checkpoints/{checkpoint["id"]}/notes.md'
                                 if checkpoint else None),
            'environment_recheck_required': True, 'files_modified': False,
            'stage_advanced': False,
        }

    def switch(self, version: str) -> dict[str, Any]:
        result = super().switch(version)
        self.workflow_state(version)
        self.write_resume_entry(version)
        return result


    def doctor(self) -> dict[str, Any]:
        result = super().doctor()
        for version in self.registry()['versions']:
            try:
                state = self.workflow_state(version)
                if state['stage'] in FRONT_STAGES | {'FRONTEND_READY'}:
                    self.check_backend(version, live=True)
                for identifier in state['backend_handoffs']:
                    self.check_backend(version, identifier, live=False)
                for pointer in state['checkpoint_history']:
                    self.read_checkpoint(version, pointer['id'])
                for parent, registered in (
                    (f'docs/releases/{version}/implementation/backend', set(state['backend_handoffs'])),
                    (f'{self.runtime(version)}/checkpoints', {p['id'] for p in state['checkpoint_history']}),
                ):
                    path = self.p(parent, exists=False)
                    if path.exists():
                        for child in path.iterdir():
                            if child.name not in registered:
                                result['problems'].append(f'{version}: unregistered handoff/checkpoint {child.name}')
            except (FlowError, OSError, ValueError) as error:
                result['problems'].append(f'{version}: {error}')
        result['ok'] = not result['problems']
        return result


def parser() -> argparse.ArgumentParser:
    top = store.parser()
    # Compose storage operations with current phase and session operations.
    sub = next(action for action in top._actions if isinstance(action, argparse._SubParsersAction))
    sub.choices['stage'].add_argument('--report')
    extra = ('checkpoint', 'resume', 'source-id', 'accept-backend', 'check-backend',
             'reopen-backend', 'review-stage', 'answer-review')
    for command in extra:
        p = sub.add_parser(command)
        p.add_argument('--root', default='.')
        p.add_argument('--version', required=command != 'resume')
        if command == 'checkpoint':
            p.add_argument('--notes', required=True)
            p.add_argument('--next-action', required=True)
            p.add_argument('--expected-previous')
        if command == 'resume':
            p.add_argument('--checkpoint')
        if command == 'source-id':
            p.add_argument('--component', choices=['backend', 'frontend'], required=True)
            p.add_argument('--frozen', action='store_true')
            p.add_argument('--allow-missing', action='store_true')
        if command == 'accept-backend':
            p.add_argument('--report', required=True)
            p.add_argument('--handoff', required=True)
        if command == 'check-backend':
            p.add_argument('--handoff-id')
            p.add_argument('--archive-only', action='store_true')
        if command == 'reopen-backend':
            p.add_argument('--reason', required=True)
        if command == 'review-stage':
            p.add_argument('--to', required=True)
            p.add_argument('--summary', required=True)
            p.add_argument('--artifact', action='append', default=[])
            p.add_argument('--remaining', default='')
        if command == 'answer-review':
            p.add_argument('--review-id', required=True)
            p.add_argument('--decision', choices=['advance', 'modify', 'pause'], required=True)
            p.add_argument('--quote', required=True)
            p.add_argument('--context', required=True)
    return top


def dispatch(flow: Flow, args: argparse.Namespace) -> dict[str, Any]:
    c = args.command
    if c == 'review-stage':
        return flow.review_stage(args.version, args.to, args.summary,
                                 artifacts=args.artifact, remaining=args.remaining)
    if c == 'answer-review':
        return flow.answer_review(args.version, args.review_id, args.decision, args.quote, args.context)
    if c == 'checkpoint':
        return flow.checkpoint(args.version, args.notes, args.next_action,
                               expected_previous=args.expected_previous)
    if c == 'resume':
        return flow.resume(args.version, identifier=args.checkpoint)
    if c == 'source-id':
        return {'ok': True, **flow.source_identity(args.version, args.component,
                                                   frozen=args.frozen, allow_missing=args.allow_missing)}
    if c == 'accept-backend':
        return flow.accept_backend(args.version, args.report, args.handoff)
    if c == 'check-backend':
        return flow.check_backend(args.version, args.handoff_id, live=not args.archive_only)
    if c == 'reopen-backend':
        return flow.reopen_backend(args.version, args.reason)
    if c == 'stage':
        return flow.stage(args.version, args.to, args.reason, report_name=args.report)
    return store.dispatch(flow, args)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        flow = Flow(args.root)
        read_only = {'status', 'check', 'diff', 'history', 'check-delivery', 'doctor',
                     'resume', 'source-id', 'check-backend'}
        if args.command in read_only:
            result = dispatch(flow, args)
        else:
            with writer_lock(flow):
                result = dispatch(flow, args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('ok') else 1
    except (FlowError, OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
