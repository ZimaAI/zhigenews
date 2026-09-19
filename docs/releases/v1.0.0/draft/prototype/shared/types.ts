export type Scenario = 'normal' | 'loading' | 'empty' | 'error' | 'partial' | 'unauthorized';
export type RunStatus = 'queued' | 'running' | 'completed' | 'partial' | 'failed' | 'cancelling' | 'cancelled';
export type DeliveryStatus = 'disabled' | 'pending' | 'submitted' | 'failed' | 'unknown';
export interface Preferences {
  version: number; role: string; topics: string[]; keywords: string[];
}
export interface DeliverySettings { time: string; }
export interface Citation { id: string; name: string; title: string; url: string; publishedAt: string | null; }
export interface NewsItem { id: string; title: string; summary: string; reason: string; topic: string; source: string; sourceType: string; publishedAt: string | null; url: string; citations: Citation[]; }
export interface Brief { id: string; title: string; date: string; version: number; summary: string; items: NewsItem[]; generationStatus: RunStatus; deliveryStatus: DeliveryStatus; generatedAt: string; runId: string; preferenceSnapshot: Preferences; }
export interface RunEvent { id: number; time: string; title: string; detail: string; status: string; duration: string; tool?: string; params?: string; output?: string; }
export interface Subtask { id: string; name: string; status: RunStatus; detail: string; }
export interface AgentRun { id: string; userName: string; status: RunStatus; model: string; configVersion: string; startedAt: string; elapsedSeconds: number; inputTokens: number; outputTokens: number; cost: number; searchCount: number; events: RunEvent[]; subtasks: Subtask[]; }
export interface Source { id: string; name: string; kind: 'rss' | 'newsnow'; sourceId: string; url: string; interval: number; upstreamInterval: number; status: 'healthy' | 'syncing' | 'failed' | 'disabled' | 'unverified'; lastSuccess: string; nextFetch: string; lastChanged: string; items: number; error: string; }
export interface ModelConfig { id: string; name: string; provider: string; modelId: string; endpoint: string; keyMasked: string; role: string; enabled: boolean; verified: boolean; contextWindow: number; }
export interface AgentConfig { id: string; name: string; version: string; status: 'published' | 'draft'; modelId: string; summaryModelId: string; maxModelCalls: number; maxToolCalls: number; maxSeconds: number; summaryTokens: number; summaryMessages: number; summaryRatio: number; subagentConcurrency: number; tools: string[]; systemPrompt: string; }
export interface EvalCase { id: string; name: string; preference: string; expected: string; }
export interface Evaluation { id: string; name: string; configVersion: string; status: string; relevance: number | null; faithfulness: number | null; citations: number | null; cost: number | null; latency: number | null; cases: number; createdAt: string; }
export interface DemoUser { id: string; name: string; email: string; role: string; status: string; topics: string[]; }
export interface Delivery { id: string; briefId: string; userName: string; destination: string; channel: string; status: DeliveryStatus; attempts: number; time: string; error: string; }
export interface GenerationProgress { id: string; status: RunStatus; percent: number | null; remainingSeconds: number | null; updatedAt: string; briefId: string | null; error: string; }
export interface DemoState {
  session: { kind: 'anonymous'; userId: string; name: string; onboardingCompleted: boolean } | null;
  generation: GenerationProgress | null; generationPreferences: Preferences | null;
  scenario: Scenario; loaded: boolean; authenticated: boolean; onboardingCompleted: boolean; preferences: Preferences; delivery: DeliverySettings;
  briefs: Brief[]; runs: AgentRun[]; sources: Source[]; models: ModelConfig[]; configs: AgentConfig[];
  evaluations: Evaluation[]; evalCases: EvalCase[]; users: DemoUser[]; deliveries: Delivery[];
}
