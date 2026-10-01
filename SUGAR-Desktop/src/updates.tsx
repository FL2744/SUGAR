import { useCallback, useEffect, useRef, useState } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { api, apiPost } from "./bridge";
import type { Prefs } from "./prefs";
import { Pill, Segmented, Spinner, relativeTime } from "./ui";

export type UpdateInfo = {
  current: string; channel: string; available: boolean; error: string; note?: string; latest?: string; tag?: string; name?: string; published_at?: string; url?: string; notes?: string;
  prerelease?: boolean; asset?: { name: string; size: number; url: string } | null; ahead?: { commits: number; headlines: string[] };
};
type Job = { state: "idle" | "downloading" | "done" | "error"; name?: string; received?: number; total?: number; error?: string; path?: string; verified?: boolean };

const mb = (n: number) => `${(n / 1048576).toFixed(n > 10485760 ? 0 : 1)} MB`;

/** Checks GitHub for a newer release when the app opens (if allowed) and drives the download. */
export function useUpdates(prefs: Prefs, ready: boolean) {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [checking, setChecking] = useState(false);
  const [job, setJob] = useState<Job>({ state: "idle" });
  const [message, setMessage] = useState("");
  const launched = useRef(false);

  const check = useCallback(async (force = false) => {
    setChecking(true);
    try { setInfo(await api<UpdateInfo>(`/api/update/check?channel=${prefs.updateChannel}${force ? "&force=1" : ""}`)); }
    catch (e) { setInfo({ current: "", channel: prefs.updateChannel, available: false, error: e instanceof Error ? e.message : String(e) }); }
    finally { setChecking(false); }
  }, [prefs.updateChannel]);

  useEffect(() => {
    if (!ready || launched.current || !prefs.autoUpdateCheck) return;
    launched.current = true;
    void check(false);
  }, [ready, prefs.autoUpdateCheck, check]);

  // Choosing another channel in Settings looks again right away, and never shows the old channel's answer meanwhile.
  const lastChannel = useRef(prefs.updateChannel);
  useEffect(() => {
    if (lastChannel.current === prefs.updateChannel) return;
    lastChannel.current = prefs.updateChannel;
    setInfo(null); setJob({ state: "idle" }); setMessage("");
    if (ready) void check(true);
  }, [prefs.updateChannel, ready, check]);

  useEffect(() => {
    if (job.state !== "downloading") return;
    const timer = window.setInterval(() => { void api<Job>("/api/update/status").then(setJob).catch(() => undefined); }, 700);
    return () => window.clearInterval(timer);
  }, [job.state]);

  const download = async () => {
    setMessage("");
    try { setJob(await apiPost<Job>("/api/update/download", { channel: prefs.updateChannel })); }
    catch (e) { setJob({ state: "error", error: e instanceof Error ? e.message : String(e) }); }
  };
  const open = async () => {
    try { setMessage((await apiPost<{ how: string }>("/api/update/open", {})).how); }
    catch (e) { setMessage(e instanceof Error ? e.message : String(e)); }
  };
  return { info, checking, check, job, download, open, message };
}
export type Updates = ReturnType<typeof useUpdates>;

function DownloadControls({ updates }: { updates: Updates }) {
  const { info, job } = updates;
  if (!info?.available) return null;
  if (!isTauri()) return <a className="button button-primary button-small" href={info.url} target="_blank" rel="noreferrer noopener">View release</a>;
  if (job.state === "downloading") return <span role="status"><Spinner /> Downloading {job.name} {job.total ? `${mb(job.received || 0)} of ${mb(job.total)}` : ""}</span>;
  if (job.state === "error") return <><span className="notice notice-warn" role="alert">{job.error || "The download failed."}</span><button className="button button-secondary button-small" onClick={() => void updates.download()}>Try again</button>{info.url && <a className="button button-quiet button-small" href={info.url} target="_blank" rel="noreferrer noopener">Open release page</a>}</>;
  if (job.state === "done") return <><Pill tone="ok">{job.verified ? "Downloaded and verified" : "Downloaded"}</Pill><button className="button button-primary button-small" onClick={() => void updates.open()}>Install update</button></>;
  return <button className="button button-primary button-small" onClick={() => void updates.download()} disabled={!info.asset}>{info.asset ? `Download ${info.asset.size ? `(${mb(info.asset.size)})` : "update"}` : "No download for this system"}</button>;
}

/** The one-line notice shown at the top of the app when a newer release exists. */
export function UpdateBanner({ updates, prefs, onSavePrefs, onOpenSettings }: { updates: Updates; prefs: Prefs; onSavePrefs: (p: Prefs) => void; onOpenSettings: () => void }) {
  const { info } = updates;
  if (!info?.available || info.latest === prefs.skippedVersion) return null;
  return (
    <div className="update-banner" role="status">
      <div>{info.channel === "latest"
        ? <><strong>A newer SUGAR build is available</strong> <span className="muted">{info.ahead?.commits ?? 0} change{info.ahead?.commits === 1 ? "" : "s"} since yours</span></>
        : <><strong>SUGAR {info.latest} is available</strong> <span className="muted">you have {info.current}{info.prerelease ? " · preview" : ""}</span></>}
        {updates.message && <p>{updates.message}</p>}</div>
      <div className="update-actions">
        <DownloadControls updates={updates} />
        <button className="button button-quiet button-small" onClick={onOpenSettings}>What’s new</button>
        <button className="button button-quiet button-small" onClick={() => onSavePrefs({ ...prefs, skippedVersion: info.latest || "" })}>Skip this version</button>
      </div>
    </div>
  );
}

/** Settings section: current version, release channel, launch check, and the release notes. */
export function UpdatesPanel({ updates, prefs, onSavePrefs }: { updates: Updates; prefs: Prefs; onSavePrefs: (p: Prefs) => void }) {
  const { info, checking } = updates;
  return (
    <div className="panel settings-panel">
      <div className="section-title"><div className="section-icon blue">↻</div><div><h3>Updates</h3><p>SUGAR looks at this project’s GitHub releases when it opens. Nothing is installed until you choose to.</p></div></div>
      <div className="settings-grid">
        <Segmented label="Release channel" value={prefs.updateChannel} onChange={(v) => onSavePrefs({ ...prefs, updateChannel: v })}
          options={[{ value: "latest", label: "Latest", hint: "Every change that passes the tests, automatically." }, { value: "stable", label: "Stable", hint: "Tested releases. Recommended." }, { value: "preview", label: "Preview", hint: "Release candidates, a little earlier." }, { value: "lts", label: "Long-term", hint: "Fixes only, for a fixed term." }]} />
        <label className="check-row"><input type="checkbox" checked={prefs.autoUpdateCheck} onChange={(e) => onSavePrefs({ ...prefs, autoUpdateCheck: e.target.checked })} /><span>Check for updates when SUGAR opens</span></label>
      </div>
      <div className="update-status">
        <button className="button button-secondary" onClick={() => void updates.check(true)} disabled={checking}>{checking ? "Checking…" : "Check now"}</button>
        {info && !info.error && <span role="status">{info.available ? (info.channel === "latest" ? <>A newer build is available. </> : <><strong>{info.latest}</strong> is available (you have {info.current}). </>) : <>{info.note || "You are up to date."} (version {info.current})</>}{info.published_at && info.available ? <small className="muted"> Published {relativeTime(info.published_at)}</small> : null}</span>}
        {info?.error && <span className="notice notice-warn" role="alert">{info.error}</span>}
        <DownloadControls updates={updates} />
      </div>
      {updates.message && <p className="notice notice-ok">{updates.message}</p>}
      {info?.error === "" && info.notes && info.available && <details open><summary>What’s in {info.latest}</summary><pre className="release-notes">{info.notes}</pre></details>}
      {info?.ahead && info.ahead.commits > 0 && (info.channel === "latest"
        ? <details open><summary>What changed ({info.ahead.commits})</summary><ul>{info.ahead.headlines.map((h, i) => <li key={i}>{h}</li>)}</ul></details>
        : <details><summary>{info.ahead.commits} change{info.ahead.commits === 1 ? "" : "s"} on the main branch since {info.tag}</summary>
          <ul>{info.ahead.headlines.map((h, i) => <li key={i}>{h}</li>)}</ul><p className="muted">These are in development and arrive in a later release.</p></details>)}
      {!isTauri() && <p className="muted">This is the browser version, so it updates when whoever runs the server updates it.</p>}
    </div>
  );
}
