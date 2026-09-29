export type BackendEvent = {
  event?: string;
  message?: string;
  outputs?: string[];
  action?: string;
  data?: unknown;
  [key: string]: unknown;
};

export type BackendResult = {
  code: number;
  events: BackendEvent[];
  stdout: string;
  stderr: string;
};

export type Institution = {
  entity_id: string;
  name: string;
  entity_type?: string;
  network?: string;
  status?: string;
  city?: string;
  country?: string;
  latitude?: number | string | null;
  longitude?: number | string | null;
  description?: string;
  claims?: Array<Record<string, unknown>>;
  evidence_refs?: Array<{ source_url?: string; title?: string; citation?: string }>;
  source_evidence?: Array<{ source_url?: string; title?: string }>;
  public_links?: string[];
  [key: string]: unknown;
};

export type SecretKey =
  | "llm_api_key"
  | "x_bearer_token"
  | "bluesky_identifier"
  | "bluesky_app_password"
  | "mastodon_token"
  | "weibo_cookie";
