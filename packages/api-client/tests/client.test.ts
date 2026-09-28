import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { ApiError, createApiClient } from '../src/client.ts';
import { contractSha256, operationMetadata } from '../src/generated.ts';
import type { RunEvent } from '../src/generated.ts';

/** Transport fixtures only: these tests never claim real backend/provider success. */
function mockFetch(handler: (input: string, init: RequestInit) => Response | Promise<Response>): typeof fetch {
  return async (input, init) => handler(String(input), init || {});
}

test('committed frontend contract remains current in an LF Linux checkout', async () => {
  const root = await mkdtemp(join(tmpdir(), 'zhige-contract-'));
  const files = ['scripts/frontend/generate-contract.mjs', 'backend/src/zhigenews/contracts/openapi.json', 'packages/api-client/src/generated.ts'];
  try {
    for (const file of files) {
      const target = join(root, file);
      await mkdir(dirname(target), { recursive: true });
      const text = await readFile(new URL(`../../../${file}`, import.meta.url), 'utf8');
      await writeFile(target, text.replaceAll('\r\n', '\n'));
    }
    const result = spawnSync(process.execPath, [join(root, files[0]!), '--check'], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.error?.message || result.stdout + result.stderr);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('generated metadata covers the active backend operations and contract fingerprint', async () => {
  const bytes = await readFile(new URL('../../../backend/src/zhigenews/contracts/openapi.json', import.meta.url));
  const contract = JSON.parse(bytes.toString());
  const operations = Object.entries(contract.paths).flatMap(([path, methods]) =>
    Object.entries(methods as Record<string, { operationId: string }>).map(([method, spec]) => ({ path, method, id: spec.operationId })));
  assert.ok(operations.length > 0);
  assert.equal(contractSha256, createHash('sha256').update(bytes).digest('hex'));
  assert.deepEqual(Object.keys(operationMetadata).sort(), operations.map((operation) => operation.id).sort());
  for (const expected of operations) {
    const actual = operationMetadata[expected.id as keyof typeof operationMetadata];
    assert.equal(actual.path, expected.path);
    assert.equal(actual.method, expected.method.toUpperCase());
  }
});

test('encodes identifiers and query values, omits nulls, and forwards cookie credentials and cancellation', async () => {
  const signal = new AbortController().signal;
  const client = createApiClient({ baseUrl: 'https://api.example.invalid/api/v1/', fetch: mockFetch((url, init) => {
    assert.equal(url, 'https://api.example.invalid/api/v1/me/briefs/a%2Fb%3F%E4%B8%AD%E6%96%87?q=%E9%87%8D+%E7%82%B9&page=0&enabled=false');
    assert.equal(init.method, 'GET');
    assert.equal(init.credentials, 'include');
    assert.equal(init.signal, signal);
    assert.equal(init.body, undefined);
    assert.equal(new Headers(init.headers).has('X-Zhige-Request'), false);
    return Response.json({ id: 'synthetic-brief' });
  }) });
  assert.deepEqual(await client.api('getBrief', { path: { id: 'a/b?中文' }, query: { q: '重 点', page: 0, enabled: false, absent: null, missing: undefined }, signal }), { id: 'synthetic-brief' });
});

test('cached news reads preserve source, title and pagination filters and encode both detail identifiers', async () => {
  const requests: string[] = [];
  const item = {
    id: 'synthetic/news', evidenceId: 'synthetic-evidence', sourceId: 'synthetic/source',
    sourceName: '合成新闻来源', title: '合成缓存新闻', url: 'https://example.invalid/news',
    publishedAt: '2026-09-28T00:00:00Z',
  };
  const page = {
    items: [item], total: 21, page: 2, pageSize: 20, totalPages: 2,
    windowStart: '2026-09-27T12:00:00Z', windowEnd: '2026-09-28T12:00:00Z',
    sources: [{ id: item.sourceId, name: item.sourceName, count: 25 }],
  };
  const detail = {
    ...item, sourceUrl: 'https://example.invalid/feed.xml', snapshotId: 'synthetic-snapshot',
    fetchedAt: '2026-09-28T00:10:00Z', firstSeenAt: '2026-09-28T00:10:00Z',
    summary: '合成摘要', content: '合成缓存正文',
  };
  const client = createApiClient({ fetch: mockFetch((url, init) => {
    requests.push(url);
    assert.equal(init.method, 'GET');
    assert.equal(init.credentials, 'include');
    assert.equal(init.body, undefined);
    assert.equal(new Headers(init.headers).has('X-Zhige-Request'), false);
    return Response.json(requests.length === 1 ? page : detail);
  }) });
  assert.equal(operationMetadata.listCachedNews.role, 'admin');
  assert.equal(operationMetadata.getCachedNews.role, 'admin');
  assert.deepEqual(await client.api('listCachedNews', {
    query: { sourceId: item.sourceId, q: '缓存 新闻', page: 2 },
  }), page);
  assert.deepEqual(await client.api('getCachedNews', {
    path: { sourceId: item.sourceId, id: item.id },
  }), detail);
  assert.deepEqual(requests, [
    '/api/v1/admin/news?sourceId=synthetic%2Fsource&q=%E7%BC%93%E5%AD%98+%E6%96%B0%E9%97%BB&page=2',
    '/api/v1/admin/sources/synthetic%2Fsource/news/synthetic%2Fnews',
  ]);
});

test('writes use JSON/CSRF and preserve the callers intent key without automatic retries', async () => {
  let calls = 0;
  const client = createApiClient({ fetch: mockFetch((url, init) => {
    calls++;
    assert.equal(url, '/api/v1/me/briefs');
    assert.equal(init.method, 'POST');
    assert.equal(init.body, '{"preferenceVersion":3}');
    assert.equal(init.credentials, 'include');
    const headers = new Headers(init.headers);
    assert.equal(headers.get('X-Zhige-Request'), '1');
    assert.equal(headers.get('Idempotency-Key'), 'synthetic-stable-intent');
    assert.equal(headers.get('Content-Type'), 'application/json');
    return Response.json({ code: 'RATE_LIMITED', message: '请求过于频繁', requestId: 'synthetic-request', fields: { version: '刷新版本' } }, { status: 429, headers: { 'Retry-After': '15' } });
  }) });
  for (let attempt = 0; attempt < 2; attempt++) {
    await assert.rejects(client.api('generateBrief', { body: { preferenceVersion: 3 }, idempotencyKey: 'synthetic-stable-intent' }), (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 429);
      assert.equal(error.code, 'RATE_LIMITED');
      assert.equal(error.message, '请求过于频繁');
      assert.equal(error.retryAfter, 15);
      assert.equal(error.requestId, 'synthetic-request');
      assert.deepEqual(error.fields, { version: '刷新版本' });
      return true;
    });
    assert.equal(calls, attempt + 1);
  }
});

test('DELETE and bodyless POST still send CSRF; 204 remains empty', async () => {
  const methods: string[] = [];
  const client = createApiClient({ fetch: mockFetch((_url, init) => {
    methods.push(init.method!);
    assert.equal(new Headers(init.headers).get('X-Zhige-Request'), '1');
    assert.equal(init.body, undefined);
    return init.method === 'DELETE' ? new Response(null, { status: 204 }) : Response.json({ kind: 'anonymous' });
  }) });
  assert.equal(await client.api('adminLogout'), undefined);
  assert.deepEqual(await client.api('ensureAnonymousSession'), { kind: 'anonymous' });
  assert.deepEqual(methods, ['DELETE', 'POST']);
});

test('invalid operation, missing path/idempotency and wrong stream helper fail before network', async () => {
  let calls = 0;
  const client = createApiClient({ fetch: mockFetch(() => { calls++; return Response.json({}); }) });
  await assert.rejects(client.api('unknownOperation'), TypeError);
  await assert.rejects(client.api('getBrief'), TypeError);
  await assert.rejects(client.api('generateBrief', { body: { preferenceVersion: 1 } }), TypeError);
  await assert.rejects(client.api('adminRunEvents', { path: { id: 'synthetic-run' } }), TypeError);
  assert.equal(calls, 0);
});

test('proxy errors stay errors, malformed success is not fake data, and abort propagates', async () => {
  const client = createApiClient({ fetch: mockFetch(() => new Response('<html>proxy failure</html>', { status: 503, headers: { 'X-Request-ID': 'proxy-request' } })) });
  await assert.rejects(client.api('getSession'), (error: unknown) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 503);
    assert.equal(error.code, 'HTTP_ERROR');
    assert.equal(error.requestId, 'proxy-request');
    assert.equal(error.retryAfter, null);
    assert.equal(error.message.includes('<html>'), false);
    return true;
  });
  const invalid = createApiClient({ fetch: mockFetch(() => new Response('not json', { status: 200 })) });
  await assert.rejects(invalid.api('getPreferences'), (error: unknown) => error instanceof ApiError && error.code === 'INVALID_RESPONSE');
  const abort = new DOMException('Aborted', 'AbortError');
  const aborted = createApiClient({ fetch: mockFetch(() => { throw abort; }) });
  await assert.rejects(aborted.api('getPreferences'), (error: unknown) => error === abort);
});

function event(id: number): RunEvent {
  return { id, time: '2026-09-19T00:00:00Z', title: '合成测试事件', detail: 'Synthetic transport fixture', status: 'running', duration: '1ms' };
}

function stream(events: number[], close = true): Response {
  const text = ': keepalive\r\n' + events.map((id) => `id: ${id}\r\nevent: run.event\r\ndata: ${JSON.stringify(event(id))}\r\n\r\n`).join('');
  const bytes = new TextEncoder().encode(text);
  return new Response(new ReadableStream<Uint8Array>({ start(controller) {
    // One-byte chunks deliberately split UTF-8 codepoints and every CRLF pair.
    for (let index = 0; index < bytes.length; index++) controller.enqueue(bytes.subarray(index, index + 1));
    if (close) controller.close();
  } }), { headers: { 'Content-Type': 'text/event-stream; charset=utf-8' } });
}

test('SSE reconnects with Last-Event-ID, handles fragmented UTF-8/CRLF and deduplicates replay', async () => {
  const statuses: string[] = [], delivered: number[] = [], cursors: (string | null)[] = [], errors: string[] = [];
  let calls = 0;
  let finished!: () => void;
  const complete = new Promise<void>((resolve) => { finished = resolve; });
  const client = createApiClient({ reconnectDelayMs: 0, fetch: mockFetch((url, init) => {
    calls++;
    assert.equal(url, '/api/v1/admin/runs/synthetic%2Frun/events');
    assert.equal(init.credentials, 'include');
    assert.equal(new Headers(init.headers).get('Accept'), 'text/event-stream');
    cursors.push(new Headers(init.headers).get('Last-Event-ID'));
    return calls === 1 ? stream([2]) : stream([2, 3], false);
  }) });
  const stop = client.subscribeRunEvents('synthetic/run', {
    afterId: 1,
    onEvent(value) {
      assert.equal(value.title, '合成测试事件');
      delivered.push(value.id);
      if (value.id === 3) { stop(); finished(); }
    },
    onStatus: (status) => statuses.push(status),
    onError: (error) => errors.push(error.message),
  });
  await complete;
  assert.equal(calls, 2);
  assert.deepEqual(delivered, [2, 3]);
  assert.deepEqual(cursors, ['1', '2']);
  assert.deepEqual(statuses, ['connecting', 'open', 'reconnecting', 'open', 'closed']);
  assert.equal(errors.length, 1);
  stop();
  assert.equal(statuses.filter((value) => value === 'closed').length, 1);
});

test('SSE authorization failure closes without retrying or fabricating a failed run event', async () => {
  let calls = 0, eventCount = 0;
  const statuses: string[] = [];
  let failed: Error | undefined;
  let finished!: () => void;
  const complete = new Promise<void>((resolve) => { finished = resolve; });
  const client = createApiClient({ fetch: mockFetch(() => {
    calls++;
    return Response.json({ code: 'FORBIDDEN', message: '管理员身份已失效', requestId: 'synthetic-auth' }, { status: 403 });
  }) });
  client.subscribeRunEvents('synthetic-run', {
    onEvent: () => { eventCount++; },
    onError: (error) => { failed = error; },
    onStatus: (status) => { statuses.push(status); if (status === 'closed') finished(); },
  });
  await complete;
  assert.equal(calls, 1);
  assert.equal(eventCount, 0);
  assert.ok(failed instanceof ApiError);
  assert.equal(failed.code, 'FORBIDDEN');
  assert.deepEqual(statuses, ['connecting', 'closed']);
});

test('stopping an opening SSE subscription aborts it and never reports open afterwards', async () => {
  let respond!: (response: Response) => void;
  let signal: AbortSignal | null | undefined;
  const statuses: string[] = [];
  const client = createApiClient({ fetch: mockFetch((_url, init) => {
    signal = init.signal;
    return new Promise<Response>((resolve) => { respond = resolve; });
  }) });
  const stop = client.subscribeRunEvents('synthetic-run', { onEvent: () => assert.fail('No event expected'), onStatus: (status) => statuses.push(status) });
  stop();
  assert.equal(signal?.aborted, true);
  respond(stream([1]));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(statuses, ['connecting', 'closed']);
});
