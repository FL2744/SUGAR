export type QuerySpec = {
  id: string; text: string; platform: string; language: string; geography: string;
  origin: string; enabled: boolean; rationale: string;
};

export type PlanSpec = {
  plan_id: string; version: number; schema_version: string;
  research_question: string; topic: string; geography: string[]; actors: string[];
  timeframe: { start: string; end: string; label: string };
  languages: string[]; source_scope: "all_enabled" | "selected"; source_categories: string[];
  platforms: string[]; exclude_platforms: string[]; search_terms: string[]; queries: QuerySpec[];
  exclusions: string[]; collection_mode: string; depth: "quick" | "standard" | "deep";
  limits: { query_count: number; max_posts_per_query: number; max_pages_per_query: number; max_items_total: number; per_source: Record<string, Record<string, number>> };
  translation: { policy: "auto" | "always" | "never"; target_language: string; translate_queries: boolean; max_chars_per_item: number; workers: number };
  dedup: { enabled: boolean; threshold: number };
  analysis_goals: string[];
  provider: { profile_id: string; model: string; use_for_planning: boolean };
  refresh: { mode: string; interval_hours: number; watch_queries: string[]; watch_sources: string[]; change_detection: boolean; notify_on_new: boolean };
  concurrency: { max_workers: number; per_source_delay_seconds: number };
  retry: { max_attempts: number; base_backoff_seconds: number };
  extraction: { min_chars: number; fetch_full_text: boolean; paragraph_split: boolean };
  interpretation: Record<string, unknown>;
  extra: Record<string, unknown>;
  created_at: string; updated_at: string;
};

export type SummaryRow = { label: string; value: string };
export type PlanIssue = { field: string; message: string; severity: "warning" | "error"; repaired: boolean };

export type Interpretation = {
  request: string; method: "llm" | "deterministic" | "manual"; plan: PlanSpec | null; summary: SummaryRow[];
  assumptions: string[]; defaulted_fields: string[]; clarifications: string[]; issues: PlanIssue[];
  attempts: Array<{ number: number; method: string; ok: boolean; error: string; ms: number; repaired: string[] }>;
  needs_manual_entry: boolean; fallback_reason: string; confidence: number;
  provider: { id?: string; type?: string; name?: string; model?: string }; total_ms: number; provider_configured?: boolean;
  defaults: Record<string, string>; operation?: string; warnings?: string[]; note?: string;
};

export type ActivityEvent = {
  seq: number; run_id: string; type: string; stage: string; ts: string; severity: "info" | "warning" | "error";
  source: string; message: string; data: Record<string, any>; lag_ms?: number;
};

export type StageState = { state: "pending" | "running" | "done" | "skipped" | "failed"; started_at?: string; finished_at?: string; [k: string]: unknown };
export type SourceRow = { status: string; items: number; queries_run: number; queries_failed: number; error: Record<string, any> };

export type RunSummary = {
  run_id: string; kind: "run" | "rerun" | "refresh_sources" | "reprocess"; parent_run_id: string; status: string; stage: string;
  requirement: string; topic: string; counts: Record<string, number>; created_at: string; started_at: string; finished_at: string;
  plan_id: string; plan_version: number; plan_fingerprint: string;
  completeness?: { complete?: boolean; incomplete_sources?: string[]; summary?: string; notes?: string[]; sources?: Record<string, SourceRow> };
  error_count: number; warning_count: number; debug: boolean;
  stage_states?: Record<string, StageState>; sources?: Record<string, SourceRow>; paused?: boolean; last_seq?: number; live?: boolean;
  plan?: PlanSpec; errors?: Array<Record<string, any>>; warnings?: string[]; generated_searches?: QuerySpec[];
  provider_ref?: Record<string, string>; metrics?: Record<string, any>;
  timings?: { categories: Record<string, { count: number; total_ms: number; max_ms: number; avg_ms: number }>; by_source: Record<string, unknown> };
};

export type ProviderType = {
  id: string; label: string; credential_label: string; needs_credential: boolean; needs_endpoint: boolean;
  default_endpoint: string; default_model: string; help: string; supports_organization: boolean;
};
export type ProviderProfileRow = {
  id: string; name: string; type: string; endpoint: string; model: string; organization: string; project: string;
  credential_ref: string; advanced: Record<string, unknown>;
  status: { state: "untested" | "ok" | "failed"; checked_at: string; message: string; stage: string };
  has_credential: boolean; credential_source: string; credential_label: string; effective_endpoint: string; effective_model: string;
};
export type ConnectionCheck = { name: string; status: "ok" | "failed" | "skipped"; message: string; ms: number };
export type ConnectionReport = {
  ok: boolean; provider_type: string; endpoint: string; model: string; checks: ConnectionCheck[];
  error_stage: string; message: string; available_models: string[]; total_ms: number;
};
export type PlatformRow = {
  id: string; label: string; keyword_search: boolean; description: string; requires: string[]; missing: string[];
  state: "ready" | "needs_credential" | "unsupported";
  secrets: Array<{ key: string; label: string; required: boolean; configured: boolean; source: string }>;
};

export type ResultItem = {
  item_id: string; platform: string; url: string; author: string; published_at: string; retrieved_at: string; language: string;
  status: string; rejection_reason: string; duplicate_of: string; similarity: number; query: string; queries: string[];
  original_text: string; translated_text: string; translation_status: string; translation_provider: string; translation_model: string;
  translation_at: string; geography: string[]; coordinates: Record<string, number>; is_new: boolean; known_from_run: string; run_id: string;
  derived_from: Record<string, string>; engagement: Record<string, unknown>; content_type: string;
  // detail only
  project_id?: string; native_id?: string; query_dispatched?: string; transformations?: Array<Record<string, any>>;
  evidence_chain?: Array<{ id: string; type: string; parent: string; created_at: string; data: Record<string, any> }>;
  paragraphs?: Array<{ index: number; node_id: string; text: string }>; translations?: Array<Record<string, any>>; notes?: Array<Record<string, any>>;
  translation?: Record<string, any>; language_method?: string; warnings?: string[]; source_mode?: string;
};
export type ResultsPayload = {
  total: number; all_items: number; group_by: string; groups: Array<{ key: string; count: number; items: ResultItem[] }>; items: ResultItem[];
  facets: Record<string, Array<{ key: string; count: number }>>; duplicates: number; rejected: number; excluded: number;
};

export type TimelineEvent = { event_id: string; event_type: string; occurred_at: string; actor: string; details: Record<string, any> };

export type ProjectOverview = {
  summary: { project_id: string; name: string; research_question: string; status: string; last_activity: string; updated_at: string; run_count: number };
  requirement_text: string; plan: PlanSpec | null; plan_summary: SummaryRow[]; plan_versions: Array<{ version: number; updated_at: string }>;
  settings: { enabled_sources?: string[]; provider_profile_id?: string; debug?: boolean };
  members: Array<{ name: string; role: string }>; runs: RunSummary[]; notes: Array<Record<string, any>>;
};
