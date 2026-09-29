import { invoke, isTauri } from "@tauri-apps/api/core";
import type { BackendEvent, BackendResult, SecretKey } from "./types";

export type Credentials = Partial<Record<SecretKey, string>>;
export type ApiWorkspace = { id: string; workspace: string; name: string; description?: string };

let apiBase = "";
let apiToken = "";

export function defaultApiUrl(): string {
  const configured = String(import.meta.env.VITE_SUGAR_API_URL || "").trim();
  if (configured) return configured.replace(/\/+$/, "");
  if (typeof window === "undefined") return "http://127.0.0.1:8765";
  const saved = window.localStorage.getItem("sugar.apiUrl");
  if (saved) return saved.replace(/\/+$/, "");
  const localHost = ["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname);
  if (localHost && ["1420", "4173", "5173"].includes(window.location.port)) return "http://127.0.0.1:8765";
  return window.location.origin.replace(/\/+$/, "");
}

export function configureApi(url: string, token: string): void {
  apiBase = url.trim().replace(/\/+$/, "");
  apiToken = token;
  if (typeof window !== "undefined") {
    if (apiBase) window.localStorage.setItem("sugar.apiUrl", apiBase);
    else window.localStorage.removeItem("sugar.apiUrl");
  }
}

function apiHeaders(extra: HeadersInit = {}): HeadersInit {
  return {
    ...extra,
    ...(apiToken ? { Authorization: `Bearer ${apiToken}` } : {}),
  };
}

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const base = apiBase || defaultApiUrl();
  if (!base) throw new Error("Set the SUGAR API address in Settings before connecting.");
  const endpoint = new URL(base, window.location.href);
  const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(endpoint.hostname);
  if (endpoint.protocol !== "https:" && !loopback) {
    throw new Error("Remote SUGAR API connections must use HTTPS. HTTP is allowed only for a local loopback service.");
  }
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, { ...init, headers: apiHeaders(init?.headers) });
  } catch (issue) {
    const detail = issue instanceof Error ? issue.message : String(issue);
    throw new Error(`Could not reach the SUGAR API at ${base}. Start the API server or check its address. (${detail})`);
  }
  const payload = await response.json().catch(() => ({})) as T & { error?: string };
  if (!response.ok) throw new Error(payload.error || `SUGAR API returned HTTP ${response.status}.`);
  return payload;
}

export async function listWorkspaces(): Promise<ApiWorkspace[]> {
  const result = await apiJson<{ workspaces: ApiWorkspace[] }>("/api/workspaces");
  return result.workspaces || [];
}

export async function createWorkspace(name: string, description = ""): Promise<ApiWorkspace> {
  return apiJson<ApiWorkspace>("/api/workspaces", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description }),
  });
}

export async function uploadWorkspaceFile(workspace: string, file: File): Promise<{ path: string; name: string }> {
  const parsed = new URL(workspace);
  if (parsed.protocol !== "sugar-workspace:") throw new Error("The selected browser project is not connected to a SUGAR API workspace.");
  const id = encodeURIComponent(parsed.hostname);
  const name = encodeURIComponent(file.name);
  return apiJson<{ path: string; name: string }>(`/api/workspaces/${id}/uploads/${name}`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: file,
  });
}

export async function downloadWorkspaceFile(reference: string, fileName?: string): Promise<void> {
  const parsed = new URL(reference);
  if (parsed.protocol !== "sugar-workspace:" && parsed.protocol !== "sugar-file:") throw new Error("The export does not belong to the connected SUGAR API workspace.");
  const segments = parsed.pathname.split("/").filter(Boolean).map(encodeURIComponent).join("/");
  const result = await fetch(`${apiBase || defaultApiUrl()}/api/workspaces/${encodeURIComponent(parsed.hostname)}/files/${segments}`, { headers: apiHeaders() });
  if (!result.ok) {
    const payload = await result.json().catch(() => ({})) as { error?: string };
    throw new Error(payload.error || `Could not download export (HTTP ${result.status}).`);
  }
  const blobUrl = URL.createObjectURL(await result.blob());
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = fileName || parsed.pathname.split("/").at(-1) || "sugar-export.zip";
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(blobUrl);
}

export async function runBackend(
  operation: string,
  config?: Record<string, unknown>,
  secrets?: Credentials,
): Promise<BackendResult> {
  let result: BackendResult;
  if (isTauri()) {
    result = await invoke<BackendResult>("run_backend", { operation, config, secrets });
  } else {
    result = await apiJson<BackendResult>("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operation, config, secrets }),
    });
  }
  const issue = result.events.find((event) => event.event === "error");
  if (result.code !== 0 || issue) {
    throw new Error(String(issue?.message ?? result.stderr ?? `Backend exited with code ${result.code}`));
  }
  return result;
}

export function latestEvent<T = unknown>(events: BackendEvent[], name: string): T | undefined {
  const event = [...events].reverse().find((item) => item.event === name);
  return event as T | undefined;
}

export function hubData<T = unknown>(events: BackendEvent[], action: string): T | undefined {
  const event = [...events].reverse().find(
    (item) => item.event === "workspace_hub_data" && item.action === action,
  );
  return event?.data as T | undefined;
}
