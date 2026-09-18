// Dev-only fixture service. Demonstrates server-issued cookies and quotas; not a production Gateway.
import type { Plugin } from 'vite';
import type { IncomingMessage, ServerResponse } from 'node:http';
import { createHash, randomBytes, randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync, renameSync } from 'node:fs';
import { dirname } from 'node:path';
import type { AnonymousAccount, AnonymousPolicy, AbuseEvent } from './anonymous';
import type { GenerationProgress } from './types';
type Account = Omit<AnonymousAccount, 'requestsLastMinute' | 'generationsToday' | 'activeGenerations'> & { requests: number[]; generations: number[]; ipKey: string; onboardingCompleted: boolean; generation: GenerationProgress | null; started: number; duration: number; partial: boolean };
type Database = { accounts: Account[]; sessions: Record<string, { accountId: string; expires: number }>; admins: Record<string, number>; ips: Record<string, { requests: number[]; created: number[]; generations: number[] }>; events: AbuseEvent[]; policy: AnonymousPolicy };
const minute = 60_000, hour = 60 * minute, day = 24 * hour;
const digest = (value: string) => createHash('sha256').update(value).digest('hex');
const iso = () => new Date().toISOString();
class Reject extends Error { constructor(public status: number, message: string, public retry = 0) { super(message); } }
export function anonymousDemoServer(file: string): Plugin {
  let db: Database = { accounts: [], sessions: {}, admins: {}, ips: {}, events: [], policy: { requestsPerMinute: 60, generationsPerDay: 20, maxConcurrentGenerations: 1, accountsPerIpHour: 10 } };
  if (existsSync(file)) db = JSON.parse(readFileSync(file, 'utf8')) as Database;
  function save() { mkdirSync(dirname(file), { recursive: true }); writeFileSync(`${file}.tmp`, JSON.stringify(db)); renameSync(`${file}.tmp`, file); }
  function event(accountId: string, kind: AbuseEvent['kind'], detail: string) { db.events.unshift({ id: randomUUID(), accountId, kind, detail, time: iso() }); db.events = db.events.slice(0, 300); }
  function cookie(req: IncomingMessage, name: string) { return (req.headers.cookie || '').split(';').map(x => x.trim()).find(x => x.startsWith(name + '='))?.slice(name.length + 1) || ''; }
  function issue(req: IncomingMessage, res: ServerResponse, name: string, maxAge: number, path: string) { const token = randomBytes(32).toString('hex'); res.setHeader('Set-Cookie', `${name}=${token}; Path=${path}; Max-Age=${maxAge}; HttpOnly; SameSite=Lax${'encrypted' in req.socket && req.socket.encrypted ? '; Secure' : ''}`); return digest(token); }
  function finish(account: Account) { const g = account.generation; if (!g || !['running', 'queued'].includes(g.status)) return; const fraction = Math.min(1, (Date.now() - account.started) / account.duration); Object.assign(g, { status: fraction === 1 ? account.partial ? 'partial' : 'completed' : 'running', percent: fraction === 1 ? 100 : Math.min(95, Math.floor(fraction * 100)), remainingSeconds: Math.max(0, Math.ceil((account.duration - (Date.now() - account.started)) / 1000)), updatedAt: iso(), briefId: fraction === 1 ? `brief-${g.id}` : null }); }
  function accountFor(req: IncomingMessage) { const session = db.sessions[digest(cookie(req, 'zhige_anon'))]; if (!session || session.expires <= Date.now()) return; return db.accounts.find(x => x.id === session.accountId); }
  async function body(req: IncomingMessage): Promise<Record<string, unknown>> { let input = ''; for await (const chunk of req) { input += chunk; if (input.length > 16384) throw new Reject(413, '请求内容过大。'); } try { return input ? JSON.parse(input) : {}; } catch { throw new Reject(400, '请求格式不正确。'); } }
  function checkWrite(req: IncomingMessage) { if (req.method === 'GET') return; if (req.headers['x-prototype-request'] !== '1' || !req.headers['content-type']?.startsWith('application/json')) throw new Reject(403, '请求来源验证失败。'); const origin = req.headers.origin; if (origin && !['http://127.0.0.1:5173', 'http://127.0.0.1:5174', 'http://localhost:5173', 'http://localhost:5174'].includes(origin)) throw new Reject(403, '请求来源验证失败。'); }
  function view(account: Account): AnonymousAccount { finish(account); const { requests, generations, ipKey: _ipKey, onboardingCompleted: _onboarded, generation, started: _started, duration: _duration, partial: _partial, ...safe } = account; return { ...safe, requestsLastMinute: requests.filter(t => t > Date.now() - minute).length, generationsToday: generations.filter(t => new Date(t).toDateString() === new Date().toDateString()).length, activeGenerations: generation && ['queued', 'running', 'cancelling'].includes(generation.status) ? 1 : 0 }; }
  return { name: 'anonymous-fixture-service', apply: 'serve', configureServer(server) {
    server.middlewares.use('/__demo', async (req, res) => {
      res.setHeader('Content-Type', 'application/json; charset=utf-8'); res.setHeader('Cache-Control', 'no-store');
      const send = (value: unknown = {}) => { save(); res.end(JSON.stringify(value)); };
      try {
        checkWrite(req);
        const path = (req.url || '').split('?')[0]; const now = Date.now();
        if (path === '/admin/session' && req.method === 'POST') { const data = await body(req); if (data.email !== 'admin@example.com' || data.password !== 'demo-admin') throw new Reject(401, '演示凭据不正确。'); db.admins[issue(req, res, 'zhige_demo_admin', 3600, '/__demo/admin')] = now + hour; return send(); }
        if (path.startsWith('/admin/')) {
          const token = digest(cookie(req, 'zhige_demo_admin')); if (!db.admins[token] || db.admins[token]! <= now) throw new Reject(401, '请先进入管理员演示会话。');
          if (path === '/admin/session') { if (req.method === 'DELETE') { delete db.admins[token]; res.setHeader('Set-Cookie', 'zhige_demo_admin=; Path=/__demo/admin; Max-Age=0; HttpOnly; SameSite=Lax'); return send(); } return send({ kind: 'admin', userId: 'admin-demo', name: '管理员' }); }
          if (path === '/admin/anonymous' && req.method === 'GET') return send({ users: db.accounts.map(view), events: db.events, policy: db.policy });
          if (path === '/admin/policy' && req.method === 'PUT') { const data = await body(req); const limits = { requestsPerMinute: 600, generationsPerDay: 100, maxConcurrentGenerations: 10, accountsPerIpHour: 100 }; for (const [key, max] of Object.entries(limits)) if (!Number.isInteger(data[key]) || Number(data[key]) < 1 || Number(data[key]) > max) throw new Reject(400, '策略必须是范围内的正整数。'); db.policy = Object.fromEntries(Object.keys(limits).map(key => [key, data[key]])) as unknown as AnonymousPolicy; return send(); }
          const match = path.match(/^\/admin\/anonymous\/([^/]+)\/(status|simulate)$/); if (!match || req.method !== 'POST') throw new Reject(404, '接口不存在。');
          const account = db.accounts.find(x => x.id === decodeURIComponent(match[1]!)); if (!account) throw new Reject(404, '账户不存在。');
          if (match[2] === 'simulate') { account.requests = Array.from({ length: db.policy.requestsPerMinute }, () => now); account.rateLimitHits++; account.risk = 'high'; event(account.id, 'rate_limited', '模拟异常：达到每分钟请求上限；该账户下一次访问将按策略限流。'); return send(); }
          const data = await body(req); if (!['active', 'blocked'].includes(String(data.status)) || typeof data.reason !== 'string' || !data.reason.trim() || data.reason.length > 200) throw new Reject(400, '请选择状态并填写 1–200 字原因。');
          account.status = data.status as Account['status']; account.blockReason = account.status === 'blocked' ? data.reason.trim() : ''; account.risk = account.status === 'blocked' ? 'high' : 'normal';
          if (account.status === 'blocked' && account.generation && ['queued', 'running'].includes(account.generation.status)) Object.assign(account.generation, { status: 'cancelled', remainingSeconds: null, updatedAt: iso() });
          event(account.id, account.status === 'blocked' ? 'account_blocked' : 'account_unblocked', data.reason.trim()); return send();
        }
        if (!path.startsWith('/anonymous/')) throw new Reject(404, '接口不存在。');
        const ipKey = digest(req.socket.remoteAddress || 'local'); const ip = db.ips[ipKey] ||= { requests: [], created: [], generations: [] };
        ip.requests = ip.requests.filter(t => t > now - minute); ip.created = ip.created.filter(t => t > now - hour); ip.generations = ip.generations.filter(t => t > now - day);
        let account = accountFor(req);
        if (account?.status === 'blocked') throw new Reject(403, '当前匿名账户已暂停访问。');
        if (account) account.requests = account.requests.filter(t => t > now - minute);
        if (ip.requests.length >= db.policy.requestsPerMinute || (account && account.requests.length >= db.policy.requestsPerMinute)) { if (account) { account.rateLimitHits++; account.risk = 'watch'; event(account.id, 'rate_limited', '达到每分钟访问上限。'); } throw new Reject(429, '访问较频繁，请稍后重试。', 60); }
        ip.requests.push(now);
        if (!account && path === '/anonymous/session' && req.method === 'POST') {
          if (ip.created.length >= db.policy.accountsPerIpHour) throw new Reject(429, '此网络创建账户较频繁，请稍后再试。', Math.ceil((ip.created[0]! + hour - now) / 1000));
          const key = randomUUID(); account = { id: `anon-${key}`, name: `匿名读者 ${key.slice(0, 4)}`, createdAt: iso(), lastSeenAt: iso(), status: 'active', risk: 'normal', requests: [], generations: [], rateLimitHits: 0, ipLabel: `本地演示 · ${ipKey.slice(0, 6)}`, blockReason: '', ipKey, onboardingCompleted: false, generation: null, started: 0, duration: 12000, partial: false };
          db.accounts.unshift(account); ip.created.push(now); db.sessions[issue(req, res, 'zhige_anon', 7 * 86400, '/')] = { accountId: account.id, expires: now + 7 * day };
        }
        if (!account) throw new Reject(401, '匿名会话已失效，请重新进入。');
        account.requests.push(now); account.lastSeenAt = iso(); finish(account);
        if (path === '/anonymous/session') return send({ session: { kind: 'anonymous', userId: account.id, name: account.name, onboardingCompleted: account.onboardingCompleted }, generation: account.generation });
        if (path === '/anonymous/touch') return send();
        if (path === '/anonymous/onboarding' && req.method === 'POST') { account.onboardingCompleted = true; return send(); }
        if (path === '/anonymous/generation' && req.method === 'GET') return send(account.generation);
        if (path === '/anonymous/generation/cancel' && req.method === 'POST') { if (!account.generation) throw new Reject(404, '没有正在生成的简报。'); if (['queued', 'running'].includes(account.generation.status)) Object.assign(account.generation, { status: 'cancelled', remainingSeconds: null, updatedAt: iso() }); return send(account.generation); }
        if (path === '/anonymous/generation' && req.method === 'POST') {
          const data = await body(req);
          if (account.generation && ['queued', 'running'].includes(account.generation.status)) return send(account.generation); // coalesce duplicate submissions
          const today = account.generations.filter(t => new Date(t).toDateString() === new Date(now).toDateString());
          if (today.length >= db.policy.generationsPerDay || ip.generations.length >= db.policy.generationsPerDay) { account.rateLimitHits++; account.risk = 'watch'; event(account.id, 'generation_rejected', '达到匿名账户或网络的生成配额。'); throw new Reject(429, '今日生成次数已用完，请明天再试。', Math.ceil((new Date().setHours(24, 0, 0, 0) - now) / 1000)); }
          const concurrent = db.accounts.filter(x => x.ipKey === ipKey && (finish(x), x.generation && ['queued', 'running'].includes(x.generation.status))).length;
          if (concurrent >= db.policy.maxConcurrentGenerations) { event(account.id, 'generation_rejected', '同网络并发生成已达上限。'); throw new Reject(429, '已有简报正在生成，请稍后重试。', 12); }
          account.partial = data.partial === true; account.started = now; account.generations.push(now); ip.generations.push(now);
          account.generation = { id: `gen-${randomUUID()}`, status: 'running', percent: 0, remainingSeconds: 12, updatedAt: iso(), briefId: null, error: '' }; return send(account.generation);
        }
        throw new Reject(404, '接口不存在。');
      } catch (error) { const problem = error instanceof Reject ? error : new Reject(500, '演示服务暂时不可用。'); res.statusCode = problem.status; if (problem.retry) res.setHeader('Retry-After', problem.retry); save(); res.end(JSON.stringify({ message: problem.message })); }
    });
  } };
}
