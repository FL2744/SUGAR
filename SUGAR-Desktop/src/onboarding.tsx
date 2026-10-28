import { useEffect, useState } from "react";
import { research } from "./research-api";
import type { ConnectionReport, PlatformRow, ProviderType } from "./research-types";
import type { Prefs } from "./prefs";
import { ConnectionResult } from "./settings-page";
import { Pill, Spinner, platformLabel } from "./ui";

type Choice = "openai" | "arc" | "other" | "none";


const CHOICES: Array<{ id: Choice; title: string; body: string }> = [
  { id: "openai", title: "OpenAI", body: "Use your OpenAI API key." },
  { id: "arc", title: "Virginia Tech ARC", body: "Use your ARC API key. Many models are available." },
  { id: "other", title: "Another provider", body: "Anthropic, a local model, or any OpenAI-compatible service. Finish this in Settings." },
  { id: "none", title: "No AI for now", body: "SUGAR still collects, de-duplicates and organizes. Non-English posts won't be translated." },
];

/**
 * Optional setup page: your name, which AI to use (tested before it is saved), what sources need, and a first example.
 * Each section is optional and saves independently. Opening this page is always an explicit user action.
 */
export function Onboarding({ prefs, onSavePrefs, onFinish, onOpenSettings, onTryExample }: {
  prefs: Prefs; onSavePrefs: (prefs: Prefs) => boolean; onFinish: () => void; onOpenSettings: () => void; onTryExample: (text: string) => void;
}) {
  const [name, setName] = useState(prefs.name);
  const [choice, setChoice] = useState<Choice>("none");
  const [secret, setSecret] = useState("");
  const [model, setModel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [types, setTypes] = useState<ProviderType[]>([]);
  const [report, setReport] = useState<ConnectionReport | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [connected, setConnected] = useState("");
  const [platforms, setPlatforms] = useState<PlatformRow[]>([]);

  useEffect(() => { void research.providers().then((r) => setTypes(r.types)).catch(() => undefined); }, []);
  useEffect(() => { void research.platforms().then(setPlatforms).catch(() => undefined); }, []);

  const type = types.find((t) => t.id === (choice === "openai" ? "openai" : "arc"));
  const profile = () => ({ name: choice === "openai" ? "OpenAI" : "Virginia Tech ARC", type: choice === "openai" ? "openai" : "arc", model: model.trim() || type?.default_model || "" });

  const test = async () => {
    setBusy("test"); setError(""); setReport(null);
    try {
      const result = await research.testDraftProvider(profile(), secret.trim());
      setReport(result);
      setModels(result.available_models || []);
    } catch (issue) { setError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); }
  };
  const saveProvider = async () => {
    setBusy("save"); setError("");
    try {
      const saved = await research.saveProvider(profile(), secret.trim(), true);
      setConnected(saved.profile.name);
      try { localStorage.setItem("sugar.providerChoice", saved.profile.id); } catch { /* storage may be unavailable */ }
      setSecret("");           // the key now lives in the credential store; do not keep it in the page

    } catch (issue) { setError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); }
  };
  const finish = (example = "") => {
    onSavePrefs({ ...prefs, name: name.trim(), onboarded: true });
    if (example) onTryExample(example);
    onFinish();
  };

  const needsKey = choice === "openai" || choice === "arc";
  const canTest = needsKey && secret.trim().length > 7 && !((report?.available_models.length || 0) > 0 && !model.trim());


  return (
    <section className="page-content setup-page">
      <div className="page-heading"><div><div className="eyebrow">OPTIONAL SETUP</div><h1>Set up SUGAR</h1><p>Everything is on this page. Configure only what you need; SUGAR works without completing setup.</p></div><button className="button button-secondary" onClick={() => onFinish()}>Back to research</button></div>
      <div className="form-stack">
        <section className="panel settings-panel"><h2>Your name</h2><label className="field-block"><span>What should we call you? <small>Optional; shown on reviews and comments</small></span><input value={name} maxLength={60} onChange={(event) => setName(event.target.value)} placeholder="e.g. Alex Rivera" /></label><button className="button button-secondary" onClick={() => onSavePrefs({ ...prefs, name: name.trim() })}>Save name</button></section>
        <section className="panel settings-panel"><h2>AI model (optional)</h2><p>AI can interpret requests, translate, and suggest broad locations. Without it, you can still collect public sources, organize results, and review evidence.</p>
          <div className="choice-grid" role="radiogroup" aria-label="AI model provider">{CHOICES.map((c) => <button key={c.id} type="button" role="radio" aria-checked={choice === c.id} className={`choice-card ${choice === c.id ? "on" : ""}`} onClick={() => { setChoice(c.id); setModel(types.find((t) => t.id === c.id)?.default_model || ""); setModels([]); setReport(null); setError(""); }}><strong>{c.title}</strong><small>{c.body}</small></button>)}</div>
          {needsKey && <div className="form-stack"><label className="field-block"><span>{type?.credential_label || "API key"}</span><input type="password" autoComplete="off" spellCheck={false} value={secret} onChange={(event) => { setSecret(event.target.value); setModels([]); setReport(null); }} /></label>
            <label className="field-block"><span>Model</span><input type="text" aria-label="Model" value={model} autoCapitalize="none" autoCorrect="off" spellCheck={false} onChange={(event) => { setModel(event.target.value); setReport(null); }} placeholder="Type a model name here" /></label>
            {models.length > 0 && <label className="field-block"><span>Available models</span><select value={models.includes(model) ? model : ""} onChange={(event) => { setModel(event.target.value); setReport(null); }}><option value="">Choose a model or type its name above</option>{models.map((m) => <option key={m} value={m}>{m}</option>)}</select></label>}
            <p className="footnote">Type a model name, or test your connection to load available models. After changing the model, test it before saving.</p>
            <div className="preview-actions"><button className="button button-secondary" onClick={() => void test()} disabled={!canTest || Boolean(busy)}>{busy === "test" ? <Spinner /> : "Test connection"}</button><button className="button button-primary" onClick={() => void saveProvider()} disabled={!report?.ok || Boolean(busy)}>{busy === "save" ? <Spinner /> : "Save provider"}</button></div>{report && <ConnectionResult report={report} />}<p className="footnote">Keys stay in session memory by default. Enter them again after restarting.</p></div>}
          {choice === "other" && <button className="button button-secondary" onClick={onOpenSettings}>Configure another provider in Settings</button>}
          {connected && <p className="notice notice-ok" role="status">{connected} is connected and set as your default.</p>}{error && <div className="inline-error" role="alert">{error}</div>}
        </section>
        <section className="panel settings-panel"><h2>Sources</h2><p>Some public sources work immediately. X and other authenticated sources need their own credentials under Settings.</p><ul className="source-list">{platforms.filter((p) => p.keyword_search).map((p) => <li key={p.id}><div><strong>{platformLabel(p.id)}</strong><small>{p.description}</small></div><Pill tone={p.state === "ready" ? "ok" : "neutral"}>{p.state === "ready" ? "Ready" : "Needs a key"}</Pill></li>)}</ul><button className="button button-secondary" onClick={onOpenSettings}>Manage sources and credentials</button></section>
        <section className="panel settings-panel"><h2>Try a request</h2><p>No setup step is required before researching. You review the plan before collection starts.</p><div className="choice-grid">{["Look into reading rooms and cultural centers run by foreign governments in Southeast Asia", "What are people saying about climate policy in Brazil on Bluesky since 2023?"].map((example) => <button key={example} className="choice-card" onClick={() => finish(example)}><strong>Try an example</strong><small>{example}</small></button>)}</div></section>
      </div>
    </section>
  );
}
