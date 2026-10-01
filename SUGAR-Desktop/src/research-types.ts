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
  limits: { query_count: number; max_posts_per_query: number; max_pages_per_query: number; max_items_total: number; llm_calls: number; per_source: Record<string, Record<string, number>> };
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
  review?: { verdict: string; tags: string[]; comments: number };
  relevance?: { score: number; band: "likely" | "uncertain" | "unlikely"; reasons: string[]; method: string } | null;
  // detail only
  project_id?: string; native_id?: string; query_dispatched?: string; transformations?: Array<Record<string, any>>;
  evidence_chain?: Array<{ id: string; type: string; parent: string; created_at: string; data: Record<string, any> }>;
  paragraphs?: Array<{ index: number; node_id: string; text: string }>; translations?: Array<Record<string, any>>; notes?: Array<Record<string, any>>;
  translation?: Record<string, any>; language_method?: string; warnings?: string[]; source_mode?: string;
  review_detail?: ReviewState;
};
export type Verdict = "" | "relevant" | "not_relevant" | "follow_up";
export type ReviewState = { verdict: Verdict; verdict_by: string; verdict_at: string; tags: string[]; comments: Array<{ id: string; author: string; text: string; at: string }> };
export type ReviewSummary = { verdicts: Record<string, number>; tags: Record<string, number>; commented: number; reviewed: number };
export type ResultsPayload = {
  total: number; all_items: number; group_by: string; groups: Array<{ key: string; count: number; items: ResultItem[] }>; items: ResultItem[];
  facets: Record<string, Array<{ key: string; count: number }>>; duplicates: number; rejected: number; excluded: number;
  review?: ReviewSummary;
  relevance_bands?: { likely: number; uncertain: number; unlikely: number; unscored: number };
};

export type TimelineEvent = { event_id: string; event_type: string; occurred_at: string; actor: string; details: Record<string, any> };

export type ProjectOverview = {
  summary: { project_id: string; name: string; research_question: string; status: string; last_activity: string; updated_at: string; run_count: number };
  requirement_text: string; plan: PlanSpec | null; plan_summary: SummaryRow[]; plan_versions: Array<{ version: number; updated_at: string }>;
  settings: { enabled_sources?: string[]; provider_profile_id?: string; debug?: boolean; rss_feeds?: string[]; web_seeds?: string[] };
  members: Array<{ name: string; role: string }>; runs: RunSummary[]; notes: Array<Record<string, any>>;
};

export type Confidence = { level: "high" | "medium" | "low"; reasons: string[]; sources: number; verified_fields: string[]; conflicts: string[] };
export type Institution = {
  entity_id: string; name: string; network: string; entity_type: string; status: string; status_date: string; country: string; region: string; city: string;
  latitude: number | null; longitude: number | null; placed: boolean; location_precision: string; aliases: string[]; programs: string[]; audiences: string[];
  delivery_modes: string[]; hosts: string[]; source_count: number; confidence: Confidence; conflicts: string[]; last_verified: string; last_evidence: string;
  activity: { items: number; recent_items: number }; updated_at: string;
};
export type ClaimView = { claim_id: string; value: unknown; review_state: string; reviewer: string; verified_at: string; note: string; observed_at: string; evidence: Array<Record<string, any>> };
export type InstitutionDetail = Institution & {
  fields: Record<string, { value: unknown; state: string; claims: ClaimView[] }>; links: Array<Record<string, any>>; lifecycle: Array<Record<string, any>>;
  relationships: Array<Record<string, any>>; evidence: Array<Record<string, any>>; description: string;
};
export type InstitutionList = { institutions: Institution[]; total: number; unplaced: number; facets: Record<string, Array<{ key: string; count: number }>> };
export type InstitutionCandidate = {
  name: string; mentions: number; item_ids: string[]; evidence: Array<{ item_id: string; quote: string; url: string }>; method: string; country: string; city?: string;
  status_hint: string; already_recorded: boolean; entity_type_hint?: string;
};

export type NetworkRow = { name: string; role: "subject" | "reference"; label: string; color: string; institutions: number; placed: number };
export type NetworkPreview = { file_id: string; filename: string; suggested_mapping: Record<string, string>; columns?: string[]; row_count: number; valid_rows: number; error_count: number; errors: string[]; sample: Array<Record<string, unknown>> };
export type SeedRow = { seed_source: string; seed_id: string; name: string; description: string; aliases: string[]; country: string; city?: string; latitude: number | null; longitude: number | null; opened_date: string; closed_date: string; status: string; website: string; source_url: string };
export type OverlapRow = {
  entity_id: string; name: string; country: string; city: string;
  nearest_reference: { entity_id: string; name: string; city: string; country: string; distance_km: number; band: string; same_city: boolean } | null;
  references_within_km: Record<string, number>; shared_audiences: string[]; shared_programs: string[];
};
export type OverlapResult = {
  rows: OverlapRow[]; by_country: Array<{ country: string; subjects: number; references: number; subjects_near_reference: number; shared_audience_pairs: number }>;
  counts: { subject_institutions: number; reference_institutions: number; subjects_not_placed: number; references_not_placed: number }; method: string; near_km: number; bands_km: number[];
};

export type CodeRow = { field: "audience" | "program" | "activity_type" | "attendance"; label: string; quote: string; methods: string[]; status: "proposed" | "confirmed" | "rejected"; decided_by: string; decided_at: string };
export type CodingSummary = { proposed: Record<string, Record<string, number>>; confirmed: Record<string, Record<string, number>>; items_coded: number };

export type Monitor = { id: string; name: string; cadence_hours: number; enabled: boolean; note: string; created_at: string; last_run_at: string; last_run_id: string; last_status: string; next_due_at: string };
export type DigestChange = { entity_id: string; name: string; kind: string; detail: string };
export type Digest = {
  id: string; at: string; run_id: string; monitor_id: string; trigger: string; first_pass: boolean; run_status: string; summary: string;
  counts: { new_items: number; changed_items: number; institution_changes: number; institutions: number; incomplete_sources: number };
  new_items: Array<{ item_id: string; platform: string; url: string; text: string }>; changed_items: Array<{ item_id: string; platform: string; url: string; text: string }>;
  institution_changes: DigestChange[]; incomplete_sources: string[];
};

export type ThemeRow = { label: string; key: string; count: number; share: number; also: string[]; platforms: Record<string, number>; languages: Record<string, number>; examples: Array<{ item_id: string; url: string; text: string }> };
export type BriefResult = { markdown: string; title: string; references: string[]; model_summary: boolean; warnings: string[]; files: { markdown: string; docx: string } };

export type Prf = { precision: number | null; recall: number | null; f1: number | null; tp: number; fp: number; fn: number };
export type AccuracyReport = {
  labeled_relevance: number; labeled_coding: number; unknown_item_ids: number; note: string;
  relevance: Prf & { threshold: number; true_negatives: number; by_threshold: Record<string, Prf> };
  audience: { overall: Prf; by_label: Record<string, Prf> }; program: { overall: Prf; by_label: Record<string, Prf> };
};

export type PostPin = {
  item_id: string; run_id: string; author: string; published_at: string; platform: string; url: string; language: string;
  original_text: string; translated_text: string;
  origin: { latitude: number; longitude: number; kind: string; precision: string; label: string } | null;
  targets: Array<{ name: string; latitude: number; longitude: number; confidence: number; method: string; precision: string; city?: string }>;
  inferred_location: { name: string; confidence: number; method: string } | null;
  placement: "origin" | "mentioned"; latitude: number | null; longitude: number | null;
  verified: boolean; verdict: string; verified_by: string; verified_at: string;
};
export type PostMap = {
  pins: PostPin[]; targets: Array<{ name: string; posts: number; last_24h: number; verified: number; last_at: string; item_ids: string[]; platforms: Record<string, number>; languages: Record<string, number>; cities: Record<string, number>; latitude: number; longitude: number }>;
  flows: Array<{ from: [number, number]; to: [number, number]; target: string; posts: number }>; note: string;
};
