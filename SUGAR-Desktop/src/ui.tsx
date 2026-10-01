import { useState, type KeyboardEvent, type ReactNode } from "react";

export function titleCase(value: string) {
  return value.replaceAll("_", " ").replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatTime(iso: string, withSeconds = false): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", ...(withSeconds ? { second: "2-digit" } : {}) });
}

export function relativeTime(iso: string): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 14) return `${days} d ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric" });
}

export function duration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  if (seconds < 90) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`;
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
}

export const LANGUAGE_NAMES: Record<string, string> = {
  en: "English", ar: "Arabic", fa: "Persian", tr: "Turkish", he: "Hebrew", ku: "Kurdish", ur: "Urdu", hi: "Hindi", bn: "Bengali",
  fr: "French", es: "Spanish", pt: "Portuguese", de: "German", it: "Italian", ru: "Russian", uk: "Ukrainian", pl: "Polish", zh: "Chinese",
  ja: "Japanese", ko: "Korean", id: "Indonesian", vi: "Vietnamese", th: "Thai", sw: "Swahili", und: "Unknown", auto: "Automatic",
};
export const languageName = (code: string) => LANGUAGE_NAMES[code] || code.toUpperCase();

export const PLATFORM_LABELS: Record<string, string> = { x: "X", bluesky: "Bluesky", mastodon: "Mastodon", bilibili: "Bilibili", weibo: "Weibo", wechat: "WeChat", wikipedia: "Wikipedia", gdelt: "News (GDELT)", openalex: "Scholarly (OpenAlex)", rss: "News & institution feeds" };
export const platformLabel = (id: string) => PLATFORM_LABELS[id] || titleCase(id);

export function Pill({ tone = "neutral", children, title }: { tone?: "neutral" | "ok" | "warn" | "error" | "info" | "busy"; children: ReactNode; title?: string }) {
  return <span className={`pill pill-${tone}`} title={title}>{children}</span>;
}

export const STATUS_TONE: Record<string, "neutral" | "ok" | "warn" | "error" | "info" | "busy"> = {
  draft: "neutral", ready: "info", running: "busy", paused: "warn", queued: "busy", cancelling: "warn", completed: "ok",
  completed_with_warnings: "warn", attention: "warn", failed: "error", cancelled: "neutral",
};

export function StatusPill({ status }: { status: string }) {
  const label = status === "completed_with_warnings" ? "Completed with warnings" : titleCase(status || "draft");
  return <Pill tone={STATUS_TONE[status] || "neutral"}>{label}</Pill>;
}

export function Spinner({ label }: { label?: string }) {
  return <span className="spinner" role="status" aria-label={label || "Working"} />;
}

export function EmptyState({ icon = "◌", title, children, action }: { icon?: string; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty-block">
      <span className="empty-block-icon" aria-hidden="true">{icon}</span>
      <strong>{title}</strong>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function Collapsible({ title, hint, defaultOpen = false, children, badge }: { title: string; hint?: string; defaultOpen?: boolean; children: ReactNode; badge?: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className={`collapsible ${open ? "open" : ""}`}>
      <button type="button" className="collapsible-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="collapsible-caret" aria-hidden="true">{open ? "▾" : "▸"}</span>
        <span><strong>{title}</strong>{hint && <small>{hint}</small>}</span>
        {badge}
      </button>
      {open && <div className="collapsible-body">{children}</div>}
    </section>
  );
}

/** A list of short text values (regions, languages, exclusions...) edited as removable chips. */
export function ChipInput({ label, values, onChange, placeholder, hint, suggestions }: {
  label: string; values: string[]; onChange: (next: string[]) => void; placeholder?: string; hint?: string; suggestions?: string[];
}) {
  const [draft, setDraft] = useState("");
  const listId = `chips-${label.replace(/\W+/g, "-").toLowerCase()}`;
  const add = () => {
    const value = draft.trim().replace(/,$/, "");
    if (value && !values.some((existing) => existing.toLowerCase() === value.toLowerCase())) onChange([...values, value]);
    setDraft("");
  };
  const onKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") { event.preventDefault(); add(); }
    else if (event.key === "Backspace" && !draft && values.length) onChange(values.slice(0, -1));
  };
  return (
    <div className="field-block chip-field">
      <span>{label}</span>
      <div className="chip-box">
        {values.map((value) => (
          <span className="chip" key={value}>{value}<button type="button" aria-label={`Remove ${value}`} onClick={() => onChange(values.filter((v) => v !== value))}>×</button></span>
        ))}
        <input value={draft} list={suggestions ? listId : undefined} onChange={(event) => setDraft(event.target.value)} onKeyDown={onKey} onBlur={add} placeholder={values.length ? "" : placeholder} aria-label={label} />
        {suggestions && <datalist id={listId}>{suggestions.map((s) => <option key={s} value={s} />)}</datalist>}
      </div>
      {hint && <small>{hint}</small>}
    </div>
  );
}

export function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: Array<{ value: T; label: string; hint?: string }>; onChange: (v: T) => void; label: string }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button type="button" key={option.value} role="radio" aria-checked={value === option.value} className={value === option.value ? "on" : ""} title={option.hint} onClick={() => onChange(option.value)}>{option.label}</button>
      ))}
    </div>
  );
}

export function CopyButton({ text, label = "Copy", className = "button button-quiet button-small" }: { text: string; label?: string; className?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button type="button" className={className} onClick={() => {
      void navigator.clipboard?.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1500); }).catch(() => undefined);
    }}>{done ? "Copied ✓" : label}</button>
  );
}

type IncompleteRun = { completeness?: { complete?: boolean; incomplete_sources?: string[]; notes?: string[]; sources?: Record<string, { status: string; error: Record<string, unknown> }> } };

/** Which sources could not be collected and why, one row each, with a retry where the caller supports it. */
export function IncompleteNotice({ run, onRetry, busy }: { run: IncompleteRun; onRetry?: (source: string) => void; busy?: boolean }) {
  const rows = run.completeness?.sources || {};
  const bad = run.completeness?.incomplete_sources || [];
  const extra = (run.completeness?.notes || []).filter((note) => !/ was (skipped|not fully collected):/.test(note));
  return (
    <div className="notice notice-warn incomplete-card" role="alert">
      <strong>Some sources could not be collected.</strong> Results cover only part of what you asked for.
      <ul className="incomplete-list">
        {bad.map((name) => {
          const row = rows[name];
          return (
            <li key={name}>
              <div><b>{platformLabel(name)}</b> <Pill tone={row?.status === "skipped" ? "neutral" : "warn"}>{row?.status === "skipped" ? "Skipped" : "Incomplete"}</Pill>
                <span className="muted">{String(row?.error?.message || "See the warnings for details.")}</span></div>
              {onRetry && <button className="button button-secondary button-small" disabled={busy} onClick={() => onRetry(name)}>Retry</button>}
            </li>);
        })}
      </ul>
      {extra.map((note) => <p key={note} className="muted">{note}</p>)}
    </div>
  );
}

export const VERDICTS: Array<{ id: "relevant" | "not_relevant" | "follow_up"; label: string; mark: string; tone: "ok" | "neutral" | "warn" }> = [
  { id: "relevant", label: "Relevant", mark: "✓", tone: "ok" },
  { id: "not_relevant", label: "Not relevant", mark: "✕", tone: "neutral" },
  { id: "follow_up", label: "Follow up", mark: "⚑", tone: "warn" },
];

export function VerdictPill({ verdict }: { verdict: string }) {
  const v = VERDICTS.find((entry) => entry.id === verdict);
  return v ? <Pill tone={v.tone} title={`Marked ${v.label.toLowerCase()}`}>{v.mark} {v.label}</Pill> : null;
}

export type Toast = { id: number; tone: "info" | "ok" | "warn"; text: string; action?: { label: string; run: () => void } };

/** Short, non-blocking confirmations ("Run finished — 14 items"). Polite live region; they dismiss themselves. */
export function ToastHost({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  return (
    <div className="toast-host" role="status" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast ${toast.tone}`}>
          <span>{toast.text}</span>
          {toast.action && <button className="toast-action" onClick={() => { toast.action?.run(); onDismiss(toast.id); }}>{toast.action.label}</button>}
          <button aria-label="Dismiss" onClick={() => onDismiss(toast.id)}>×</button>
        </div>))}
    </div>
  );
}
