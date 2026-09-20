const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const vue = require('vue');

function setup(file = 'source-list') {
  const pending = [];
  const source = fs.readFileSync(path.join(__dirname, `../src/${file}.ts`), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const exports = {};
  new Function('require', 'exports', code)(name => name === 'vue' ? { ...vue, onBeforeUnmount() {} } : {
    request: (operation, options) => new Promise((resolve, reject) => pending.push({ resolve, reject, options })), errorText: String,
  }, exports);
  return { list: exports.useSourceList?.(), deletion: exports.useSourceDeletion?.(), pending };
}
const page = (items, n = 1) => ({ items, page: n, total: 20, totalPages: 2, invalidTotal: 2 });

test('background refresh preserves selection and does not disable page operations', async () => {
  const { list, pending } = setup();
  let load = list.load(); pending.shift().resolve(page([{ id: 'a' }])); await load;
  list.toggle('a');
  load = list.refresh();
  assert.equal(list.loading.value, false);
  assert.equal(list.refreshing.value, true);
  list.toggle('b');
  pending.shift().resolve(page([{ id: 'a' }])); await load;
  assert.deepEqual([...list.selectedIds.value], ['a', 'b']);
});

test('old refresh cannot overwrite a successful write', async () => {
  const { list, pending } = setup();
  let load = list.load(); pending.shift().resolve(page([{ id: 'a', enabled: true }])); await load;
  load = list.refresh(); const old = pending.shift();
  list.invalidate(); list.replace({ id: 'a', enabled: false });
  assert.equal(old.options.signal.aborted, true);
  old.resolve(page([{ id: 'a', enabled: true }])); await load;
  assert.equal(list.items.value[0].enabled, false);
});

test('page navigation supersedes refresh; deletion progress cannot resurrect removed rows', async () => {
  const { list, pending } = setup();
  let load = list.load(); pending.shift().resolve(page([{ id: 'a' }])); await load;
  const refresh = list.refresh(); const old = pending.shift();
  const next = list.load(2); const current = pending.shift();
  list.remove(['b']);
  current.resolve(page([{ id: 'b' }, { id: 'c' }], 2)); await next;
  old.resolve(page([{ id: 'a' }])); await refresh;
  assert.equal(list.page.value, 2);
  assert.deepEqual(list.items.value.map(item => item.id), ['c']);
});

test('old status requests cannot re-enable deletion after a job is accepted', async () => {
  const { deletion, pending } = setup('source-deletion');
  const poll = deletion.poll(); const stale = pending.shift();
  deletion.accept({ id: 'job', status: 'queued', items: [{ id: 'a', status: 'pending' }] });
  stale.resolve({ job: null }); await poll;
  assert.equal(deletion.unavailable.value, true);
  assert.equal(deletion.pendingIds.value.has('a'), true);
  assert.equal(stale.options.signal.aborted, true);
});

test('revisit restores job; connection errors preserve progress until completion is confirmed', async () => {
  const { deletion, pending } = setup('source-deletion');
  assert.equal(deletion.unavailable.value, true);
  let poll = deletion.poll();
  pending.shift().resolve({ job: { id: 'job', status: 'running', items: [{ id: 'a', status: 'running' }] } }); await poll;
  poll = deletion.poll(); pending.shift().reject(new Error('offline')); await poll;
  assert.equal(deletion.job.value.status, 'running');
  assert.equal(deletion.unavailable.value, true);
  poll = deletion.poll(); pending.shift().resolve({ job: { id: 'job', status: 'completed', items: [{ id: 'a', status: 'deleted' }] } }); await poll;
  assert.equal(deletion.unavailable.value, false);
  assert.equal(deletion.pendingIds.value.size, 0);
  assert.equal(deletion.error.value, '');
});
