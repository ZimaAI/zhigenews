const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const vue = require('vue');

function setup() {
  const pending = [];
  const source = fs.readFileSync(path.join(__dirname, '../src/news.ts'), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const exports = {};
  new Function('require', 'exports', code)(name => name === 'vue' ? { ...vue, onBeforeUnmount() {} } : {
    request: (operation, options) => new Promise((resolve, reject) => pending.push({ operation, options, resolve, reject })),
    errorText: error => error.message,
  }, exports);
  return { list: exports.useNewsList(), detail: exports.useNewsDetail(), newsUrl: exports.newsUrl, pending };
}

const filters = (sourceId = '', page = 1, q = '') => ({ sourceId, q, page });
const page = (sourceId, number = 1) => ({
  items: [{ id: `news-${sourceId}-${number}`, sourceId }],
  sources: [{ id: sourceId, name: sourceId, count: 30 }],
  page: number, pageSize: 20, total: 30, totalPages: 2,
});

test('switching sources prevents an older response from replacing the selected source', async () => {
  const { list, pending } = setup();
  const firstLoad = list.load(filters('first'));
  const first = pending.shift();
  const secondLoad = list.load(filters('second'));
  const second = pending.shift();
  assert.equal(first.options.signal.aborted, true);
  assert.equal(second.operation, 'listCachedNews');
  assert.deepEqual(second.options.query, filters('second'));

  const currentPage = page('second');
  second.resolve(currentPage);
  await secondLoad;
  first.resolve(page('first'));
  await firstLoad;

  assert.deepEqual(list.result.value, currentPage);
  assert.deepEqual(list.sources.value, currentPage.sources);
  assert.equal(list.loading.value, false);
  assert.equal(list.error.value, '');
});

test('switching pages keeps the latest page loading when an old request fails', async () => {
  const { list, pending } = setup();
  const firstLoad = list.load(filters('source', 1));
  const first = pending.shift();
  const secondLoad = list.load(filters('source', 2));
  const second = pending.shift();

  first.reject(new Error('old page failed'));
  await firstLoad;
  assert.equal(first.options.signal.aborted, true);
  assert.equal(list.loading.value, true);
  assert.equal(list.error.value, '');
  assert.equal(list.result.value, null);

  second.resolve(page('source', 2));
  await secondLoad;
  assert.equal(list.result.value.page, 2);
  assert.equal(list.loading.value, false);
});

test('a failed refresh of the same query preserves the previous successful result', async () => {
  const { list, pending } = setup();
  const initialPage = page('source');
  const initialLoad = list.load(filters('source', 1, 'keyword'));
  pending.shift().resolve(initialPage);
  await initialLoad;

  const refresh = list.load(filters('source', 1, 'keyword'));
  assert.deepEqual(list.result.value, initialPage);
  assert.equal(list.loading.value, true);
  pending.shift().reject(new Error('offline'));
  await refresh;

  assert.deepEqual(list.result.value, initialPage);
  assert.deepEqual(list.sources.value, initialPage.sources);
  assert.equal(list.error.value, 'offline');
  assert.equal(list.loading.value, false);
});

test('changing a filter clears the old rows even when the new request fails', async () => {
  for (const nextFilters of [filters('second'), filters('first', 2), filters('first', 1, 'new keyword')]) {
    const { list, pending } = setup();
    const initialLoad = list.load(filters('first'));
    pending.shift().resolve(page('first'));
    await initialLoad;

    const nextLoad = list.load(nextFilters);
    assert.equal(list.result.value, null);
    pending.shift().reject(new Error('new query failed'));
    await nextLoad;

    assert.equal(list.result.value, null);
    assert.equal(list.error.value, 'new query failed');
    assert.equal(list.loading.value, false);
  }
});

test('switching detail articles clears the old content and ignores late responses', async () => {
  const { detail, pending } = setup();
  const initialLoad = detail.load('source', 'initial');
  pending.shift().resolve({ id: 'initial' });
  await initialLoad;

  const oldLoad = detail.load('source', 'old');
  const old = pending.shift();
  assert.equal(detail.item.value, null);
  const currentLoad = detail.load('other-source', 'current');
  const current = pending.shift();
  assert.equal(old.options.signal.aborted, true);
  assert.equal(current.operation, 'getCachedNews');
  assert.deepEqual(current.options.path, { sourceId: 'other-source', id: 'current' });

  current.resolve({ id: 'current', sourceId: 'other-source' });
  await currentLoad;
  old.resolve({ id: 'old', sourceId: 'source' });
  await oldLoad;

  assert.deepEqual(detail.item.value, { id: 'current', sourceId: 'other-source' });
  assert.equal(detail.loading.value, false);
  assert.equal(detail.error.value, '');
});

test('returning to the list cancels detail state and ignores late success or failure', async () => {
  for (const outcome of ['success', 'failure']) {
    const { detail, pending } = setup();
    const load = detail.load('source', 'article');
    const request = pending.shift();
    await detail.load('', '');

    assert.equal(request.options.signal.aborted, true);
    assert.equal(pending.length, 0);
    assert.equal(detail.item.value, null);
    assert.equal(detail.loading.value, false);
    if (outcome === 'success') request.resolve({ id: 'article' });
    else request.reject(new Error('late detail failure'));
    await load;

    assert.equal(detail.item.value, null);
    assert.equal(detail.error.value, '');
    assert.equal(detail.loading.value, false);
  }
});

test('external news links allow HTTP and HTTPS and reject executable or invalid URLs', () => {
  const { newsUrl } = setup();
  assert.equal(newsUrl('https://example.com/article?q=1#section'), 'https://example.com/article?q=1#section');
  assert.equal(newsUrl('http://example.com/article'), 'http://example.com/article');
  for (const value of ['javascript:alert(1)', 'JavaScript:alert(1)', 'data:text/html,<script>alert(1)</script>', 'file:///tmp/article', '//example.com/article', '/article', '']) {
    assert.equal(newsUrl(value), undefined, value);
  }
});
