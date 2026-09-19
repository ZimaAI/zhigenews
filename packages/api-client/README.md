# Shared API client

Generated DTOs and operation metadata come only from the accepted `v1.0.0/b003` backend handoff `h001/contracts/openapi.json`. Run `npm run generate:api` after deliberately selecting a new accepted contract in the generator; `npm run check:contract` detects drift. The generated header records the source SHA-256. TypeScript preserves field names, required/optional fields, nulls, enums and references; the server validates range, length and cross-field rules.

```ts
import { api, ApiError, type Preferences, type GenerationProgress } from '@zhigenews/api-client'

const preferences = await api<Preferences>('getPreferences')
// Keep this key for retries of this same intent; create another key for a new intent.
const idempotencyKey = crypto.randomUUID()
const generation = await api<GenerationProgress>('generateBrief', {
  body: { preferenceVersion: preferences.version },
  idempotencyKey,
})
```

The base is `import.meta.env.VITE_API_BASE_URL || '/api/v1'`. Requests include cookies; writes send the CSRF header. The client neither creates identities in local storage nor retries writes. `ApiError` exposes `status`, `code`, `message`, `retryAfter` (seconds or null), `fields` and `requestId`. Network errors and aborts retain their original errors. A 204 response resolves to `undefined`.

```ts
import { subscribeRunEvents } from '@zhigenews/api-client'

const stop = subscribeRunEvents(runId, {
  afterId: lastSeenId,
  onEvent: event => appendRunEvent(event), // RunEvent DTO, not an envelope
  onStatus: status => setConnectionStatus(status),
  onError: error => showConnectionError(error.message),
})
// Call on component unmount, route change, or when the consumer no longer needs events.
stop()
```

Connection statuses are `connecting`, `open`, `reconnecting`, `closed`. Read-only SSE reconnects using `Last-Event-ID` and discards replayed sequence IDs. Authentication/not-found errors close the subscription; a transport disconnect is not a task failure and creates no synthetic run event. The consumer owns the visible event list and task status.

`npm run test:api` exercises transport fixtures, request/error boundaries and fragmented/replayed streams. These synthetic unit tests do not establish live backend, model, Tavily or delivery acceptance.
