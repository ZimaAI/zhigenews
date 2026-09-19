import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const contracts = path.resolve(root, '../contracts');
const readJSON = p => JSON.parse(fs.readFileSync(p, 'utf8').replace(/^\uFEFF/, ''));
const spec = readJSON(path.join(contracts, 'openapi.json'));
const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
const schemaId = 'https://zhigenews.local/prototype-schemas';
ajv.addSchema({ $id: schemaId, components: spec.components });
const validators = new Map();
const failures = [];
let checked = 0;
function validate(name, value, label) {
  if (!validators.has(name)) validators.set(name, ajv.compile({ $ref: `${schemaId}#/components/schemas/${name}` }));
  const check = validators.get(name); checked++;
  if (!check(value)) failures.push({ label, errors: check.errors });
}
const examples = fs.readdirSync(path.join(contracts, 'examples')).filter(x => x.endsWith('.json'));
for (const filename of examples) {
  const example = readJSON(path.join(contracts, 'examples', filename));
  if (example.synthetic !== true) failures.push({ label: filename, error: 'Missing synthetic marker' });
  validate(example.schema, example.data, filename);
}
// Check the actual mock seed, rather than only separate contract examples.
const source = fs.readFileSync(path.join(root, 'shared/fixtures.ts'), 'utf8');
const output = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const { createSeed } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
const seed = createSeed();
// The approved prototype keeps its original display models. This explicit synthetic
// projection supplies the technical metadata required by the final HTTP contract;
// none of these fixture values are evidence of real collection or execution.
for (const brief of seed.briefs) {
  brief.missingSources = brief.generationStatus === 'partial' ? ['模拟失败来源'] : [];
  for (const item of brief.items) {
    item.fetchedAt = `${brief.date}T07:55:00+08:00`;
    item.snapshotId = `synthetic-snapshot-${item.id}`;
  }
}
for (const run of seed.runs) {
  run.events = run.events.map(event => ({ ...event, time: `${run.startedAt.slice(0, 10)}T${event.time}+08:00` }));
  if (run.id === 'run-003') run.inputTokens = run.outputTokens = run.cost = null;
}
for (const source of seed.sources) {
  const fetchedAt = source.lastSuccess || null;
  Object.assign(source, {
    snapshotId: fetchedAt ? `synthetic-snapshot-${source.id}` : null,
    snapshotFetchedAt: fetchedAt,
    lastFetchedAt: '2026-09-18T08:10:00+08:00',
    cacheAgeSeconds: fetchedAt ? Math.max(0, (Date.parse('2026-09-18T08:12:00+08:00') - Date.parse(fetchedAt)) / 1000) : null,
    stale: !fetchedAt || Date.parse('2026-09-18T08:12:00+08:00') - Date.parse(fetchedAt) > source.interval * 1000,
    upstreamRevision: source.kind === 'newsnow' ? 'synthetic-newsnow-revision' : null,
  });
}
for (const row of seed.evalCases) Object.assign(row, {
  preferenceSnapshot: { version: 0, role: row.preference, topics: [], keywords: [] },
  fixedAt: '2026-09-18T08:12:00+08:00',
  sourceSnapshotIds: seed.sources.filter(source => source.snapshotId).map(source => source.snapshotId),
  revision: 1,
});
for (const evaluation of seed.evaluations) Object.assign(evaluation, {
  datasetVersion: 'synthetic-dataset-v1', scorerVersion: 'synthetic-scorer-v1', modelId: 'model-01',
  results: seed.evalCases.map(row => ({ caseId: row.id, caseRevision: 1, status: 'completed', scores: [
    { metric: 'relevance', method: 'llm', value: evaluation.relevance, maximum: 5, passed: null, error: '' },
    { metric: 'faithfulness', method: 'llm', value: evaluation.faithfulness, maximum: 5, passed: null, error: '' },
    { metric: 'citationAccuracy', method: 'rule', value: evaluation.citations, maximum: 100, passed: true, error: '' },
  ] })),
});
validate('Preferences', seed.preferences, 'seed.preferences');
validate('DeliverySettings', seed.delivery, 'seed.delivery');
// Brief is still the prototype's internal aggregate; HTTP readers receive its public projection.
// Legacy seed.users is private demonstration data, no longer a public user DTO.
for (const [collection, name] of Object.entries({ briefs: 'AdminBrief', runs: 'AgentRun', sources: 'Source', models: 'ModelConfig', configs: 'AgentConfig', evaluations: 'Evaluation', evalCases: 'EvalCase', deliveries: 'Delivery' })) {
  for (const row of seed[collection]) validate(name, row, `seed.${collection}.${row.id}`);
}
for (const brief of seed.briefs) {
  const { runId, preferenceSnapshot, ...publicBrief } = brief;
  validate('Brief', publicBrief, `public.briefs.${brief.id}`);
  if (!seed.runs.some(run => run.id === brief.runId && run.userName === '林序')) failures.push({ label: brief.id, error: 'Brief references missing or another reader run' });
  if (brief.items.some(item => item.publishedAt && Date.parse(item.publishedAt) > Date.parse(brief.generatedAt))) failures.push({ label: brief.id, error: 'News date is after briefing generation' });
}
// Validate the changed public boundary, including values that must be rejected.
let rejectedCases = 0;
function reject(name, value, label) {
  const check = ajv.compile({ $ref: `${schemaId}#/components/schemas/${name}` });
  rejectedCases++;
  if (check(value)) failures.push({ label, error: 'Invalid/removed public data was accepted' });
}
const progress = readJSON(path.join(contracts, 'examples/generation-running.json')).data;
for (const [field, value] of [['percent', -1], ['percent', 101], ['remainingSeconds', -1], ['remainingSeconds', 1.5], ['updatedAt', '08:12'], ['events', []], ['model', 'private-model']]) {
  reject('GenerationProgress', { ...progress, [field]: value }, `progress rejects ${field}=${JSON.stringify(value)}`);
}
const session = readJSON(path.join(contracts, 'examples/session-anonymous.json')).data;
reject('Session', { ...session, kind: 'admin' }, 'anonymous session cannot become admin');
reject('Session', { ...session, token: 'secret' }, 'session must not expose token');
reject('NewsItem', { ...seed.briefs[0].items[0], read: false }, 'removed read state');
reject('Brief', seed.briefs[0], 'public brief excludes internal run and preference snapshot');
const policy = readJSON(path.join(contracts, 'examples/anonymous-policy.json')).data;
reject('AnonymousPolicy', { ...policy, maxConcurrentGenerations: 0 }, 'concurrency must be positive');
reject('AnonymousPolicy', { ...policy, accountsPerIpHour: 101 }, 'new-account policy bound');
for (const removed of ['/auth/register', '/me/news/{id}/read', '/me/runs', '/me/runs/{id}', '/me/runs/{id}/events']) {
  if (spec.paths[removed]) failures.push({ label: removed, error: 'Removed reader route remains exposed' });
}
if (spec.paths['/auth/session'].post) failures.push({ error: 'Reader password login remains exposed' });
const privateSchemas = new Set(['AgentRun', 'RunEvent', 'Subtask', 'AdminBrief', 'AnonymousAccount', 'AbuseEvent']);
function containsPrivateSchema(value, seen = new Set()) {
  if (!value || typeof value !== 'object') return false;
  if (value.$ref?.startsWith('#/components/schemas/')) {
    const name = value.$ref.split('/').at(-1);
    if (privateSchemas.has(name)) return true;
    if (seen.has(name)) return false;
    seen.add(name);
    return containsPrivateSchema(spec.components.schemas[name], seen);
  }
  return Object.values(value).some(child => containsPrivateSchema(child, seen));
}
for (const [route, methods] of Object.entries(spec.paths)) {
  for (const operation of Object.values(methods)) {
    if (route.startsWith('/me/') && containsPrivateSchema(operation.responses)) failures.push({ label: route, error: 'Private schema exposed to reader' });
    if (route.startsWith('/admin/') && route !== '/admin/auth/login' && !operation.security?.some(s => 'adminSessionCookie' in s)) failures.push({ label: route, error: 'Missing independent admin authentication' });
  }
}
const operationIds = Object.values(spec.paths).flatMap(p => Object.values(p).map(op => op?.operationId).filter(Boolean));
if (new Set(operationIds).size !== operationIds.length) failures.push({ error: 'Duplicate operationId' });
console.log(JSON.stringify({ examples: examples.length, schemas: Object.keys(spec.components.schemas).length, operations: operationIds.length, instancesChecked: checked, rejectedCases, failures }, null, 2));
process.exitCode = failures.length ? 1 : 0;
