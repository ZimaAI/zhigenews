#!/usr/bin/env python3
"""Local versioned specification manager. Python 3.10+, standard library only.

Copies real snapshots; never runs project code, Git, deployments or migrations.
Approval and test records are assertions, NOT authenticated signatures or test execution.
CLI writes use an exclusive local lock. Individual JSON writes are atomic; a whole
multi-file operation is NOT a database transaction. See references/tooling.md.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile
from typing import Any, Iterator
from zipfile import ZipFile, ZIP_DEFLATED

SCHEMA = 4
SKILL_VERSION = '4.1.0'
EXCLUDED_DIRS = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', '.pytest_cache',
                 '.mypy_cache', '.ruff_cache', '.next', 'dist', 'build', 'coverage',
                 'test-results', 'playwright-report'}
DOCUMENTS = {
    'index': 'spec/00-index.md', 'requirements': 'spec/01-requirements.md',
    'ux': 'spec/02-ux.md', 'domain': 'spec/03-domain.md',
    'architecture': 'spec/04-architecture.md', 'acceptance': 'spec/05-acceptance.md',
    'implementation': 'spec/06-implementation.md', 'changes': 'spec/07-changes.md',
    'migration': 'spec/08-compatibility-migration.md', 'release_plan': 'spec/09-release-plan.md',
}
STAGES = {'DISCOVER', 'SCOPE', 'ITERATE', 'SPECIFY', 'READY',
          'BACKEND_BUILD', 'BACKEND_VERIFY', 'FRONTEND_READY',
          'FRONTEND_BUILD', 'FRONTEND_VERIFY', 'INTEGRATION_VERIFY',
          'DELIVERED', 'BLOCKED', 'CANCELLED'}


class FlowError(ValueError):
    """A local invariant or record check failed."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def nonblank(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FlowError(f'{field} must be a nonempty string.')
    return value


def version_label(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', value) or value.endswith('.'):
        raise FlowError('Invalid version label; use e.g. v1.1.0 (no paths).')
    if value.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        raise FlowError('Reserved version label.')
    return value


def ref_parts(ref: str, *, draft: bool = False) -> tuple[str, str]:
    if not isinstance(ref, str) or ref.count('/') != 1:
        raise FlowError('Reference must be VERSION/bNNN, e.g. v1.1.0/b001.')
    version, baseline = ref.split('/')
    version_label(version)
    if not re.fullmatch(r'b[0-9]{3,}', baseline) and not (draft and baseline == 'draft'):
        raise FlowError('Invalid baseline reference.')
    return version, baseline


def local(root: Path, relative: str, *, exists: bool = True) -> Path:
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative:
        raise FlowError(f'Invalid relative path: {relative!r}')
    parts = relative.split('/')
    if PurePosixPath(relative).is_absolute() or any(p in {'', '.', '..'} for p in parts):
        raise FlowError(f'Use normalized relative paths: {relative!r}')
    target = root
    for part in parts:
        target /= part
        if target.is_symlink():
            raise FlowError(f'Symlink path rejected: {relative}')
    if not target.resolve().is_relative_to(root):
        raise FlowError('Path escapes root.')
    if exists and not target.exists():
        raise FlowError(f'Missing path: {relative}')
    return target


def obj(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise FlowError(f'Expected JSON object: {path}')
    return value


def write_json(path: Path, value: dict[str, Any], *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    if exclusive:
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(data)
        return
    fd, temp = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def scan(root: Path, *, snapshot: bool = False) -> dict[str, str]:
    """Hash the whole authoritative tree, excluding only documented runtime paths."""
    if not root.is_dir() or root.is_symlink():
        raise FlowError(f'Not a regular directory: {root}')
    result: dict[str, str] = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in list(dirs):
            path = Path(directory) / name
            if name in EXCLUDED_DIRS and not snapshot:
                dirs.remove(name)
                continue
            if path.is_symlink():
                raise FlowError(f'Symlink rejected: {path}')
        for name in files:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            local(root, relative)
            if not path.is_file():
                raise FlowError(f'Not a regular file: {relative}')
            if name == '.DS_Store' or name.endswith(('.pyc', '.pyo')):
                if not snapshot:
                    continue
            if (name == '.env' or name.startswith('.env.')) and name not in {'.env.example', '.env.template'}:
                raise FlowError(f'Remove secret-bearing environment file from specification tree: {relative}')
            if name.endswith(('.pem', '.key', '.p12', '.pfx')) or name in {'id_rsa', 'id_ed25519'}:
                raise FlowError(f'Possible credential file rejected: {relative}')
            result[relative] = sha(path)
    return dict(sorted(result.items()))


def differences(left: dict[str, str], right: dict[str, str]) -> dict[str, list[str]]:
    return {'added': sorted(right.keys() - left.keys()), 'deleted': sorted(left.keys() - right.keys()),
            'modified': sorted(p for p in left.keys() & right.keys() if left[p] != right[p])}


def changed(diff: dict[str, list[str]]) -> bool:
    return any(diff.values())


class Store:
    final_stage = 'INTEGRATION_VERIFY'
    verification_schema = SCHEMA

    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise FlowError('Project root must already be a directory.')

    def p(self, relative: str, *, exists: bool = True) -> Path:
        return local(self.root, relative, exists=exists)

    def registry(self) -> dict[str, Any]:
        value = obj(self.p('.project-flow/project.json'))
        if value.get('schema_version') != SCHEMA or not isinstance(value.get('versions'), dict):
            raise FlowError('Unsupported project registry: schema_version=4 is required. No conversion is provided.')
        return value

    def entry(self, version: str) -> dict[str, Any]:
        version_label(version)
        record = self.registry()['versions'].get(version)
        if not isinstance(record, dict):
            raise FlowError(f'Unknown version: {version}')
        return record

    def state_path(self, version: str) -> str:
        return f'.project-flow/versions/{version_label(version)}/state.json'

    def state(self, version: str) -> dict[str, Any]:
        self.entry(version)
        value = obj(self.p(self.state_path(version)))
        if (value.get('schema_version') != SCHEMA or value.get('workflow_version') != SCHEMA
                or value.get('version') != version or value.get('stage') not in STAGES):
            raise FlowError('Unsupported or malformed version state: schema_version=4 and workflow_version=4 are required.')
        return value

    def save_state(self, state: dict[str, Any]) -> None:
        write_json(self.p(self.state_path(state['version']), exists=False), state)

    def draft(self, version: str) -> Path:
        version_label(version)
        return self.p(f'docs/releases/{version}/draft')

    def init(self, version: str, name: str) -> dict[str, Any]:
        version_label(version)
        if self.p('.project-flow/project.json', exists=False).exists():
            raise FlowError('Registry already exists; use new.')
        for relative in ('.project-flow', 'docs/releases'):
            directory = self.p(relative, exists=False)
            if directory.exists():
                if not directory.is_dir() or any(
                    child.name != '.version-flow.lock' for child in directory.iterdir()
                ):
                    raise FlowError('Managed data already exists; current-format initialization requires empty managed directories. Nothing was converted or overwritten.')
        # Refuse existing managed content, including interrupted initialization.
        for relative in (f'docs/releases/{version}', f'.project-flow/versions/{version}'):
            if self.p(relative, exists=False).exists():
                raise FlowError(f'Target exists; inspect/recover it rather than overwriting: {relative}')
        registry = {'schema_version': SCHEMA, 'skill_version': SKILL_VERSION,
                    'project_name': nonblank(name, 'name'), 'active_version': version,
                    'current_delivered': None, 'versions': {}, 'promotion_history': []}
        write_json(self.p('.project-flow/project.json', exists=False), registry, exclusive=True)
        return self.new(version, None)

    def new(self, version: str, base_ref: str | None, *, allow_unreleased: bool = False) -> dict[str, Any]:
        version_label(version)
        registry = self.registry()
        if any(v.casefold() == version.casefold() for v in registry['versions']):
            raise FlowError('Version already exists (case-insensitive); never overwrite it.')
        if registry['versions'] and base_ref is None:
            raise FlowError('An existing project needs an explicit parent baseline.')
        base = None
        source = None
        if base_ref:
            verified = self.check(base_ref)
            base_version, _ = ref_parts(base_ref)
            delivery = self.entry(base_version).get('delivery')
            is_delivered = bool(delivery and delivery.get('baseline_ref') == base_ref)
            if is_delivered:
                self.check_delivery(base_version)
            if not is_delivered and not allow_unreleased:
                raise FlowError('Parent must be delivered; --allow-unreleased permits planning only, not building.')
            base = {'ref': base_ref, 'manifest_sha256': verified['manifest_sha256'],
                    'delivered_at_creation': is_delivered}
            source = self.snapshot(base_ref)
        release_root = self.p(f'docs/releases/{version}', exists=False)
        runtime_root = self.p(f'.project-flow/versions/{version}', exists=False)
        if release_root.exists() or runtime_root.exists():
            raise FlowError('Destination exists, possibly from an interrupted operation; inspect it first.')
        release_root.mkdir(parents=True)
        target = release_root / 'draft'
        target.mkdir()
        if source:
            self.copy_tree(source, target, scan(source, snapshot=True))
            scope = obj(target / 'scope.json')
            scope.update({'product_version': version, 'base_ref': base_ref, 'change_summary': '',
                          'readiness_reviewed': False, 'incorporated_refs': []})
            write_json(target / 'scope.json', scope)
            trace = obj(target / 'traceability.json')
            for req in trace.get('requirements', []):
                req['change'] = 'unchanged'
            write_json(target / 'traceability.json', trace)
            changes_path = local(target, scope['documents']['changes'].split('#')[0], exists=False)
            # Do not erase other content if a small project combines semantic units.
            if [value.split('#')[0] for value in scope['documents'].values()].count(scope['documents']['changes'].split('#')[0]) == 1:
                changes_path.write_text(f'# 本期变更\n\n目标：{version}；来源：{base_ref}。\n\n尚未确定本期变更；先做影响分析。\n', encoding='utf-8')
        else:
            scope = {'schema_version': SCHEMA, 'product_version': version, 'base_ref': None,
                     'change_summary': '', 'readiness_reviewed': False, 'incorporated_refs': [],
                     'documents': DOCUMENTS.copy()}
            write_json(target / 'scope.json', scope)
            write_json(target / 'traceability.json', {'schema_version': SCHEMA, 'requirements': [], 'acceptance': []})
            write_json(target / 'quality-gates.json', {'schema_version': SCHEMA, 'gates': []})
            (target / 'spec').mkdir()
            (target / DOCUMENTS['index']).write_text('# 实施规范入口\n\n版本身份见 ../scope.json。当前为未批准草稿。\n', encoding='utf-8')
        runtime_root.mkdir(parents=True)
        (runtime_root / 'evidence').mkdir()
        state = {'schema_version': SCHEMA, 'workflow_version': SCHEMA, 'version': version, 'stage': 'SCOPE' if base else 'DISCOVER',
                 'resume_stage': None, 'prototype_revision': 0, 'candidate': None,
                 'approved': None, 'active_baseline': None, 'code_start_ref': None,
                 'approvals': [], 'open_questions': [], 'blockers': [], 'history': [],
                 'next_action': '核对来源代码与文档，讨论本期差异。' if base else '明确目标并做首条可运行原型。'}
        write_json(runtime_root / 'state.json', state)
        write_json(runtime_root / 'tasks.json', {'schema_version': SCHEMA, 'version': version, 'tasks': []})
        (runtime_root / 'decisions.md').write_text(f'# {version} 的讨论决定\n', encoding='utf-8')
        (runtime_root / 'handoff.md').write_text(f'# {version} 续接入口\n\n{state["next_action"]}\n', encoding='utf-8')
        registry['versions'][version] = {'base': base, 'baselines': {}, 'delivery': None, 'created_at': now()}
        registry['active_version'] = version
        write_json(self.p('.project-flow/project.json'), registry)
        return {'ok': True, 'version': version, 'base': base, 'stage': state['stage'],
                'approvals_inherited': False, 'code_checkout_performed': False}

    @staticmethod
    def copy_tree(source: Path, destination: Path, hashes: dict[str, str]) -> None:
        for relative, expected in hashes.items():
            src = local(source, relative)
            dest = local(destination, relative, exists=False)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            if sha(dest) != expected:
                raise FlowError(f'Source changed while copying: {relative}')

    def snapshot(self, ref: str) -> Path:
        version, baseline = ref_parts(ref)
        return self.p(f'docs/releases/{version}/baselines/{baseline}/snapshot')

    def validate_spec(self, version: str) -> dict[str, Any]:
        tree = self.draft(version)
        scope = obj(local(tree, 'scope.json'))
        entry = self.entry(version)
        base_ref = entry['base']['ref'] if entry['base'] else None
        if scope.get('schema_version') != SCHEMA or scope.get('product_version') != version or scope.get('base_ref') != base_ref:
            raise FlowError('scope.json version or parent does not match the registry.')
        if scope.get('readiness_reviewed') is not True:
            raise FlowError('Readiness review has not been recorded. A flag alone does not prove semantic completeness.')
        nonblank(scope.get('change_summary'), 'change_summary')
        incorporated = scope.get('incorporated_refs')
        if not isinstance(incorporated, list) or any(not isinstance(r, str) for r in incorporated) or len(set(incorporated)) != len(incorporated):
            raise FlowError('incorporated_refs must be a unique reference array.')
        for merged_ref in incorporated:
            merged_version, _ = ref_parts(merged_ref)
            self.check(merged_ref)
            delivered = self.check_delivery(merged_version)
            if delivered['baseline_ref'] != merged_ref:
                raise FlowError('incorporated_refs must pin an actually delivered baseline.')
        docs = scope.get('documents', {})
        if not isinstance(docs, dict) or not DOCUMENTS.keys() <= docs.keys():
            raise FlowError('Document mapping must cover every required semantic unit.')
        for ref in docs.values():
            p = local(tree, nonblank(ref, 'document reference').split('#')[0])
            if not p.is_file() or not p.read_text(encoding='utf-8').strip():
                raise FlowError('Document mapping points to an empty/non-text document.')
        trace = obj(local(tree, 'traceability.json'))
        if trace.get('schema_version') != SCHEMA:
            raise FlowError('Unsupported traceability schema.')
        reqs = self.id_map(trace.get('requirements'), 'requirements')
        cases = self.id_map(trace.get('acceptance'), 'acceptance')
        if not reqs or not cases:
            raise FlowError('Requirements and acceptance cases cannot be empty at baseline time.')
        for req in reqs.values():
            if req.get('status') not in {'active', 'deprecated', 'removed'}:
                raise FlowError('Unknown requirement status.')
            if req.get('change') not in {'added', 'modified', 'unchanged', 'deprecated', 'removed'}:
                raise FlowError('Unknown requirement change classification.')
            nonblank(req.get('title'), 'requirement title')
            version_label(req.get('since'))
            self.validate_refs(tree, req.get('spec_refs'))
            if req['status'] == 'removed':
                nonblank(req.get('reason'), 'removed requirement reason')
            else:
                ids = req.get('acceptance_ids')
                if not isinstance(ids, list) or not ids or any(i not in cases for i in ids):
                    raise FlowError('Active requirement has missing acceptance links.')
                for cid in ids:
                    if cases[cid].get('status') != 'active' or req['id'] not in cases[cid].get('requirement_ids', []):
                        raise FlowError('Acceptance links must be active and bidirectional.')
        for case in cases.values():
            if case.get('status') not in {'active', 'retired'}:
                raise FlowError('Unknown acceptance status.')
            ids = case.get('requirement_ids')
            if not isinstance(ids, list) or not ids or any(i not in reqs for i in ids):
                raise FlowError('Acceptance has unknown requirement references.')
            self.validate_refs(tree, case.get('spec_refs'))
            if case['status'] == 'retired':
                nonblank(case.get('reason'), 'retired acceptance reason')
            if not isinstance(case.get('required'), bool):
                raise FlowError('Acceptance required must be boolean.')
            if case['status'] == 'active' and not case['required']:
                nonblank(case.get('waiver_reason'), 'optional acceptance waiver_reason')
        prior_refs = [base_ref] if base_ref else []
        if entry['baselines']:
            latest = max(entry['baselines'], key=lambda b: int(b[1:]))
            prior_refs.append(f'{version}/{latest}')
        for prior_ref in prior_refs:
            self.check(prior_ref)
            prior = obj(self.snapshot(prior_ref) / 'traceability.json')
            old_reqs = self.id_map(prior['requirements'], 'prior requirements')
            old_cases = self.id_map(prior['acceptance'], 'prior acceptance')
            if old_reqs.keys() - reqs.keys() or old_cases.keys() - cases.keys():
                raise FlowError('Historical IDs disappeared; retain removed/retired tombstones instead.')
            for rid, old in old_reqs.items():
                if old['since'] != reqs[rid]['since']:
                    raise FlowError(f'Cannot reset introduction version of {rid}.')
        gate_file = obj(local(tree, 'quality-gates.json'))
        gates = self.id_map(gate_file.get('gates'), 'gates')
        if gate_file.get('schema_version') != SCHEMA or not gates or not any(g.get('required') is True for g in gates.values()):
            raise FlowError('At least one required quality gate is needed.')
        if gates.keys() & cases.keys():
            raise FlowError('Gate IDs must not collide with acceptance IDs.')
        for gate in gates.values():
            nonblank(gate.get('description'), 'gate description')
            if not isinstance(gate.get('required'), bool):
                raise FlowError('Gate required must be boolean.')
            if not gate['required']:
                nonblank(gate.get('waiver_reason'), 'optional gate waiver_reason')
        required = {cid for cid, c in cases.items() if c['status'] == 'active' and c['required']}
        required.update(gid for gid, g in gates.items() if g['required'])
        return {'scope': scope, 'traceability': trace, 'required_checks': sorted(required)}

    @staticmethod
    def id_map(items: Any, label: str) -> dict[str, dict[str, Any]]:
        if not isinstance(items, list):
            raise FlowError(f'{label} must be an array.')
        result = {}
        for item in items:
            if not isinstance(item, dict):
                raise FlowError(f'{label} entries must be objects.')
            key = nonblank(item.get('id'), f'{label} id')
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9._-]{0,100}', key) or key in result:
                raise FlowError(f'Duplicate or invalid ID in {label}: {key}')
            result[key] = item
        return result

    @staticmethod
    def validate_refs(tree: Path, refs: Any) -> None:
        if not isinstance(refs, list) or not refs:
            raise FlowError('spec_refs must be a nonempty array.')
        for ref in refs:
            path = local(tree, nonblank(ref, 'spec_ref').split('#')[0])
            if not path.is_file():
                raise FlowError('spec_ref does not point to a file.')

    @staticmethod
    def no_blockers(state: dict[str, Any]) -> None:
        if state.get('blockers') or any(q.get('blocking', True) for q in state.get('open_questions', [])):
            raise FlowError('Resolve blocking questions and blockers before proceeding.')

    def seal(self, version: str) -> dict[str, Any]:
        state = self.state(version)
        if state['stage'] not in {'DISCOVER', 'SCOPE', 'ITERATE', 'SPECIFY'}:
            raise FlowError('Use revise before changing a frozen/authorized baseline; delivered versions are immutable.')
        self.no_blockers(state)
        reviewed = self.validate_spec(version)
        registry = self.registry()
        entry = registry['versions'][version]
        number = max([int(b[1:]) for b in entry['baselines']] + [0]) + 1
        baseline = f'b{number:03d}'
        ref = f'{version}/{baseline}'
        final = self.p(f'docs/releases/{version}/baselines/{baseline}', exists=False)
        if final.exists():
            raise FlowError('Baseline destination already exists; inspect interrupted operation, never overwrite.')
        final.parent.mkdir(parents=True, exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix='.seal-', dir=final.parent))
        try:
            hashes = scan(self.draft(version))
            snap = temp / 'snapshot'
            snap.mkdir()
            self.copy_tree(self.draft(version), snap, hashes)
            if changed(differences(hashes, scan(self.draft(version)))):
                raise FlowError('Draft changed during sealing; retry after writers stop.')
            manifest = {'schema_version': SCHEMA, 'kind': 'specification', 'version': version,
                        'baseline': baseline, 'base': entry['base'], 'created_at': now(), 'files': hashes,
                        'required_checks': reviewed['required_checks'], 'exclusions': sorted(EXCLUDED_DIRS)}
            write_json(temp / 'manifest.json', manifest, exclusive=True)
            temp.rename(final)
        finally:
            if temp.exists():
                shutil.rmtree(temp)
        manifest_path = final / 'manifest.json'
        relative = manifest_path.relative_to(self.root).as_posix()
        entry['baselines'][baseline] = {'manifest': relative, 'sha256': sha(manifest_path)}
        state.update({'candidate': baseline, 'approved': None, 'active_baseline': None, 'stage': 'SPECIFY'})
        state['history'].append({'event': 'sealed', 'ref': ref, 'at': now()})
        write_json(self.p('.project-flow/project.json'), registry)
        self.save_state(state)
        return {'ok': True, 'ref': ref, 'manifest_sha256': sha(manifest_path), 'files': len(hashes), 'approval_created': False}

    def check(self, ref: str, *, against_draft: bool = False) -> dict[str, Any]:
        version, baseline = ref_parts(ref)
        entry = self.entry(version)
        record = entry.get('baselines', {}).get(baseline)
        expected_path = f'docs/releases/{version}/baselines/{baseline}/manifest.json'
        if not isinstance(record, dict) or record.get('manifest') != expected_path:
            raise FlowError('Unknown baseline or noncanonical manifest path.')
        path = self.p(record['manifest'])
        digest = sha(path)
        if digest != record.get('sha256'):
            raise FlowError('Manifest hash no longer matches registry.')
        manifest = obj(path)
        if manifest.get('schema_version') != SCHEMA or manifest.get('kind') != 'specification' or manifest.get('version') != version or manifest.get('baseline') != baseline or manifest.get('base') != entry['base']:
            raise FlowError('Baseline identity or ancestry mismatch.')
        files = manifest.get('files')
        if not isinstance(files, dict) or not files:
            raise FlowError('Empty/malformed baseline.')
        for file, digest_value in files.items():
            local(self.snapshot(ref), file)
            if not isinstance(digest_value, str) or not re.fullmatch('[0-9a-f]{64}', digest_value):
                raise FlowError('Malformed SHA-256.')
        delta = differences(files, scan(self.snapshot(ref), snapshot=True))
        if changed(delta):
            raise FlowError('Snapshot drift: ' + json.dumps(delta, ensure_ascii=False))
        if against_draft:
            delta = differences(files, scan(self.draft(version)))
            if changed(delta):
                raise FlowError('Draft differs from baseline: ' + json.dumps(delta, ensure_ascii=False))
        return {'ok': True, 'ref': ref, 'manifest_sha256': digest,
                'checked_files': len(files), 'build_records_checked': False}

    def parent_delivered(self, entry: dict[str, Any]) -> None:
        if not entry.get('base'):
            return
        ref = entry['base']['ref']
        parent_version, _ = ref_parts(ref)
        verified = self.check(ref)
        if verified['manifest_sha256'] != entry['base']['manifest_sha256']:
            raise FlowError('Pinned parent hash mismatch.')
        delivery = self.entry(parent_version).get('delivery')
        if not delivery or delivery.get('baseline_ref') != ref:
            raise FlowError('Unreleased parent: planning is allowed but building is blocked until exact parent delivery.')
        self.check_delivery(parent_version)

    @staticmethod
    def has_approval(state: dict[str, Any], kind: str, ref: str, digest: str) -> bool:
        return any(isinstance(a, dict) and a.get('kind') == kind and a.get('ref') == ref
                   and a.get('manifest_sha256') == digest and isinstance(a.get('user_quote'), str)
                   and a['user_quote'].strip() and isinstance(a.get('context_reference'), str)
                   and a['context_reference'].strip() for a in state.get('approvals', []))


    def revise(self, version: str, reason: str) -> dict[str, Any]:
        nonblank(reason, 'revision reason')
        state = self.state(version)
        if state['stage'] in {'DELIVERED', 'CANCELLED'} or self.entry(version).get('delivery'):
            raise FlowError('Delivered/cancelled version cannot be revised; create another product version.')
        state['history'].append({'event': 'revised', 'previous_baseline': state['candidate'], 'reason': reason, 'at': now()})
        state.update({'stage': 'ITERATE', 'resume_stage': None, 'approved': None, 'active_baseline': None,
                      'candidate': None, 'code_start_ref': None})
        self.save_state(state)
        path = self.p(f'.project-flow/versions/{version}/tasks.json')
        tasks = obj(path)
        for task in tasks.get('tasks', []):
            task['previous_status'] = task.get('status')
            task['status'] = 'needs_revalidation'
        write_json(path, tasks)
        return {'ok': True, 'version': version, 'stage': 'ITERATE', 'old_snapshots_preserved': True,
                'old_approvals_preserved_but_not_transferred': True}


    def switch(self, version: str) -> dict[str, Any]:
        self.state(version)
        registry = self.registry()
        old = registry['active_version']
        registry['active_version'] = version
        write_json(self.p('.project-flow/project.json'), registry)
        return {'ok': True, 'previous': old, 'active_version': version, 'code_checkout_performed': False,
                'warning': 'Verify branch/worktree, code start ref and uncommitted changes before writing code.'}

    def deliver(self, version: str, report_name: str) -> dict[str, Any]:
        state = self.state(version)
        if state['stage'] != self.final_stage:
            raise FlowError('Delivery requires INTEGRATION_VERIFY, not merely generated code.')
        ref = f'{version}/{state["active_baseline"]}'
        checked = self.check(ref, for_build=True)
        report_path = self.p(report_name)
        report = obj(report_path)
        if report.get('schema_version') != self.verification_schema or report.get('version') != version or report.get('baseline_ref') != ref or report.get('manifest_sha256') != checked['manifest_sha256']:
            raise FlowError('Verification report must bind this exact version, baseline and hash.')
        code_ref = nonblank(report.get('code_ref'), 'verified code_ref')
        if report.get('open_blockers') != []:
            raise FlowError('Verification report must explicitly have no open blockers.')
        checks = self.id_map(report.get('checks'), 'verification checks')
        manifest = obj(self.p(self.entry(version)['baselines'][state['active_baseline']]['manifest']))
        required = set(manifest['required_checks'])
        if not required <= checks.keys():
            raise FlowError('Missing required acceptance/regression/quality-gate results: ' + ', '.join(sorted(required - checks.keys())))
        evidence: dict[str, str] = {}
        prefix = f'.project-flow/versions/{version}/evidence/'
        for cid, check in checks.items():
            if check.get('code_ref') != code_ref:
                raise FlowError(f'Stale or wrong code_ref on verification check: {cid}')
            if cid in required and check.get('status') != 'passed':
                raise FlowError(f'Required check did not pass: {cid}')
            if check.get('status') not in {'passed', 'skipped'}:
                raise FlowError(f'Failed/unresolved check cannot be delivered: {cid}')
            if check.get('status') == 'skipped':
                nonblank(check.get('reason'), 'skipped check reason')
                continue
            paths = check.get('evidence')
            if not isinstance(paths, list) or not paths:
                raise FlowError(f'Passed result has no evidence: {cid}')
            for path in paths:
                if not isinstance(path, str) or not path.startswith(prefix):
                    raise FlowError('Evidence must belong to this version evidence directory.')
                f = self.p(path)
                if not f.is_file() or not f.stat().st_size:
                    raise FlowError('Evidence file is missing, empty or not regular.')
                evidence[path] = sha(f)
        tasks = obj(self.p(f'.project-flow/versions/{version}/tasks.json'))
        if tasks.get('schema_version') != SCHEMA or tasks.get('version') != version:
            raise FlowError('Every current-version task file must identify its schema and version.')
        task_map = self.id_map(tasks.get('tasks'), 'tasks')
        if not task_map or any(t.get('status') != 'done' or t.get('baseline_ref') != ref for t in task_map.values()):
            raise FlowError('Every current-version task must be done and bound to this baseline; do not inherit completion.')
        final = self.p(f'docs/releases/{version}/delivery', exists=False)
        if final.exists() or self.entry(version).get('delivery'):
            raise FlowError('Delivery already exists; never overwrite it.')
        temp = Path(tempfile.mkdtemp(prefix='.delivery-', dir=final.parent))
        try:
            # Rewrite report evidence references into the durable archive, not mutable run logs.
            archived_report = json.loads(json.dumps(report))
            for check in archived_report['checks']:
                check['evidence'] = ['evidence/' + p[len(prefix):] for p in check.get('evidence', [])]
            for relative, expected in evidence.items():
                dst = local(temp, 'evidence/' + relative[len(prefix):], exists=False)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self.p(relative), dst)
                if sha(dst) != expected:
                    raise FlowError('Evidence changed during archival.')
            write_json(temp / 'verification.json', archived_report, exclusive=True)
            write_json(temp / 'tasks.json', tasks, exclusive=True)
            payload = scan(temp, snapshot=True)
            delivery = {'schema_version': SCHEMA, 'kind': 'delivery', 'version': version,
                        'baseline_ref': ref, 'manifest_sha256': checked['manifest_sha256'], 'code_ref': code_ref,
                        'created_at': now(), 'files': payload, 'production_deployed': False}
            write_json(temp / 'manifest.json', delivery, exclusive=True)
            temp.rename(final)
        finally:
            if temp.exists():
                shutil.rmtree(temp)
        registry = self.registry()
        registry['versions'][version]['delivery'] = {'baseline_ref': ref,
            'manifest': (final / 'manifest.json').relative_to(self.root).as_posix(),
            'sha256': sha(final / 'manifest.json'), 'code_ref': code_ref}
        state.update({'stage': 'DELIVERED', 'next_action': '交付记录已归档；生产部署需独立授权。'})
        self.save_state(state)
        write_json(self.p('.project-flow/project.json'), registry)
        return {'ok': True, 'version': version, 'baseline_ref': ref, 'code_ref': code_ref,
                'current_pointer_changed': False, 'production_deployed': False,
                'tests_executed_by_this_command': False}

    def check_delivery(self, version: str) -> dict[str, Any]:
        delivery = self.entry(version).get('delivery')
        if not isinstance(delivery, dict):
            raise FlowError('Version has no delivery record.')
        expected = f'docs/releases/{version}/delivery/manifest.json'
        if delivery.get('manifest') != expected:
            raise FlowError('Noncanonical delivery path.')
        path = self.p(expected)
        if sha(path) != delivery.get('sha256'):
            raise FlowError('Delivery manifest drift.')
        record = obj(path)
        baseline = self.check(delivery['baseline_ref'])
        if record.get('schema_version') != SCHEMA or record.get('kind') != 'delivery' or record.get('version') != version or record.get('baseline_ref') != delivery['baseline_ref'] or record.get('manifest_sha256') != baseline['manifest_sha256'] or record.get('code_ref') != delivery.get('code_ref'):
            raise FlowError('Delivery identity mismatch.')
        hashes = scan(path.parent, snapshot=True)
        hashes.pop('manifest.json')
        delta = differences(record['files'], hashes)
        if changed(delta):
            raise FlowError('Delivery evidence drift: ' + json.dumps(delta, ensure_ascii=False))
        return {'ok': True, 'version': version, 'baseline_ref': delivery['baseline_ref'], 'code_ref': record['code_ref']}

    def promote(self, version: str, expected_current: str, quote: str, context: str, *, allow_divergence: bool = False, reason: str = '') -> dict[str, Any]:
        nonblank(quote, 'actual user quote')
        nonblank(context, 'message context')
        delivery = self.check_delivery(version)
        registry = self.registry()
        current = registry['current_delivered']
        if (current or 'none') != expected_current:
            raise FlowError('Current delivery pointer changed or was not explicitly identified.')
        if current and not self.lineage_contains(delivery['baseline_ref'], current):
            if not allow_divergence:
                raise FlowError('Divergent/current newer line: record forward-port reconciliation, or explicitly authorize pointer divergence.')
            nonblank(reason, 'divergence reason')
        registry['current_delivered'] = delivery['baseline_ref']
        registry['promotion_history'].append({'from': current, 'to': delivery['baseline_ref'],
            'user_quote': quote, 'context_reference': context, 'reason': reason, 'at': now()})
        write_json(self.p('.project-flow/project.json'), registry)
        return {'ok': True, 'current_delivered': delivery['baseline_ref'], 'production_deployed': False}

    def lineage_contains(self, ref: str, ancestor: str) -> bool:
        pending, visited = [ref], set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            self.check(current)
            if current == ancestor:
                return True
            version, _ = ref_parts(current)
            entry = self.entry(version)
            if entry['base']:
                pending.append(entry['base']['ref'])
            scope = obj(self.snapshot(current) / 'scope.json')
            pending.extend(scope.get('incorporated_refs', []))
        return False

    def tree_ref(self, ref: str) -> tuple[Path, dict[str, str]]:
        version, baseline = ref_parts(ref, draft=True)
        self.entry(version)
        if baseline == 'draft':
            return self.draft(version), scan(self.draft(version))
        self.check(ref)
        tree = self.snapshot(ref)
        return tree, scan(tree, snapshot=True)

    def diff(self, left: str, right: str) -> dict[str, Any]:
        ltree, lhashes = self.tree_ref(left)
        rtree, rhashes = self.tree_ref(right)
        lreq = self.id_map(obj(ltree / 'traceability.json')['requirements'], 'left requirements')
        rreq = self.id_map(obj(rtree / 'traceability.json')['requirements'], 'right requirements')
        keys = set(lreq) | set(rreq)
        changes = []
        metadata_only = []
        for rid in sorted(keys):
            before, after = lreq.get(rid), rreq.get(rid)
            if before == after:
                continue
            item = {'id': rid, 'before': before, 'after': after}
            stripped_before = {k: v for k, v in before.items() if k != 'change'} if before else None
            stripped_after = {k: v for k, v in after.items() if k != 'change'} if after else None
            (metadata_only if stripped_before == stripped_after else changes).append(item)
        return {'ok': True, 'left': left, 'right': right, 'files': differences(lhashes, rhashes),
                'requirements': changes, 'classification_only': metadata_only, 'semantic_api_compatibility_checked': False}

    def history(self, identifier: str) -> dict[str, Any]:
        nonblank(identifier, 'identifier')
        records = []
        for version, entry in self.registry()['versions'].items():
            for baseline in sorted(entry['baselines'], key=lambda b: int(b[1:])):
                ref = f'{version}/{baseline}'
                self.check(ref)
                trace = obj(self.snapshot(ref) / 'traceability.json')
                for group in ('requirements', 'acceptance'):
                    for item in trace[group]:
                        if item['id'] == identifier:
                            records.append({'ref': ref, 'base': entry['base'], 'kind': group,
                                            'definition': item, 'source': f'docs/releases/{version}/baselines/{baseline}/snapshot/traceability.json'})
        return {'ok': True, 'id': identifier, 'records': records}

    def status(self) -> dict[str, Any]:
        registry = self.registry()
        return {'ok': True, 'active_version': registry['active_version'], 'current_delivered': registry['current_delivered'],
                'versions': [{'version': v, 'stage': self.state(v)['stage'], 'base': e['base'],
                              'candidate': self.state(v)['candidate'], 'baselines': sorted(e['baselines']),
                              'delivery': e['delivery']} for v, e in registry['versions'].items()]}

    def doctor(self) -> dict[str, Any]:
        problems = []
        registry = self.registry()
        if registry.get('active_version') not in registry['versions']:
            problems.append('Active version points to an unknown version.')
        if registry.get('current_delivered'):
            try:
                current_version, _ = ref_parts(registry['current_delivered'])
                if self.check_delivery(current_version)['baseline_ref'] != registry['current_delivered']:
                    problems.append('Current delivery pointer does not match delivery archive.')
            except (FlowError, OSError, ValueError) as error:
                problems.append(f'Current delivery pointer: {error}')
        for version, entry in registry['versions'].items():
            try:
                self.state(version)
                if not self.draft(version).is_dir():
                    raise FlowError('Draft missing.')
                for baseline in entry['baselines']:
                    self.check(f'{version}/{baseline}')
                if entry['delivery']:
                    self.check_delivery(version)
                    if self.state(version)['stage'] != 'DELIVERED':
                        problems.append(f'{version}: delivery/state mismatch')
                elif self.p(f'docs/releases/{version}/delivery', exists=False).exists():
                    problems.append(f'{version}: unregistered delivery directory')
                base_dir = self.p(f'docs/releases/{version}/baselines', exists=False)
                if base_dir.exists():
                    for p in base_dir.iterdir():
                        if p.name not in entry['baselines']:
                            problems.append(f'{version}: unregistered baseline/temp {p.name}')
            except (FlowError, OSError, ValueError) as error:
                problems.append(f'{version}: {error}')
        releases = self.p('docs/releases', exists=False)
        if releases.exists():
            for p in releases.iterdir():
                if p.is_dir() and p.name not in registry['versions']:
                    problems.append(f'Unregistered version directory: {p.name}')
        return {'ok': not problems, 'problems': problems, 'repairs_performed': False}

    def index(self) -> dict[str, Any]:
        registry = self.registry()
        marker = '<!-- prototype-to-product:generated-index:v2 -->'
        path = self.p('docs/releases/INDEX.md', exists=False)
        if path.exists() and not path.read_text(encoding='utf-8').startswith(marker):
            raise FlowError('INDEX.md is not a generated index; do not overwrite user content.')
        lines = [marker, '# 系统版本与文档索引', '',
                 '由 project.json 与各版本 state.json 生成；不要手写产品规范到这个索引。', '',
                 f'当前讨论版本：`{registry["active_version"]}`。',
                 f'当前交付文档指针：`{registry["current_delivered"] or "尚未指定"}`。该指针不代表线上部署。', '',
                 '| 产品版本 | 阶段 | 来源基线 | 草稿入口 | 冻结基线 | 交付归档 |',
                 '| --- | --- | --- | --- | --- | --- |']
        for version, entry in registry['versions'].items():
            state = self.state(version)
            base = entry['base']['ref'] if entry['base'] else '首次创建'
            baselines = ', '.join(f'[{b}]({version}/baselines/{b}/snapshot/scope.json)' for b in sorted(entry['baselines'], key=lambda x: int(x[1:]))) or '无'
            delivery = f'[已归档]({version}/delivery/manifest.json)' if entry['delivery'] else '未交付'
            lines.append(f'| {version} | {state["stage"]} | {base} | [草稿]({version}/draft/scope.json) | {baselines} | {delivery} |')
        lines += ['', '完整阅读路径由各 scope.json 的 documents.index 指定；具体基线优先于“最新文件”。', '']
        path.parent.mkdir(parents=True, exist_ok=True)
        # Regenerable navigation only; not part of a frozen specification.
        fd, temp = tempfile.mkstemp(prefix='.index-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                stream.write('\n'.join(lines))
            os.replace(temp, path)
        finally:
            if os.path.exists(temp): os.unlink(temp)
        return {'ok': True, 'index': 'docs/releases/INDEX.md', 'authoritative': False}

    def export(self, ref: str, output: str) -> dict[str, Any]:
        checked = self.check(ref)
        version, baseline = ref_parts(ref)
        path = self.p(output, exists=False)
        if not output.endswith('.zip') or path.exists():
            raise FlowError('Export needs a new .zip path; existing files are never overwritten.')
        if output.startswith(('docs/releases/', '.project-flow/')):
            raise FlowError('Export outside managed state and specification directories.')
        path.parent.mkdir(parents=True, exist_ok=True)
        prefix = f'{version}-{baseline}'
        source = self.snapshot(ref)
        created = False
        try:
            with ZipFile(path, 'x', ZIP_DEFLATED) as archive:
                created = True
                archive.write(source.parent / 'manifest.json', f'{prefix}/manifest.json')
                for name in scan(source, snapshot=True):
                    archive.write(local(source, name), f'{prefix}/snapshot/{name}')
            self.check(ref)
        except Exception:
            if created:
                path.unlink(missing_ok=True)
            raise
        return {'ok': True, 'ref': ref, 'output': output, 'sha256': sha(path),
                'manifest_sha256': checked['manifest_sha256'], 'production_source_included': False}



@contextmanager
def writer_lock(flow: Store) -> Iterator[None]:
    path = flow.p('.project-flow/.version-flow.lock', exists=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise FlowError('Another writer or stale lock exists. Inspect owner/process before removing the lock.') from error
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'pid': os.getpid(), 'created_at': now()}, stream)
        yield
    finally:
        path.unlink(missing_ok=True)


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(description=__doc__)
    commands = top.add_subparsers(dest='command', required=True)
    for cmd in ('init', 'new', 'status', 'switch', 'seal', 'check', 'approve', 'revise', 'stage',
                'diff', 'history', 'deliver', 'check-delivery', 'promote', 'doctor', 'index', 'export'):
        p = commands.add_parser(cmd)
        p.add_argument('--root', default='.')
        if cmd in {'init', 'new', 'switch', 'seal', 'revise', 'stage', 'deliver', 'check-delivery', 'promote'}:
            p.add_argument('--version', required=True)
        if cmd in {'init'}:
            p.add_argument('--name', default='Project')
        if cmd == 'new':
            p.add_argument('--from', dest='base_ref', required=True)
            p.add_argument('--allow-unreleased', action='store_true')
        if cmd in {'check', 'approve', 'export'}:
            p.add_argument('--ref', required=True)
        if cmd == 'check':
            p.add_argument('--against-draft', action='store_true')
            p.add_argument('--for-build', action='store_true')
        if cmd in {'approve', 'promote'}:
            p.add_argument('--quote', required=True)
            p.add_argument('--context', required=True)
        if cmd == 'approve':
            p.add_argument('--kind', choices=['baseline', 'backend', 'frontend'], required=True)
            p.add_argument('--code-ref')
        if cmd in {'revise', 'stage', 'promote'}:
            p.add_argument('--reason', default='')
        if cmd == 'stage':
            p.add_argument('--to', required=True)
        if cmd == 'diff':
            p.add_argument('--left', required=True)
            p.add_argument('--right', required=True)
        if cmd == 'history':
            p.add_argument('--id', required=True)
        if cmd == 'deliver':
            p.add_argument('--report', required=True)
        if cmd == 'promote':
            p.add_argument('--expected-current', required=True)
            p.add_argument('--allow-divergence', action='store_true')
        if cmd == 'export':
            p.add_argument('--output', required=True)
    return top


def dispatch(flow: Store, a: argparse.Namespace) -> dict[str, Any]:
    c = a.command
    if c == 'init': return flow.init(a.version, a.name)
    if c == 'new': return flow.new(a.version, a.base_ref, allow_unreleased=a.allow_unreleased)
    if c == 'status': return flow.status()
    if c == 'index': return flow.index()
    if c == 'export': return flow.export(a.ref, a.output)
    if c == 'switch': return flow.switch(a.version)
    if c == 'seal': return flow.seal(a.version)
    if c == 'check': return flow.check(a.ref, against_draft=a.against_draft, for_build=a.for_build)
    if c == 'approve': return flow.approve(a.ref, a.kind, a.quote, a.context, code_ref=a.code_ref)
    if c == 'revise': return flow.revise(a.version, a.reason)
    if c == 'stage': return flow.stage(a.version, a.to, a.reason)
    if c == 'diff': return flow.diff(a.left, a.right)
    if c == 'history': return flow.history(a.id)
    if c == 'deliver': return flow.deliver(a.version, a.report)
    if c == 'check-delivery': return flow.check_delivery(a.version)
    if c == 'promote': return flow.promote(a.version, a.expected_current, a.quote, a.context,
                                           allow_divergence=a.allow_divergence, reason=a.reason)
    if c == 'doctor': return flow.doctor()
    raise FlowError('Unknown command.')


