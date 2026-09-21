const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const vue = require('vue');

function setup() {
  const requests = [], timers = new Map(), errors = [], cleanup = [];
  class ApiError extends Error { constructor(status, retryAfter) { super('internal'); this.status = status; this.retryAfter = retryAfter; } }
  const source = fs.readFileSync(path.join(__dirname, '../src/useGeneration.ts'), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const exports = {};
  let timerId = 0;
  new Function('require', 'exports', 'setTimeout', 'clearTimeout', code)(name => name === 'vue'
    ? { ...vue, onBeforeUnmount: fn => cleanup.push(fn) }
    : { ApiError, api: (operation, options) => new Promise((resolve, reject) => requests.push({ operation, options, resolve, reject })) },
  exports, (fn, delay) => { timers.set(++timerId, { fn, delay }); return timerId; }, id => timers.delete(id));
  const brief = vue.ref({ id: 'previous', items: [{ id: 'news' }] });
  return { state: exports.useGeneration(brief, error => errors.push(error)), brief, requests, timers, errors, ApiError, cleanup };
}
const running = { id: 'run', status: 'running', phase: 'researching', briefId: null, emptyResult: false };

test('restores the current run and automatically reconnects without replacing readable content', async () => {
  const { state, requests, timers, brief } = setup();
  let pending = state.poll();
  assert.equal(requests[0].operation, 'getCurrentGeneration');
  requests.shift().resolve(running); await pending;
  pending = state.poll(); requests.shift().reject(new Error('offline')); await pending;
  assert.equal(state.reconnecting.value, true);
  assert.equal(state.progress.value.id, 'run');
  assert.equal(brief.value.id, 'previous');
  assert.equal([...timers.values()][0].delay, 3000);
  pending = [...timers.values()][0].fn();
  assert.equal(requests[0].operation, 'getGenerationProgress');
  assert.equal(requests[0].options.path.id, 'run');
  requests.shift().resolve({ ...running, status: 'completed', emptyResult: true }); await pending;
  assert.equal(state.reconnecting.value, false);
  assert.equal(state.progress.value.emptyResult, true);
  assert.equal(brief.value.id, 'previous');
  assert.equal(timers.size, 0);
});

test('failed content download retries the same completed run before announcing success', async () => {
  const { state, requests, brief } = setup();
  await state.accept(running);
  let pending = state.accept({ ...running, status: 'partial', briefId: 'new' });
  requests.shift().reject(new Error('offline')); await pending;
  assert.equal(state.progress.value.status, 'running');
  assert.equal(state.reconnecting.value, true);
  assert.equal(brief.value.id, 'previous');
  pending = state.poll(); requests.shift().resolve({ ...running, status: 'partial', briefId: 'new' });
  await Promise.resolve();
  requests.shift().resolve({ id: 'new', items: [{ id: 'new-news' }] }); await pending;
  assert.equal(state.progress.value.status, 'partial');
  assert.equal(state.reconnecting.value, false);
  assert.equal(brief.value.id, 'new');
});

test('late poll cannot overwrite cancellation or restart polling', async () => {
  const { state, requests, timers } = setup();
  await state.accept(running);
  const pending = state.poll(), stale = requests.shift();
  await state.accept({ ...running, status: 'cancelled' });
  assert.equal(stale.options.signal.aborted, true);
  stale.resolve(running); await pending;
  assert.equal(state.progress.value.status, 'cancelled');
  assert.equal(timers.size, 0);
});

test('rate limits respect Retry-After; access errors stop automatic retry', async () => {
  const { state, requests, timers, ApiError, errors } = setup();
  let pending = state.poll(); requests.shift().reject(new ApiError(429, 45)); await pending;
  assert.equal([...timers.values()][0].delay, 45000);
  pending = state.poll(); requests.shift().reject(new ApiError(401)); await pending;
  assert.equal(timers.size, 0);
  assert.equal(state.reconnecting.value, false);
  assert.equal(errors.length, 1);
});

test('unmount fences outstanding requests and scheduled reconnection', async () => {
  const { state, requests, timers, cleanup } = setup();
  await state.accept(running);
  const pending = state.poll(), last = requests.shift();
  cleanup.forEach(fn => fn());
  assert.equal(last.options.signal.aborted, true);
  last.reject(new Error('offline')); await pending;
  assert.equal(timers.size, 0);
  assert.equal(state.reconnecting.value, false);
});
