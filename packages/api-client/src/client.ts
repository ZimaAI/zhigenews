import { operationMetadata } from './generated.ts';
import type { OperationId, RunEvent } from './generated.ts';

export type ApiOptions = {
  path?: Record<string, string | number>;
  query?: Record<string, string | number | boolean | undefined | null>;
  body?: unknown;
  idempotencyKey?: string;
  signal?: AbortSignal;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryAfter: number | null;
  readonly fields?: Record<string, string>;
  readonly requestId?: string;

  constructor(status: number, code: string, message: string, details: {
    retryAfter?: number | null;
    fields?: Record<string, string>;
    requestId?: string;
  } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.retryAfter = details.retryAfter ?? null;
    this.fields = details.fields;
    this.requestId = details.requestId;
  }
}

export type RunEventConnectionStatus = 'connecting' | 'open' | 'reconnecting' | 'closed';
export type RunEventOptions = {
  afterId?: number;
  onEvent: (event: RunEvent) => void;
  onStatus: (status: RunEventConnectionStatus) => void;
  onError?: (error: ApiError | Error) => void;
};

export type ApiClientOptions = {
  baseUrl?: string;
  fetch?: typeof globalThis.fetch;
  /** Initial reconnect delay; bounded exponential retry applies only to the read-only SSE stream. */
  reconnectDelayMs?: number;
};

function endpoint(baseUrl: string, operationId: string, options: ApiOptions) {
  if (!Object.hasOwn(operationMetadata, operationId)) throw new TypeError(`未知接口操作：${operationId}`);
  const operation = operationMetadata[operationId as OperationId];
  const path = operation.path.replace(/\{([^}]+)\}/g, (_, name: string) => {
    const value = options.path?.[name];
    if (value === undefined || value === null || String(value) === '') throw new TypeError(`接口缺少路径参数：${name}`);
    return encodeURIComponent(String(value));
  });
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(options.query || {})) {
    if (value !== undefined && value !== null) query.set(key, String(value));
  }
  return { operation, url: `${baseUrl.replace(/\/$/, '')}${path}${query.size ? `?${query}` : ''}` };
}

function retryAfter(response: Response): number | null {
  const header = response.headers.get('Retry-After');
  if (!header) return null;
  if (/^\d+(\.\d+)?$/.test(header)) return Number(header);
  const date = Date.parse(header);
  return Number.isNaN(date) ? null : Math.max(0, Math.ceil((date - Date.now()) / 1000));
}

async function responseError(response: Response): Promise<ApiError> {
  let body: Record<string, unknown> = {};
  try {
    const parsed: unknown = await response.json();
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) body = parsed as Record<string, unknown>;
  } catch { /* A proxy may return HTML instead of the API Error schema. */ }
  const fields = body.fields && typeof body.fields === 'object' && !Array.isArray(body.fields)
    ? Object.fromEntries(Object.entries(body.fields).filter((entry): entry is [string, string] => typeof entry[1] === 'string'))
    : undefined;
  return new ApiError(response.status, typeof body.code === 'string' ? body.code : 'HTTP_ERROR',
    typeof body.message === 'string' ? body.message : `请求失败（${response.status}）`, {
      retryAfter: retryAfter(response), fields,
      requestId: typeof body.requestId === 'string' ? body.requestId : response.headers.get('X-Request-ID') || undefined,
    });
}

/** Incremental SSE framing; a chunk may end inside a UTF-8 character, CRLF or JSON line. */
class EventDecoder {
  private buffer = '';
  private data: string[] = [];
  private eventName = '';
  private id = '';
  private onMessage: (event: string, id: string, data: string) => void;
  private onRetry: (milliseconds: number) => void;

  constructor(onMessage: (event: string, id: string, data: string) => void, onRetry: (milliseconds: number) => void) {
    this.onMessage = onMessage;
    this.onRetry = onRetry;
  }

  feed(chunk: string) {
    this.buffer += chunk;
    while (true) {
      const end = this.buffer.search(/[\r\n]/);
      if (end < 0 || (this.buffer[end] === '\r' && end === this.buffer.length - 1)) return;
      const line = this.buffer.slice(0, end);
      const skip = this.buffer[end] === '\r' && this.buffer[end + 1] === '\n' ? 2 : 1;
      this.buffer = this.buffer.slice(end + skip);
      if (line === '') {
        if (this.data.length) this.onMessage(this.eventName, this.id, this.data.join('\n'));
        this.data = [];
        this.eventName = '';
        this.id = '';
        continue;
      }
      if (line.startsWith(':')) continue;
      const colon = line.indexOf(':');
      const field = colon < 0 ? line : line.slice(0, colon);
      let value = colon < 0 ? '' : line.slice(colon + 1);
      if (value.startsWith(' ')) value = value.slice(1);
      if (field === 'data') this.data.push(value);
      else if (field === 'event') this.eventName = value;
      else if (field === 'id' && !value.includes('\0')) this.id = value;
      else if (field === 'retry' && /^\d+$/.test(value)) this.onRetry(Number(value));
    }
  }
}

function waitForReconnect(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve();
    const finish = () => { clearTimeout(timer); signal.removeEventListener('abort', finish); resolve(); };
    const timer = setTimeout(finish, milliseconds);
    signal.addEventListener('abort', finish, { once: true });
  });
}

export function createApiClient(options: ApiClientOptions = {}) {
  const baseUrl = options.baseUrl || '/api/v1';
  const transport = options.fetch || ((input, init) => globalThis.fetch(input, init));

  async function api<T = unknown>(operationId: string, options: ApiOptions = {}): Promise<T> {
    const { operation, url } = endpoint(baseUrl, operationId, options);
    if (operation.stream) throw new TypeError('运行事件请使用 subscribeRunEvents');
    if (operation.idempotencyRequired && !options.idempotencyKey) throw new TypeError('请为此操作提供稳定的 idempotencyKey');
    const headers = new Headers({ Accept: 'application/json' });
    if (operation.method !== 'GET') headers.set('X-Zhige-Request', '1');
    if (options.body !== undefined) headers.set('Content-Type', 'application/json');
    if (options.idempotencyKey) headers.set('Idempotency-Key', options.idempotencyKey);
    const response = await transport(url, {
      method: operation.method, credentials: 'include', headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body), signal: options.signal,
    });
    if (!response.ok) throw await responseError(response);
    if (response.status === 204) return undefined as T;
    try { return await response.json() as T; }
    catch {
      throw new ApiError(response.status, 'INVALID_RESPONSE', '服务器返回了无法读取的数据', {
        requestId: response.headers.get('X-Request-ID') || undefined,
      });
    }
  }

  function subscribeRunEvents(runId: string, callbacks: RunEventOptions): () => void {
    const controller = new AbortController();
    let stopped = false;
    let lastId = callbacks.afterId ?? 0;
    let delay = options.reconnectDelayMs ?? 1000;
    let retries = 0;
    const { url } = endpoint(baseUrl, 'adminRunEvents', { path: { id: runId } });
    const stop = () => {
      if (stopped) return;
      stopped = true;
      controller.abort();
      callbacks.onStatus('closed');
    };
    const listen = async () => {
      callbacks.onStatus('connecting');
      while (!stopped) {
        let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
        try {
          const headers = new Headers({ Accept: 'text/event-stream' });
          if (lastId > 0) headers.set('Last-Event-ID', String(lastId));
          const response = await transport(url, { method: 'GET', credentials: 'include', headers, signal: controller.signal });
          if (stopped) break;
          if (!response.ok) throw await responseError(response);
          if (!response.body || !response.headers.get('Content-Type')?.includes('text/event-stream')) {
            throw new ApiError(response.status, 'INVALID_RESPONSE', '运行事件连接返回了无效响应');
          }
          callbacks.onStatus('open');
          reader = response.body.getReader();
          const text = new TextDecoder();
          const decoder = new EventDecoder((name, id, value) => {
            if (name && name !== 'run.event') return;
            const event = JSON.parse(value) as RunEvent;
            if (!Number.isSafeInteger(event.id) || event.id < 1 ||
                !['time', 'title', 'detail', 'status', 'duration'].every((key) => typeof event[key as keyof RunEvent] === 'string') ||
                (id && id !== String(event.id))) throw new Error('运行事件格式无效');
            if (event.id <= lastId || stopped) return;
            lastId = event.id;
            retries = 0;
            callbacks.onEvent(event);
          }, (milliseconds) => { delay = Math.min(30000, Math.max(250, milliseconds)); });
          while (!stopped) {
            const result = await reader.read();
            if (result.done) break;
            decoder.feed(text.decode(result.value, { stream: true }));
          }
          decoder.feed(text.decode());
          if (!stopped) throw new Error('运行事件连接已断开，正在重新连接');
        } catch (error) {
          if (stopped || controller.signal.aborted) break;
          const failure = error instanceof Error ? error : new Error('运行事件连接失败');
          callbacks.onError?.(failure);
          if (failure instanceof ApiError && [400, 401, 403, 404].includes(failure.status)) {
            stop();
            break;
          }
          callbacks.onStatus('reconnecting');
          const nextDelay = failure instanceof ApiError && failure.retryAfter !== null
            ? failure.retryAfter * 1000 : Math.min(10000, delay * 2 ** Math.min(retries++, 5));
          await waitForReconnect(nextDelay, controller.signal);
        } finally {
          if (reader) {
            await reader.cancel().catch(() => undefined);
            reader.releaseLock();
          }
        }
      }
    };
    void listen();
    return stop;
  }
  return { api, subscribeRunEvents };
}

const configuredBase = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env?.VITE_API_BASE_URL;
const client = createApiClient({ baseUrl: configuredBase || '/api/v1' });
export const api = client.api;
export const subscribeRunEvents = client.subscribeRunEvents;
