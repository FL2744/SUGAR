import { useCallback, useEffect, useRef, useState } from "react";
import { Channel, invoke, isTauri } from "@tauri-apps/api/core";
import { version } from "../package.json";
import { Icon, Modal } from "./ui";

const RELEASES_URL = "https://github.com/FL2744/SUGAR/releases/latest";
const CHECK_INTERVAL = 6 * 60 * 60 * 1000;
const RETRY_INTERVAL = 15 * 60 * 1000;
type Phase = "idle" | "checking" | "current" | "available" | "downloading" | "ready" | "installing";
type UpdateInfo = { version: string; currentVersion: string; notes: string };
type UpdateConfig = { configured: boolean; currentVersion: string };
type Progress = { downloaded: number; total: number | null };

function readPreference(key: string, fallback = ""): string {
  try { return localStorage.getItem(`sugar.updates.${key}`) ?? fallback; }
  catch { return fallback; }
}

function savePreference(key: string, value: string) {
  try { localStorage.setItem(`sugar.updates.${key}`, value); }
  catch { /* Updating still works when local preferences are unavailable. */ }
}

export function useUpdater(researchBusy: boolean) {
  const desktop = isTauri();
  const [config, setConfig] = useState<UpdateConfig | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [update, setUpdate] = useState<UpdateInfo | null>(null);
  const [progress, setProgress] = useState<Progress>({ downloaded: 0, total: null });
  const [error, setError] = useState("");
  const [lastChecked, setLastChecked] = useState("");
  const [automaticChecks, setAutomaticChecks] = useState(() => readPreference("automaticChecks", "true") !== "false");
  const [automaticDownloads, setAutomaticDownloads] = useState(() => readPreference("automaticDownloads") === "true");
  const [dismissedVersion, setDismissedVersion] = useState("");
  const [confirmInstall, setConfirmInstall] = useState(false);
  const operation = useRef(false);
  const lastAttempt = useRef(0);
  const busy = useRef(researchBusy);
  busy.current = researchBusy;
  const preferences = useRef({ automaticChecks, automaticDownloads });
  preferences.current = { automaticChecks, automaticDownloads };

  const initialize = useCallback(async () => {
    if (!desktop) return;
    setError("");
    try { setConfig(await invoke<UpdateConfig>("updater_status")); }
    catch (issue) { setError(`Could not initialize updates: ${String(issue)}`); }
  }, [desktop]);

  useEffect(() => { void initialize(); }, [initialize]);
  useEffect(() => { savePreference("automaticChecks", String(automaticChecks)); }, [automaticChecks]);
  useEffect(() => { savePreference("automaticDownloads", String(automaticDownloads)); }, [automaticDownloads]);

  const downloadPackage = useCallback(async () => {
    setPhase("downloading");
    setProgress({ downloaded: 0, total: null });
    const channel = new Channel<Progress>();
    channel.onmessage = setProgress;
    try {
      await invoke("download_update", { onProgress: channel });
      setPhase("ready");
    } catch (issue) {
      setPhase("available");
      setError(String(issue));
    }
  }, []);

  const check = useCallback(async () => {
    if (!config?.configured || operation.current) return;
    operation.current = true;
    lastAttempt.current = Date.now();
    setError("");
    setPhase("checking");
    try {
      const next = await invoke<UpdateInfo | null>("check_for_update");
      const checked = new Date().toISOString();
      savePreference(`lastCheck.${config.currentVersion}`, checked);
      setLastChecked(checked);
      setUpdate(next);
      setDismissedVersion("");
      setPhase(next ? "available" : "current");
      if (next && preferences.current.automaticChecks && preferences.current.automaticDownloads) await downloadPackage();
    } catch (issue) {
      setError(String(issue));
      setPhase("idle");
      setUpdate(null);
    } finally { operation.current = false; }
  }, [config, downloadPackage]);

  useEffect(() => {
    if (!config?.configured) return;
    const stored = readPreference(`lastCheck.${config.currentVersion}`);
    setLastChecked(Number.isFinite(Date.parse(stored)) ? stored : "");
  }, [config]);

  useEffect(() => {
    if (!config?.configured || !automaticChecks) return;
    const checkWhenDue = () => {
      if (!navigator.onLine || document.visibilityState !== "visible" || operation.current || update) return;
      const now = Date.now();
      const checked = Date.parse(readPreference(`lastCheck.${config.currentVersion}`));
      const age = now - checked;
      if (Number.isFinite(checked) && age >= 0 && age < CHECK_INTERVAL) return;
      if (now - lastAttempt.current < RETRY_INTERVAL) return;
      void check();
    };
    // Give startup diagnostics and project restoration time to settle.
    const startup = window.setTimeout(checkWhenDue, 2500);
    const interval = window.setInterval(checkWhenDue, 60_000);
    window.addEventListener("online", checkWhenDue);
    document.addEventListener("visibilitychange", checkWhenDue);
    return () => {
      clearTimeout(startup);
      clearInterval(interval);
      window.removeEventListener("online", checkWhenDue);
      document.removeEventListener("visibilitychange", checkWhenDue);
    };
  }, [automaticChecks, check, config, update]);

  const download = async () => {
    if (!update || operation.current) return;
    operation.current = true;
    setError("");
    try { await downloadPackage(); }
    finally { operation.current = false; }
  };

  const install = async () => {
    if (phase !== "ready" || operation.current || busy.current) return;
    operation.current = true;
    setConfirmInstall(false);
    setError("");
    setPhase("installing");
    try { await invoke("install_update"); }
    catch (issue) { setError(String(issue)); setPhase("ready"); }
    finally { operation.current = false; }
  };

  return {
    desktop, config, phase, update, progress, error, lastChecked,
    automaticChecks, setAutomaticChecks, automaticDownloads, setAutomaticDownloads,
    check, download, install, initialize, researchBusy, confirmInstall, setConfirmInstall,
    noticeVisible: Boolean(update && dismissedVersion !== update.version),
    dismiss: () => setDismissedVersion(update?.version || ""),
    installing: phase === "installing",
  };
}

type Updater = ReturnType<typeof useUpdater>;

function progressText({ downloaded, total }: Progress) {
  const megabytes = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return total ? `${megabytes(downloaded)} of ${megabytes(total)}` : `${megabytes(downloaded)} downloaded`;
}

export function UpdateNotice({ updater, onOpen }: { updater: Updater; onOpen: () => void }) {
  if (!updater.noticeVisible) return null;
  return <div className="update-notice" role="status"><Icon name="download" size={19} /><span><strong>SUGAR {updater.update?.version}</strong> {updater.phase === "ready" ? "is ready to install." : updater.phase === "downloading" ? "is downloading." : "is available."}</span><button className="button button-quiet" onClick={onOpen}>View update</button><button className="icon-button" onClick={updater.dismiss} aria-label="Dismiss update notice"><Icon name="close" size={16} /></button></div>;
}

export function UpdatePanel({ updater: u }: { updater: Updater }) {
  const working = ["checking", "downloading", "installing"].includes(u.phase);
  const status = u.phase === "checking" ? "Checking for updates…"
    : u.phase === "downloading" ? "Downloading and verifying…"
    : u.phase === "installing" ? "Installing update. SUGAR will restart…"
    : u.phase === "ready" ? `SUGAR ${u.update?.version} is ready to install`
    : u.update ? `SUGAR ${u.update.version} is available`
    : u.phase === "current" ? "You’re up to date"
    : "Keep your research workspace current";
  return <div className="panel update-panel" aria-labelledby="updates-title">
    <div className="section-title"><div className="section-icon green"><Icon name="download" /></div><div><h3 id="updates-title">Software updates</h3><p>SUGAR {u.config?.currentVersion || version} · Stable channel</p></div>{u.config?.configured && <span className="secure-badge"><Icon name="shield" size={14} /> Signed updates</span>}</div>
    {!u.desktop ? <div className="update-unavailable"><strong>Browser updates are managed by your host.</strong><p>Reload the page to use the deployed interface. The Python service and CLI are upgraded separately.</p><a href={RELEASES_URL} target="_blank" rel="noreferrer">View releases <span aria-hidden="true">↗</span></a></div>
      : !u.config?.configured ? <div className="update-unavailable"><strong>{u.config ? "Automatic updates aren’t enabled in this build." : "Connecting to the updater…"}</strong><p>Install an updater-enabled desktop release to receive verified updates here.</p><a href={RELEASES_URL} target="_blank" rel="noreferrer">View release downloads <span aria-hidden="true">↗</span></a>{!u.config && u.error && <button className="button button-secondary" onClick={() => void u.initialize()}>Retry updater connection</button>}</div>
      : <>
        <div className="update-status" role="status" aria-live="polite"><strong>{status}</strong>{u.lastChecked && <span>Last checked {new Date(u.lastChecked).toLocaleString()}</span>}</div>
        {u.phase === "downloading" && <div className="update-progress"><progress aria-label="Update download progress" value={u.progress.total ? Math.min(u.progress.downloaded, u.progress.total) : undefined} max={u.progress.total || 1} /><span>{progressText(u.progress)}</span></div>}
        {u.update?.notes && <details className="update-release-notes"><summary>What’s new in {u.update.version}</summary><p>{u.update.notes}</p></details>}
        <div className="update-actions">
          {u.phase !== "ready" && <button className="button button-secondary" onClick={() => void u.check()} disabled={working}><Icon name="refresh" size={17} />Check for updates</button>}
          {u.update && u.phase === "available" && <button className="button button-primary" onClick={() => void u.download()}><Icon name="download" size={17} />Download update</button>}
          {u.phase === "ready" && <button className="button button-primary" onClick={() => u.setConfirmInstall(true)} disabled={u.researchBusy}>Install and restart</button>}
          <a href={RELEASES_URL} target="_blank" rel="noreferrer">All release downloads <span aria-hidden="true">↗</span></a>
        </div>
        {u.phase === "ready" && <p className="update-help">{u.researchBusy ? "Wait for the active research operation to finish before installing." : "The download has been verified. Restart when you’re ready."}</p>}
        <div className="settings-divider" />
        <label className="update-preference"><input type="checkbox" checked={u.automaticChecks} onChange={(event) => u.setAutomaticChecks(event.target.checked)} /><span><strong>Check for updates automatically</strong><small>On startup and every six hours while SUGAR is open.</small></span></label>
        <label className="update-preference"><input type="checkbox" checked={u.automaticDownloads} disabled={!u.automaticChecks} onChange={(event) => u.setAutomaticDownloads(event.target.checked)} /><span><strong>Download updates automatically</strong><small>Downloads are verified. You choose when to install and restart.</small></span></label>
      </>}
    {u.error && <div className="update-error" role="alert"><Icon name="info" size={18} /><span>{u.error}</span></div>}
    <Modal open={u.confirmInstall} onClose={() => u.setConfirmInstall(false)} labelId="install-update-title" className="update-dialog"><Icon name="download" size={28} /><h2 id="install-update-title">Ready to restart SUGAR?</h2><p>Install version {u.update?.version} and reopen the app. Save any form edits before continuing. Your project files stay in their current folders.</p><div className="update-actions"><button data-dialog-focus className="button button-secondary" onClick={() => u.setConfirmInstall(false)}>Keep working</button><button className="button button-primary" onClick={() => void u.install()} disabled={u.researchBusy}>Install and restart now</button></div></Modal>
  </div>;
}
