import { useCallback, useEffect, useMemo, useState } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { research } from "./research-api";
import type { ConnectionReport, PlatformRow, ProviderProfileRow, ProviderType } from "./research-types";
import { applyPrefs, DEFAULT_PREFS, type Prefs } from "./prefs";
import { Collapsible, CopyButton, Pill, Segmented, Spinner, formatTime } from "./ui";

type Section = "providers" | "platforms" | "interface" | "connection" | "privacy";
type ProfileDraft = ProviderProfileRow & { isNew?: boolean; secret?: string; removeSecret?: boolean; replacing?: boolean };

const BLANK_TYPE = "openai";

function stageHint(stage: string): string {
  return ({ reachable: "Check the address and your network.", credential: "Re-enter the key for this provider.", model: "Choose a model this credential can use.", rate_limit: "Wait a moment and test again.", inference: "The provider answered with an error." } as Record<string, string>)[stage] || "";
}

function ConnectionResult({ report }: { report: ConnectionReport }) {
  return (
    <div className={`test-result ${report.ok ? "ok" : "failed"}`} role="status">
      <strong>{report.ok ? `Connected — ${report.total_ms.toFixed(0)} ms` : "Connection failed"}</strong>
      <ol>{report.checks.map((check) => (
        <li key={check.name} className={`check-${check.status}`}><span aria-hidden="true">{check.status === "ok" ? "✓" : check.status === "failed" ? "✕" : "–"}</span><div><b>{{ reachable: "Provider reachable", credential: "Credential accepted", model: "Model available", inference: "Test request works" }[check.name] || check.name}</b><small>{check.message}</small></div></li>))}</ol>
      {!report.ok && report.message && <p className="test-message">{report.message} {stageHint(report.error_stage)}</p>}
    </div>
  );
}

export function SettingsPage({ prefs, onSavePrefs, onDirtyChange, engineState, apiUrl, apiToken, onApiUrl, onApiToken, onConnect, busy, onError }: {
  prefs: Prefs; onSavePrefs: (prefs: Prefs) => boolean; onDirtyChange: (dirty: boolean) => void; engineState: string;
  apiUrl: string; apiToken: string; onApiUrl: (value: string) => void; onApiToken: (value: string) => void; onConnect: () => void; busy: boolean; onError: (message: string) => void;
}) {
  const [section, setSection] = useState<Section>("providers");
  const [types, setTypes] = useState<ProviderType[]>([]);
  const [saved, setSaved] = useState<ProviderProfileRow[]>([]);
  const [profiles, setProfiles] = useState<ProfileDraft[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [defaultId, setDefaultId] = useState("");
  const [savedDefault, setSavedDefault] = useState("");
  const [storage, setStorage] = useState("");
  const [platforms, setPlatforms] = useState<PlatformRow[]>([]);
  const [platformSecrets, setPlatformSecrets] = useState<Record<string, string>>({});
  const [platformClear, setPlatformClear] = useState<Set<string>>(new Set());
  const [platformReplacing, setPlatformReplacing] = useState<Set<string>>(new Set());
  const [draftPrefs, setDraftPrefs] = useState<Prefs>(prefs);
  const [reports, setReports] = useState<Record<string, ConnectionReport>>({});
  const [testing, setTesting] = useState("");
  const [state, setState] = useState<{ kind: "idle" | "saving" | "saved" | "error"; at?: string; message?: string }>({ kind: "idle" });
  const [loaded, setLoaded] = useState(false);
  const [diagnostic, setDiagnostic] = useState("");

  const load = useCallback(async () => {
    try {
      const [providerData, platformData] = await Promise.all([research.providers(), research.platforms()]);
      setTypes(providerData.types); setSaved(providerData.profiles); setProfiles(providerData.profiles.map((p) => ({ ...p })));
      setDefaultId(providerData.default_profile_id); setSavedDefault(providerData.default_profile_id); setStorage(providerData.credential_storage);
      setSelectedId((current) => (providerData.profiles.some((p) => p.id === current) ? current : providerData.profiles[0]?.id || ""));
      setPlatforms(platformData); setPlatformSecrets({}); setPlatformClear(new Set()); setPlatformReplacing(new Set()); setLoaded(true);
    } catch (issue) { setLoaded(true); onError(issue instanceof Error ? issue.message : String(issue)); }
  }, [onError]);
  useEffect(() => { void load(); }, [load, engineState]);

  // Interface changes preview live but are not persisted until Save; leaving the page restores the saved look.
  useEffect(() => { applyPrefs(draftPrefs); }, [draftPrefs]);
  useEffect(() => () => applyPrefs(prefs), [prefs]);

  const prefsDirty = JSON.stringify(draftPrefs) !== JSON.stringify(prefs);
  const providerChanges = useMemo(() => {
    let count = 0;
    const savedById = new Map(saved.map((p) => [p.id, p]));
    for (const p of profiles) {
      const original = savedById.get(p.id);
      if (p.isNew || p.secret || p.removeSecret) count += 1;
      else if (original && (["name", "type", "endpoint", "model", "organization", "project"] as const).some((k) => p[k] !== original[k]) || JSON.stringify(original?.advanced) !== JSON.stringify(p.advanced)) count += 1;
    }
    count += saved.filter((p) => !profiles.some((x) => x.id === p.id)).length;
    if (defaultId !== savedDefault) count += 1;
    return count;
  }, [profiles, saved, defaultId, savedDefault]);
  const platformChanges = Object.values(platformSecrets).filter((v) => v.trim()).length + platformClear.size;
  const changeCount = providerChanges + platformChanges + (prefsDirty ? 1 : 0);
  const dirty = changeCount > 0;
  useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => {
    if (!dirty) return;
    const guard = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);

  const selected = profiles.find((p) => p.id === selectedId) || null;
  const selectedType = types.find((t) => t.id === selected?.type);
  const patchProfile = (id: string, changes: Partial<ProfileDraft>) => setProfiles((rows) => rows.map((p) => (p.id === id ? { ...p, ...changes } : p)));

  const addProfile = () => {
    const type = types.find((t) => t.id === BLANK_TYPE) || types[0];
    if (!type) return;
    const id = `prov_${Math.random().toString(36).slice(2, 12)}`;
    const draft: ProfileDraft = {
      id, name: type.label, type: type.id, endpoint: "", model: type.default_model, organization: "", project: "", credential_ref: type.needs_credential ? `provider:${id}` : "", advanced: {},
      status: { state: "untested", checked_at: "", message: "", stage: "" }, has_credential: false, credential_source: "", credential_label: type.credential_label,
      effective_endpoint: type.default_endpoint, effective_model: type.default_model, isNew: true,
    };
    setProfiles((rows) => [...rows, draft]); setSelectedId(id); if (!defaultId) setDefaultId(id);
  };
  const changeType = (id: string, typeId: string) => {
    const type = types.find((t) => t.id === typeId);
    if (type) patchProfile(id, { type: typeId, name: type.label, model: type.default_model, endpoint: "", credential_label: type.credential_label, credential_ref: type.needs_credential ? `provider:${id}` : "", organization: "", project: "" });
  };
  const removeProfile = (id: string) => {
    if (!window.confirm("Remove this provider and its saved credential?")) return;
    setProfiles((rows) => rows.filter((p) => p.id !== id));
    setSelectedId((current) => (current === id ? profiles.find((p) => p.id !== id)?.id || "" : current));
    if (defaultId === id) setDefaultId(profiles.find((p) => p.id !== id)?.id || "");
  };

  const test = async (profile: ProfileDraft) => {
    setTesting(profile.id);
    try {
      const payload = { id: profile.isNew ? undefined : profile.id, name: profile.name, type: profile.type, endpoint: profile.endpoint, model: profile.model, organization: profile.organization, project: profile.project, advanced: profile.advanced };
      const report = await research.testDraftProvider({ ...payload, ...(profile.isNew ? { id: profile.id } : {}) }, profile.secret || "");
      setReports((current) => ({ ...current, [profile.id]: report }));
      if (report.available_models.length && !profile.model) patchProfile(profile.id, { model: report.available_models[0] });
    } catch (issue) {
      setReports((current) => ({ ...current, [profile.id]: { ok: false, provider_type: profile.type, endpoint: "", model: profile.model, checks: [], error_stage: "config", message: issue instanceof Error ? issue.message : String(issue), available_models: [], total_ms: 0 } }));
    } finally { setTesting(""); }
  };

  const save = async () => {
    setState({ kind: "saving" });
    try {
      for (const original of saved) if (!profiles.some((p) => p.id === original.id)) await research.deleteProvider(original.id);
      for (const p of profiles) {
        const original = saved.find((s) => s.id === p.id);
        const body = { id: p.id, name: p.name, type: p.type, endpoint: p.endpoint, model: p.model, organization: p.organization, project: p.project, advanced: p.advanced };
        const changed = p.isNew || p.secret || p.removeSecret || !original || (["name", "type", "endpoint", "model", "organization", "project"] as const).some((k) => p[k] !== original[k]) || JSON.stringify(original.advanced) !== JSON.stringify(p.advanced);
        if (changed) await research.saveProvider(body, p.removeSecret ? "" : p.secret ? p.secret : null, p.id === defaultId);
      }
      if (defaultId && defaultId !== savedDefault && profiles.some((p) => p.id === defaultId)) await research.setDefaultProvider(defaultId);
      for (const [key, value] of Object.entries(platformSecrets)) if (value.trim()) await research.setPlatformCredential(key, value.trim());
      for (const key of platformClear) await research.setPlatformCredential(key, "");
      const persisted = onSavePrefs(draftPrefs);
      await load();
      setState(persisted ? { kind: "saved", at: new Date().toISOString() } : { kind: "error", message: "Settings were applied but this browser would not store the interface preferences." });
    } catch (issue) {
      setState({ kind: "error", message: issue instanceof Error ? issue.message : String(issue) });
    }
  };
  const revert = () => { setDraftPrefs(prefs); setPlatformSecrets({}); setPlatformClear(new Set()); setPlatformReplacing(new Set()); setReports({}); setState({ kind: "idle" }); void load(); };

  const sections: Array<[Section, string, number]> = [["providers", "LLM providers", providerChanges], ["platforms", "Platform credentials", platformChanges], ["interface", "Interface", prefsDirty ? 1 : 0],
    ...(!isTauri() ? [["connection", "Connection", 0] as [Section, string, number]] : []), ["privacy", "Privacy & diagnostics", 0]];
  const modelOptions = selected ? (reports[selected.id]?.available_models || []) : [];

  return (
    <section className="page-content settings-page">
      <div className="page-heading compact-heading"><div><div className="eyebrow">SETTINGS <span className="eyebrow-line" /></div><h1>Settings</h1>
        <p>Changes apply when you press <strong>Save changes</strong>. Nothing is saved automatically.</p></div>
        <Pill tone={engineState === "ready" ? "ok" : "warn"}>{engineState === "ready" ? "Engine connected" : "Engine not connected"}</Pill></div>

      <div className="settings-shell">
        <nav className="settings-nav" aria-label="Settings sections">
          {sections.map(([id, label, changes]) => <button key={id} className={section === id ? "on" : ""} aria-current={section === id} onClick={() => setSection(id)}>{label}{changes > 0 && <span className="dirty-dot" title="Unsaved changes" />}</button>)}
        </nav>

        <div className="settings-body">
          {section === "providers" && (
            <div className="panel settings-panel">
              <div className="section-title"><div className="section-icon amber">⌘</div><div><h3>LLM providers</h3><p>Used to interpret requests, suggest searches, and translate. Each provider has its own credential and model.</p></div></div>
              {!loaded && <div className="loading-block"><Spinner /> Loading…</div>}
              {loaded && engineState !== "ready" && profiles.length === 0 && <div className="notice notice-warn">The research engine is not connected, so providers cannot be loaded. Check the Connection section.</div>}
              <div className="provider-layout">
                <ul className="provider-list" aria-label="Configured providers">
                  {profiles.map((p) => (
                    <li key={p.id}><button className={p.id === selectedId ? "on" : ""} onClick={() => setSelectedId(p.id)}>
                      <strong>{p.name}</strong><small>{types.find((t) => t.id === p.type)?.label} · {p.model || "no model"}</small>
                      <span className="provider-badges">{p.id === defaultId && <Pill tone="info">Default</Pill>}
                        <Pill tone={reports[p.id] ? (reports[p.id].ok ? "ok" : "error") : p.status.state === "ok" ? "ok" : p.status.state === "failed" ? "error" : "neutral"}>{reports[p.id] ? (reports[p.id].ok ? "Connected" : "Failed") : p.status.state === "ok" ? "Connected" : p.status.state === "failed" ? "Failed" : "Not tested"}</Pill></span></button></li>))}
                  <li><button className="add-provider" onClick={addProfile}>＋ Add provider</button></li>
                </ul>

                {selected && selectedType ? (
                  <div className="provider-editor">
                    <ol className="hierarchy">
                      <li className="hier-step"><span className="hier-n">1</span><div className="hier-body"><h4>Provider</h4>
                        <label className="field-block"><span>Type</span><select value={selected.type} disabled={!selected.isNew} onChange={(event) => changeType(selected.id, event.target.value)}>{types.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</select><small>{selectedType.help}</small></label>
                        <label className="field-block"><span>Name</span><input value={selected.name} onChange={(event) => patchProfile(selected.id, { name: event.target.value })} /></label>
                        {selectedType.needs_endpoint && <label className="field-block"><span>Endpoint (base URL)</span><input value={selected.endpoint} placeholder={selectedType.default_endpoint || "https://api.example.com/v1"} onChange={(event) => patchProfile(selected.id, { endpoint: event.target.value })} /></label>}</div></li>
                      <li className="hier-step"><span className="hier-n">2</span><div className="hier-body"><h4>Credential</h4>
                        {!selectedType.needs_credential ? <p className="muted">This provider type does not use a credential.</p> : (
                          <div className="field-block"><span>{selectedType.credential_label}</span>
                            {selected.has_credential && !selected.replacing && !selected.secret && !selected.removeSecret ? (
                              <div className="credential-saved"><span className="secret-mask">•••••••• saved{selected.credential_source ? ` (${selected.credential_source})` : ""}</span>
                                <button className="button button-quiet button-small" onClick={() => patchProfile(selected.id, { replacing: true })}>Replace</button>
                                <button className="button button-quiet button-small danger" onClick={() => patchProfile(selected.id, { removeSecret: true })}>Remove</button></div>
                            ) : selected.removeSecret ? (
                              <div className="credential-saved"><span className="muted">Will be removed when you save.</span><button className="button button-quiet button-small" onClick={() => patchProfile(selected.id, { removeSecret: false })}>Undo</button></div>
                            ) : (
                              <input type="password" autoComplete="off" spellCheck={false} value={selected.secret || ""} placeholder={`Paste your ${selectedType.credential_label.toLowerCase()}`} onChange={(event) => patchProfile(selected.id, { secret: event.target.value })} />)}
                            <small>Stored only on this computer in {storage === "keyring" ? "your operating system's credential vault" : storage === "file" ? "an owner-only file in your SUGAR folder" : "memory for this session"}. Never written to projects, logs, or Git.</small></div>)}</div></li>
                      <li className="hier-step"><span className="hier-n">3</span><div className="hier-body"><h4>Model</h4>
                        <label className="field-block"><span>Model</span><input value={selected.model} list={`models-${selected.id}`} placeholder={selectedType.default_model || "model name"} onChange={(event) => patchProfile(selected.id, { model: event.target.value })} />
                          <datalist id={`models-${selected.id}`}>{modelOptions.map((m) => <option key={m} value={m} />)}</datalist>
                          <small>{modelOptions.length ? `${modelOptions.length} models available to this credential — start typing to choose.` : "Run Test connection to list the models this credential can use."}</small></label></div></li>
                      <li className="hier-step"><span className="hier-n">4</span><div className="hier-body"><Collapsible title="Advanced options" hint="Endpoint override, organization, timeout">
                        {!selectedType.needs_endpoint && <label className="field-block"><span>Endpoint override</span><input value={selected.endpoint} placeholder={selectedType.default_endpoint} onChange={(event) => patchProfile(selected.id, { endpoint: event.target.value })} /></label>}
                        {selectedType.supports_organization && <div className="field-grid">
                          <label className="field-block"><span>Organization ID (optional)</span><input value={selected.organization} onChange={(event) => patchProfile(selected.id, { organization: event.target.value })} /></label>
                          <label className="field-block"><span>Project ID (optional)</span><input value={selected.project} onChange={(event) => patchProfile(selected.id, { project: event.target.value })} /></label></div>}
                        <label className="field-block"><span>Request timeout (seconds)</span><input type="number" min={5} max={600} value={Number(selected.advanced.timeout_seconds ?? 60)} onChange={(event) => patchProfile(selected.id, { advanced: { ...selected.advanced, timeout_seconds: Number(event.target.value) || 60 } })} /></label>
                      </Collapsible></div></li>
                    </ol>
                    <div className="provider-actions">
                      <button className="button button-secondary" disabled={testing === selected.id || (selectedType.needs_credential && !selected.secret && !selected.has_credential)} onClick={() => void test(selected)}>{testing === selected.id ? <><Spinner /> Testing…</> : "Test connection"}</button>
                      <label className="check-row"><input type="checkbox" checked={defaultId === selected.id} onChange={() => setDefaultId(selected.id)} /><span>Use as default</span></label>
                      <button className="button button-quiet danger" onClick={() => removeProfile(selected.id)}>Remove provider</button>
                    </div>
                    {reports[selected.id] ? <ConnectionResult report={reports[selected.id]} /> : selected.status.state !== "untested" && selected.status.checked_at ? (
                      <p className={`muted ${selected.status.state === "failed" ? "warn-text" : ""}`}>Last test {formatTime(selected.status.checked_at)}: {selected.status.state === "ok" ? "connected." : selected.status.message}</p>) : null}
                    {selected.isNew && <p className="muted">This provider is not saved yet.</p>}
                  </div>
                ) : <div className="provider-empty"><p className="muted">No providers yet. Without one, SUGAR interprets requests with its built-in interpreter and skips translation.</p><button className="button button-primary" onClick={addProfile}>＋ Add a provider</button></div>}
              </div>
            </div>)}

          {section === "platforms" && (
            <div className="panel settings-panel">
              <div className="section-title"><div className="section-icon blue">↗</div><div><h3>Platform credentials</h3><p>Some platforms need a key before they can be searched. Platforms without one are skipped, with a clear message.</p></div></div>
              <div className="platform-cards">
                {platforms.filter((p) => p.secrets.length > 0).map((platform) => (
                  <div className="platform-card" key={platform.id}>
                    <div className="platform-card-head"><strong>{platform.label}</strong><Pill tone={platform.state === "ready" ? "ok" : "warn"}>{platform.state === "ready" ? "Ready" : "Needs credential"}</Pill></div>
                    <p className="muted">{platform.description}</p>
                    {platform.secrets.map((secret) => (
                      <label className="field-block" key={secret.key}><span>{secret.label}</span>
                        {secret.configured && !platformReplacing.has(secret.key) && !platformClear.has(secret.key) ? (
                          <span className="credential-saved"><span className="secret-mask">•••••••• saved{secret.source ? ` (${secret.source})` : ""}</span>
                            {secret.source !== "environment" && <button type="button" className="button button-quiet button-small danger" onClick={() => setPlatformClear(new Set([...platformClear, secret.key]))}>Remove</button>}
                            <button type="button" className="button button-quiet button-small" onClick={() => setPlatformReplacing(new Set([...platformReplacing, secret.key]))}>Replace</button></span>
                        ) : platformClear.has(secret.key) ? <span className="credential-saved"><span className="muted">Will be removed when you save.</span><button type="button" className="button button-quiet button-small" onClick={() => { const next = new Set(platformClear); next.delete(secret.key); setPlatformClear(next); }}>Undo</button></span>
                          : <input type="password" autoComplete="off" spellCheck={false} value={platformSecrets[secret.key] || ""} placeholder={secret.required ? "Required to search this platform" : "Optional"} onChange={(event) => setPlatformSecrets({ ...platformSecrets, [secret.key]: event.target.value })} />}
                      </label>))}
                  </div>))}
                {platforms.filter((p) => p.secrets.length === 0).length > 0 && <p className="muted">No credential needed: {platforms.filter((p) => p.secrets.length === 0 && p.keyword_search).map((p) => p.label).join(", ") || "none"}.</p>}
              </div>
              <p className="footnote">Credentials are stored only on this computer and are redacted from logs, exports, and diagnostic reports. Environment variables such as SUGAR_X_BEARER_TOKEN take precedence for local development.</p>
            </div>)}

          {section === "interface" && (
            <div className="panel settings-panel">
              <div className="section-title"><div className="section-icon violet">◫</div><div><h3>Interface</h3><p>Preview changes here; press Save changes to keep them.</p></div></div>
              <div className="form-stack">
                <div className="field-block"><span>Experience</span>
                  <Segmented label="Experience" value={draftPrefs.mode} onChange={(mode) => setDraftPrefs({ ...draftPrefs, mode })} options={[{ value: "basic", label: "Basic", hint: "Request, plan, run, activity, results" }, { value: "advanced", label: "Advanced", hint: "Adds source, query, language, limits and provider controls" }]} />
                  <small>{draftPrefs.mode === "basic" ? "Research request, plan, activity and results — with sensible defaults." : "Adds query editing, source and language controls, limits, concurrency, providers, and models."}</small></div>
                <div className="field-block"><span>Text size — {Math.round(draftPrefs.textScale * 100)}%</span>
                  <input type="range" min={85} max={150} step={5} value={Math.round(draftPrefs.textScale * 100)} onChange={(event) => setDraftPrefs({ ...draftPrefs, textScale: Number(event.target.value) / 100 })} aria-label="Text size" />
                  <small>This adjusts SUGAR's text on top of your operating system's display scaling. Everything, including buttons and spacing, scales with it.</small>
                  <p className="text-sample">The quick brown fox — تجربة النص — 文本示例</p></div>
                <div className="field-block"><span>Color theme</span>
                  <Segmented label="Color theme" value={draftPrefs.theme} onChange={(theme) => setDraftPrefs({ ...draftPrefs, theme })} options={[{ value: "light", label: "Light" }, { value: "dark", label: "Dark" }]} /></div>
                <div className="field-block"><span>Density</span>
                  <Segmented label="Density" value={draftPrefs.density} onChange={(density) => setDraftPrefs({ ...draftPrefs, density })} options={[{ value: "comfortable", label: "Comfortable" }, { value: "compact", label: "Compact" }]} /></div>
                <div className="field-block"><span>Request interpretation</span>
                  <Segmented label="Interpreter" value={draftPrefs.interpreter} onChange={(interpreter) => setDraftPrefs({ ...draftPrefs, interpreter })} options={[{ value: "auto", label: "Use my LLM provider", hint: "Falls back to the built-in interpreter" }, { value: "deterministic", label: "Built-in only", hint: "Offline and reproducible" }]} />
                  <small>{draftPrefs.interpreter === "auto" ? "If a provider is set up SUGAR uses it, and falls back to the built-in interpreter if it fails." : "Never calls a model to interpret; the same request always gives the same plan."}</small></div>
                <label className="check-row"><input type="checkbox" checked={draftPrefs.debug} onChange={(event) => setDraftPrefs({ ...draftPrefs, debug: event.target.checked })} /><span><strong>Debug mode</strong> — show interpreted schema, queries, connector and model calls, timings, retries, and rejection reasons. Secrets stay redacted.</span></label>
                <button className="button button-quiet" onClick={() => setDraftPrefs(DEFAULT_PREFS)}>Reset interface to defaults</button>
              </div>
            </div>)}

          {section === "connection" && !isTauri() && (
            <div className="panel settings-panel">
              <div className="section-title"><div className="section-icon blue">↗</div><div><h3>Research API</h3><p>The browser interface works with a local service or an approved hosted endpoint. This connects immediately; it is not part of Save changes.</p></div></div>
              <div className="form-stack">
                <label className="field-block"><span>API address</span><input type="url" value={apiUrl} onChange={(event) => onApiUrl(event.target.value)} placeholder="http://127.0.0.1:8765" /></label>
                <label className="field-block"><span>API token <small>Only when the service requires one</small></span><input type="password" autoComplete="off" value={apiToken} onChange={(event) => onApiToken(event.target.value)} placeholder="Kept in this browser session only" /></label>
                <div><button className="button button-primary" onClick={onConnect} disabled={busy}>Connect</button></div>
              </div>
            </div>)}

          {section === "privacy" && (
            <div className="panel settings-panel">
              <div className="section-title"><div className="section-icon green">◉</div><div><h3>Privacy and diagnostics</h3><p>What is stored, where, and how to report a problem safely.</p></div></div>
              <ul className="plain-list">
                <li>Credentials live in {storage === "keyring" ? "your operating system's credential vault" : "an owner-only file in your SUGAR folder"} and are referenced — never copied — by projects and runs.</li>
                <li>Logs, activity events, exports, and diagnostic reports have credentials redacted.</li>
                <li>Projects contain plans, runs, sources, translations, and notes, but no credentials.</li>
              </ul>
              <div className="preview-actions"><button className="button button-secondary" onClick={() => void research.diagnostics().then(setDiagnostic).catch((issue) => onError(String(issue)))}>Build diagnostic report</button>
                {diagnostic && <CopyButton text={diagnostic} label="Copy for a bug report" className="button button-primary button-small" />}</div>
              {diagnostic && <pre className="json-view">{diagnostic}</pre>}
            </div>)}
        </div>
      </div>

      <div className={`save-bar ${dirty ? "dirty" : ""} state-${state.kind}`} role="region" aria-label="Save settings">
        <span className="save-status" role="status" aria-live="polite">
          {state.kind === "saving" ? <><Spinner /> Saving…</> : state.kind === "error" ? <span className="warn-text">Could not save: {state.message}</span> : dirty ? <><span className="dirty-dot" /> {changeCount} unsaved change{changeCount === 1 ? "" : "s"}</> : state.kind === "saved" ? <span className="ok-text">✓ All changes saved at {formatTime(state.at || "", true)}</span> : "No unsaved changes"}
        </span>
        <div><button className="button button-quiet" disabled={!dirty || state.kind === "saving"} onClick={revert}>Revert</button>
          <button className="button button-primary" disabled={!dirty || state.kind === "saving"} onClick={() => void save()}>Save changes</button></div>
      </div>
    </section>
  );
}
