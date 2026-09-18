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
validate('Preferences', seed.preferences, 'seed.preferences');
validate('DeliverySettings', seed.delivery, 'seed.delivery');
for (const [collection, name] of Object.entries({ briefs: 'Brief', runs: 'AgentRun', sources: 'Source', models: 'ModelConfig', configs: 'AgentConfig', evaluations: 'Evaluation', evalCases: 'EvalCase', users: 'DemoUser', deliveries: 'Delivery', memories: 'Memory' })) {
  for (const row of seed[collection]) validate(name, row, `seed.${collection}.${row.id}`);
}
for (const brief of seed.briefs) {
  if (!seed.runs.some(run => run.id === brief.runId && run.userName === '林序')) failures.push({ label: brief.id, error: 'Brief references missing or another reader run' });
  if (brief.items.some(item => item.publishedAt && Date.parse(item.publishedAt) > Date.parse(brief.generatedAt))) failures.push({ label: brief.id, error: 'News date is after briefing generation' });
}
const operationIds = Object.values(spec.paths).flatMap(p => Object.values(p).map(op => op?.operationId).filter(Boolean));
if (new Set(operationIds).size !== operationIds.length) failures.push({ error: 'Duplicate operationId' });
console.log(JSON.stringify({ examples: examples.length, schemas: Object.keys(spec.components.schemas).length, operations: operationIds.length, instancesChecked: checked, failures }, null, 2));
process.exitCode = failures.length ? 1 : 0;
