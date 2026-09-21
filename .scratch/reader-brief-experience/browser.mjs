import { createServer } from 'vite';
import { resolve } from 'node:path';

let scenario = 'running', started = new Date().toISOString();
const news = { id: 'synthetic-news', title: '新工具让新闻整理更方便', summary: '这款工具可以把多篇报道整理成简短要点。读者能更快了解重点，也可以打开原文核对。', topic: 'AI 产品', source: '模拟新闻来源', sourceType: 'rss', publishedAt: '2026-09-21T02:00:00Z', fetchedAt: '2026-09-21T02:05:00Z', url: 'https://example.com/synthetic', snapshotId: 'synthetic' };
const brief = { id: 'synthetic-brief', title: '新工具简化新闻阅读', summary: '新闻工具正在帮助读者更快掌握重点。本期关注一款自动整理报道的产品。', date: '2026-09-21', version: 1, items: [news], generationStatus: 'partial', deliveryStatus: 'submitted', generatedAt: started };
const state = () => ({ id: 'synthetic-run', status: ['running', 'publishing', 'offline', 'slow'].includes(scenario) ? 'running' : scenario === 'empty' ? 'completed' : scenario,
  phase: scenario === 'publishing' ? 'publishing' : 'researching', phaseStartedAt: scenario === 'slow' ? new Date(Date.now() - 60000).toISOString() : started,
  updatedAt: started, percent: 95, remainingSeconds: 12, briefId: scenario === 'partial' ? brief.id : null, emptyResult: scenario === 'empty', error: scenario === 'failed' ? 'INTERNAL_SECRET_DIAGNOSTIC' : '' });
const server = await createServer({
  configFile: resolve('apps/user-web/vite.config.ts'), root: resolve('apps/user-web'),
  server: { port: 5183, host: '127.0.0.1', strictPort: true },
  plugins: [{ name: 'synthetic-browser-fixture',
    transformIndexHtml(html) { return html.replace('<body>', '<body><div style="padding:6px;text-align:center;background:#fff8e6;font:13px sans-serif">模拟验收环境 · 新闻与任务均为模拟</div>'); },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = new URL(req.url, 'http://127.0.0.1:5183');
        const send = (data, status = 200) => { res.statusCode = status; res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(data)); };
        if (url.pathname === '/__fixture') { scenario = url.searchParams.get('state') || 'running'; started = new Date().toISOString(); return send({ scenario }); }
        if (!url.pathname.startsWith('/api/')) return next();
        if (url.pathname.endsWith('/auth/session')) return send({ userId: 'synthetic-reader', name: '模拟读者', role: 'anonymous', onboardingCompleted: true });
        if (url.pathname.endsWith('/me/preferences')) return send({ version: 1, topics: ['AI 产品'], keywords: [], role: '' });
        if (url.pathname.endsWith('/me/briefs') && req.method === 'POST') { scenario = 'running'; return send(state()); }
        if (url.pathname.includes('/generations/')) {
          if (scenario === 'offline') return send({ error: { code: 'TEMPORARY', message: 'Synthetic connection failure' } }, 503);
          if (url.pathname.endsWith('/cancel')) scenario = 'cancelled';
          return send(state());
        }
        if (url.pathname.endsWith('/me/briefs')) return send({ items: [brief], nextCursor: null });
        if (url.pathname.includes('/me/briefs/')) return send(brief);
        return send({ error: { code: 'NOT_FOUND', message: 'Synthetic route missing' } }, 404);
      });
    },
  }],
});
await server.listen();
console.log('Synthetic reader fixture: http://127.0.0.1:5183');
