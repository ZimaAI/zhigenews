import assert from 'node:assert/strict';
import { readFile, mkdtemp, unlink, rmdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer, transformWithEsbuild } from 'vite';

const source = await readFile(new URL('../shared/demo-server.ts', import.meta.url), 'utf8');
const transformed = await transformWithEsbuild(source, 'demo-server.ts', { loader: 'ts' });
const { anonymousDemoServer } = await import('data:text/javascript;base64,' + Buffer.from(transformed.code).toString('base64'));
const dir = await mkdtemp(join(tmpdir(), 'zhige-anonymous-check-'));
const database = join(dir, 'accounts.json');
let server, base;
const checks = [];
async function start() { server = await createServer({ configFile: false, plugins: [anonymousDemoServer(database)], server: { host: '127.0.0.1', port: 0, strictPort: false }, logLevel: 'silent' }); await server.listen(); base = `http://127.0.0.1:${server.httpServer.address().port}/__demo`; }
async function call(path, cookie = '', body, extra = {}) {
  const response = await fetch(base + path, { method: extra.method || (body === undefined ? 'GET' : 'POST'), headers: { 'Content-Type': 'application/json', 'X-Prototype-Request': '1', ...(cookie ? { Cookie: cookie } : {}), ...extra.headers }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  return { status: response.status, cookie: response.headers.get('set-cookie'), retry: response.headers.get('retry-after'), data: await response.json() };
}
try {
  await start();
  const first = await call('/anonymous/session', '', {}); assert.equal(first.status, 200);
  assert.match(first.cookie, /HttpOnly/); assert.match(first.cookie, /SameSite=Lax/); assert.match(first.cookie, /Path=\//);
  const userCookie = first.cookie.split(';')[0]; const accountId = first.data.session.userId;
  assert.equal((await call('/anonymous/session', userCookie, {})).data.session.userId, accountId);
  assert.equal(first.data.session.kind, 'anonymous'); assert.ok(!JSON.stringify(first.data).includes(userCookie.split('=')[1])); checks.push('server Cookie flags, opaque token, idempotent identity');
  assert.equal((await call('/admin/anonymous', userCookie)).status, 401);
  assert.equal((await call('/anonymous/session', userCookie, {}, { headers: { Origin: 'https://untrusted.example' } })).status, 403);
  assert.equal((await call('/anonymous/session', userCookie, {}, { headers: { 'X-Prototype-Request': '' } })).status, 403); checks.push('anonymous/admin isolation and write-origin protection');
  const admin = await call('/admin/session', '', { email: 'admin@example.com', password: 'demo-admin' }); assert.equal(admin.status, 200);
  const adminCookie = admin.cookie.split(';')[0];
  const second = await call('/anonymous/session', '', {}); const secondCookie = second.cookie.split(';')[0]; assert.notEqual(second.data.session.userId, accountId);
  const [job, duplicate] = await Promise.all([call('/anonymous/generation', userCookie, {}), call('/anonymous/generation', userCookie, {})]);
  assert.equal(job.status, 200); assert.equal(job.data.id, duplicate.data.id);
  assert.deepEqual(Object.keys(job.data).sort(), ['id','status','percent','remainingSeconds','updatedAt','briefId','error'].sort());
  const concurrent = await call('/anonymous/generation', secondCookie, {}); assert.equal(concurrent.status, 429); assert.ok(Number(concurrent.retry) > 0);
  const listed = await call('/admin/anonymous', adminCookie); const user = listed.data.users.find(u => u.id === accountId); assert.equal(user.generationsToday, 1); assert.equal(user.activeGenerations, 1); checks.push('concurrent duplicate coalescing, quota counters, public progress projection');
  assert.equal((await call('/anonymous/generation/cancel', userCookie, {})).data.status, 'cancelled');
  assert.equal((await call(`/admin/anonymous/${accountId}/status`, adminCookie, { status: 'blocked', reason: 'test abuse' })).status, 200);
  assert.equal((await call('/anonymous/session', userCookie, {})).status, 403);
  assert.equal((await call('/anonymous/generation', userCookie)).status, 403);
  assert.equal((await call(`/admin/anonymous/${accountId}/status`, adminCookie, { status: 'active', reason: 'test resolved' })).status, 200);
  assert.equal((await call('/anonymous/session', userCookie, {})).data.session.userId, accountId); checks.push('blocked Cookie refused, cancellation, reversible audited release');
  const policy = listed.data.policy;
  assert.equal((await call('/admin/policy', adminCookie, { ...policy, requestsPerMinute: 0 }, { method:'PUT' })).status, 400);
  assert.equal((await call('/admin/policy', adminCookie, { ...policy, generationsPerDay: 1, accountsPerIpHour: 1 }, { method:'PUT' })).status, 200);
  assert.equal((await call('/anonymous/generation', userCookie, {})).status, 429);
  assert.equal((await call('/anonymous/session', '', {})).status, 429); checks.push('policy validation, daily generation cap, cookie-deletion/IP creation quota');
  await server.close(); await start();
  assert.equal((await call('/anonymous/session', userCookie, {})).data.session.userId, accountId); checks.push('identity and policies persist across prototype-server restart');
  await call(`/admin/anonymous/${accountId}/simulate`, adminCookie, {});
  const limited = await call('/anonymous/touch', userCookie, {}); assert.equal(limited.status, 429); assert.ok(Number(limited.retry) > 0);
  const after = await call('/admin/anonymous', adminCookie); assert.ok(after.data.events.some(e => e.accountId === accountId && e.kind === 'rate_limited')); checks.push('simulated burst invokes actual quota rejection and monitoring event');
  console.log(JSON.stringify({ checks, passed: checks.length, failures: [] }, null, 2));
} finally {
  await server?.close();
  await unlink(database).catch(() => {});
  await unlink(database + '.tmp').catch(() => {});
  await rmdir(dir);
}
