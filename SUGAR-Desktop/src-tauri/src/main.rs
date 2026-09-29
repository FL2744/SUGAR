#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use serde_json::{json, Value};
use std::{collections::HashMap, fs, time::{SystemTime, UNIX_EPOCH}};
use tauri::{AppHandle, Emitter};
use tauri_plugin_shell::ShellExt;

const OPERATIONS: &[&str] = &[
    "workspace-init", "workspace-status", "workspace-register", "workspace-hub",
    "research-requirement", "research-compile", "research-plan", "research-plan-review",
    "research-collect", "research-handoff", "research-handoff-verify", "search", "ingest",
    "harvest", "map", "analysis", "overlap", "diagnostics", "llm-check",
    "research-strategy-review", "research-strategy-update", "research-plan-update",
    "research-import", "research-prepare-review", "research-triage", "research-feedback",
    "weibo-investigate", "weibo-seed-harvest", "weibo-qualify", "state-package", "state-map",
    "state-triage", "state-review-export", "state-review-apply", "state-audit", "state-diff",
    "state-template-us-sites", "state-template-entities", "state-query-plan", "intel-packet",
    "intel-tradecraft", "intel-synthesize", "intel-hypotheses", "intel-compare",
    "intel-next-evidence", "intel-content-lineage", "intel-evidence-graph", "intel-robustness",
    "intel-media-ingest", "intel-media-attach", "intel-capture-page", "intel-semantic-search",
];
const SECRET_ENV: &[(&str, &str)] = &[
    ("llm_api_key", "SUGAR_LLM_API_KEY"),
    ("x_bearer_token", "SUGAR_X_BEARER_TOKEN"),
    ("bluesky_identifier", "SUGAR_BLUESKY_IDENTIFIER"),
    ("bluesky_app_password", "SUGAR_BLUESKY_APP_PASSWORD"),
    ("mastodon_token", "SUGAR_MASTODON_TOKEN"),
    ("weibo_cookie", "SUGAR_WEIBO_COOKIE"),
];

#[derive(Serialize)]
struct BackendResult {
    code: i32,
    events: Vec<Value>,
    stdout: String,
    stderr: String,
}

#[tauri::command]
async fn run_backend(
    app: AppHandle,
    operation: String,
    config: Option<Value>,
    secrets: Option<HashMap<String, String>>,
) -> Result<BackendResult, String> {
    if !OPERATIONS.contains(&operation.as_str()) {
        return Err(format!("Unsupported SUGAR operation: {operation}"));
    }
    let mut command = app.shell().sidecar("sugar-bridge").map_err(|e| e.to_string())?;
    if operation == "diagnostics" {
        command = command.args([operation.as_str()]);
    } else {
        let config_value = config.unwrap_or_else(|| json!({}));
        if !config_value.is_object() {
            return Err("Backend configuration must be a JSON object.".into());
        }
        let stamp = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_nanos();
        let config_path = std::env::temp_dir().join(format!("sugar-{}-{stamp}.json", std::process::id()));
        let bytes = serde_json::to_vec_pretty(&config_value).map_err(|e| e.to_string())?;
        fs::write(&config_path, bytes).map_err(|e| format!("Could not prepare backend request: {e}"))?;
        command = command.args([operation.as_str(), "--config", config_path.to_string_lossy().as_ref()]);
        for (key, variable) in SECRET_ENV {
            command = command.env(*variable, secrets.as_ref().and_then(|m| m.get(*key)).map(String::as_str).unwrap_or(""));
        }
        let result = command.output().await;
        let _ = fs::remove_file(config_path);
        return finish_result(&app, operation, result.map_err(|error| error.to_string())?, secrets.as_ref());
    }
    let output = command.output().await.map_err(|error| error.to_string())?;
    finish_result(&app, operation, output, None)
}

fn finish_result(
    app: &AppHandle,
    operation: String,
    output: tauri_plugin_shell::process::Output,
    secrets: Option<&HashMap<String, String>>,
) -> Result<BackendResult, String> {
    let stdout = redact_secrets(String::from_utf8_lossy(&output.stdout).to_string(), secrets);
    let stderr = redact_secrets(String::from_utf8_lossy(&output.stderr).to_string(), secrets);
    let mut events = Vec::new();
    for line in stdout.lines() {
        if let Ok(event) = serde_json::from_str::<Value>(line) {
            let _ = app.emit("backend-event", &event);
            events.push(event);
        }
    }
    if !stderr.trim().is_empty() {
        let _ = app.emit("backend-event", json!({"event":"backend-stderr", "message":stderr.trim()}));
    }
    let code = output.status.code().unwrap_or(-1);
    let _ = app.emit("backend-finished", json!({"operation":operation, "code":code}));
    Ok(BackendResult { code, events, stdout, stderr })
}

fn redact_secrets(mut text: String, secrets: Option<&HashMap<String, String>>) -> String {
    if let Some(secrets) = secrets {
        for secret in secrets.values().filter(|value| value.len() >= 8) {
            text = text.replace(secret, "[REDACTED]");
        }
    }
    text
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![run_backend])
        .run(tauri::generate_context!())
        .expect("error while running SUGAR desktop");
}
