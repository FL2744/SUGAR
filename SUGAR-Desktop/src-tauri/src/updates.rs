use serde::Serialize;
use std::{
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    time::{Duration, Instant},
};
use tauri::{ipc::Channel, AppHandle, State};
use tauri_plugin_updater::{Update, UpdaterExt};

// Both the sidecar and the installer enter this gate. A UI race cannot interrupt
// an active export, collection, or credential-vault write with an app restart.
#[derive(Default)]
struct Activity {
    backend_count: usize,
    installing: bool,
}

pub struct WorkGuard(Arc<Mutex<Activity>>, bool);

impl Drop for WorkGuard {
    fn drop(&mut self) {
        let mut activity = self.0.lock().unwrap_or_else(|e| e.into_inner());
        if self.1 {
            activity.installing = false;
        } else {
            activity.backend_count -= 1;
        }
    }
}

#[derive(Default)]
pub struct UpdateRuntime {
    activity: Arc<Mutex<Activity>>,
    operation: AtomicBool,
    pending: Mutex<Option<Update>>,
    downloaded: Mutex<Option<Vec<u8>>>,
}

impl UpdateRuntime {
    pub fn start_backend(&self) -> Result<WorkGuard, String> {
        let mut activity = self.activity.lock().map_err(|e| e.to_string())?;
        if activity.installing {
            return Err("SUGAR is installing an update. Research can resume after restart.".into());
        }
        activity.backend_count += 1;
        Ok(WorkGuard(self.activity.clone(), false))
    }

    fn start_install(&self) -> Result<WorkGuard, String> {
        let mut activity = self.activity.lock().map_err(|e| e.to_string())?;
        if activity.installing || activity.backend_count > 0 {
            return Err(
                "Wait for the active research operation to finish before installing.".into(),
            );
        }
        activity.installing = true;
        Ok(WorkGuard(self.activity.clone(), true))
    }

    fn start_operation(&self) -> Result<OperationGuard<'_>, String> {
        self.operation
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .map_err(|_| "An update operation is already running.".to_string())?;
        Ok(OperationGuard(&self.operation))
    }
}

struct OperationGuard<'a>(&'a AtomicBool);

impl Drop for OperationGuard<'_> {
    fn drop(&mut self) {
        self.0.store(false, Ordering::SeqCst);
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateStatus {
    configured: bool,
    current_version: String,
}

#[tauri::command]
pub fn updater_status(app: AppHandle) -> UpdateStatus {
    let config = app.config();
    let updater = config.plugins.0.get("updater");
    let configured = updater.is_some_and(|value| {
        value["pubkey"]
            .as_str()
            .is_some_and(|key| !key.trim().is_empty())
            && value["endpoints"].as_array().is_some_and(|urls| {
                !urls.is_empty()
                    && urls
                        .iter()
                        .all(|url| url.as_str().is_some_and(|url| url.starts_with("https://")))
            })
    });
    UpdateStatus {
        configured,
        current_version: app.package_info().version.to_string(),
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateInfo {
    version: String,
    current_version: String,
    notes: String,
}

fn make_updater<R: tauri::Runtime>(
    app: &AppHandle<R>,
) -> Result<tauri_plugin_updater::Updater, String> {
    app.updater_builder()
        .version_comparator(|current, release| {
            release.version > current && release.version.pre.is_empty()
        })
        .timeout(Duration::from_secs(30))
        .build()
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn check_for_update(
    app: AppHandle,
    state: State<'_, UpdateRuntime>,
) -> Result<Option<UpdateInfo>, String> {
    let _operation = state.start_operation()?;
    if !updater_status(app.clone()).configured {
        return Err(
            "Automatic updates are not configured in this build. Use the release downloads.".into(),
        );
    }
    // Checking must finish promptly while large installer downloads get their own timeout.
    let update = make_updater(&app)?
        .check()
        .await
        .map_err(|e| format!("Could not check for updates: {e}"))?;
    if let Some(update) = &update {
        if update.download_url.scheme() != "https" {
            return Err("The update download must use HTTPS.".into());
        }
        if update.signature.trim().is_empty() {
            return Err("The update is missing its signature.".into());
        }
    }
    let info = update.as_ref().map(|update| UpdateInfo {
        version: update.version.clone(),
        current_version: update.current_version.clone(),
        notes: update.body.clone().unwrap_or_default(),
    });
    *state.pending.lock().map_err(|e| e.to_string())? = update;
    *state.downloaded.lock().map_err(|e| e.to_string())? = None;
    Ok(info)
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DownloadProgress {
    downloaded: u64,
    total: Option<u64>,
}

#[tauri::command]
pub async fn download_update(
    state: State<'_, UpdateRuntime>,
    on_progress: Channel<DownloadProgress>,
) -> Result<(), String> {
    let _operation = state.start_operation()?;
    let mut update = state
        .pending
        .lock()
        .map_err(|e| e.to_string())?
        .clone()
        .ok_or("Check for an update before downloading.")?;
    update.timeout = Some(Duration::from_secs(15 * 60));
    let mut downloaded = 0_u64;
    let mut last_notification = Instant::now();
    let bytes = update
        .download(
            |chunk, total| {
                downloaded += chunk as u64;
                if last_notification.elapsed() >= Duration::from_millis(100)
                    || total == Some(downloaded)
                {
                    let _ = on_progress.send(DownloadProgress { downloaded, total });
                    last_notification = Instant::now();
                }
            },
            || {},
        )
        .await
        .map_err(|e| format!("The update could not be downloaded and verified: {e}"))?;
    // download() verifies the signature before the package becomes installable.
    let _ = on_progress.send(DownloadProgress {
        downloaded: bytes.len() as u64,
        total: Some(bytes.len() as u64),
    });
    *state.downloaded.lock().map_err(|e| e.to_string())? = Some(bytes);
    Ok(())
}

#[tauri::command]
pub async fn install_update(app: AppHandle, state: State<'_, UpdateRuntime>) -> Result<(), String> {
    let _operation = state.start_operation()?;
    let _work = state.start_install()?;
    let update = state
        .pending
        .lock()
        .map_err(|e| e.to_string())?
        .clone()
        .ok_or("Check for an update before installing.")?;
    let bytes = state
        .downloaded
        .lock()
        .map_err(|e| e.to_string())?
        .take()
        .ok_or("Download and verify the update before installing.")?;
    let (result, bytes) = tauri::async_runtime::spawn_blocking(move || {
        let result = update.install(&bytes);
        (result, bytes)
    })
    .await
    .map_err(|e| e.to_string())?;
    if let Err(error) = result {
        *state.downloaded.lock().map_err(|e| e.to_string())? = Some(bytes);
        return Err(format!("The update could not be installed: {error}"));
    }
    // Windows exits inside install(); macOS needs an explicit relaunch.
    app.restart();
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        io::{Read, Write},
        net::TcpListener,
        thread,
    };
    use tauri::test::{mock_builder, mock_context, noop_assets};

    const PAYLOAD: &[u8] = b"SUGAR updater verification test; not an installer.\n";
    const PUBLIC_KEY: &str = include_str!("../tests/fixtures/updater-public-key.txt");
    const SIGNATURE: &str = include_str!("../tests/fixtures/updater-signature.txt");

    // Exercise Tauri's actual check/download/signature path without opening a GUI
    // or running an installer. HTTP is enabled only in this loopback test context.
    fn download_fixture(payload: &[u8], announced_version: &str) -> Result<Vec<u8>, String> {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let address = listener.local_addr().unwrap();
        let body = serde_json::to_vec(&serde_json::json!({
            "version": announced_version,
            "url": format!("http://{address}/payload"),
            "signature": SIGNATURE.trim(),
        }))
        .unwrap();
        let payload = payload.to_vec();
        let server = thread::spawn(move || {
            for body in [body, payload] {
                let deadline = Instant::now() + Duration::from_secs(5);
                let mut stream = loop {
                    match listener.accept() {
                        Ok((stream, _)) => break stream,
                        Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                            if Instant::now() >= deadline {
                                return;
                            }
                            thread::sleep(Duration::from_millis(5));
                        }
                        Err(error) => panic!("Fixture server failed: {error}"),
                    }
                };
                stream
                    .set_read_timeout(Some(Duration::from_secs(5)))
                    .unwrap();
                let mut request = [0_u8; 4096];
                stream.read(&mut request).unwrap();
                let header = format!("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n", body.len());
                stream.write_all(header.as_bytes()).unwrap();
                stream.write_all(&body).unwrap();
            }
        });
        let mut context = mock_context(noop_assets());
        context.config_mut().plugins.0.insert(
            "updater".into(),
            serde_json::json!({
                "pubkey": PUBLIC_KEY.trim(),
                "endpoints": [format!("http://{address}/manifest")],
                "requireSignedVersion": true,
                "dangerousInsecureTransportProtocol": true,
            }),
        );
        let app = mock_builder()
            .plugin(tauri_plugin_updater::Builder::new().build())
            .build(context)
            .unwrap();
        let result = tauri::async_runtime::block_on(async {
            let update = make_updater(app.handle())?
                .check()
                .await
                .map_err(|e| e.to_string())?
                .ok_or("Expected a newer version")?;
            update
                .download(|_, _| {}, || {})
                .await
                .map_err(|e| e.to_string())
        });
        server.join().unwrap();
        result
    }

    #[test]
    fn actual_tauri_download_verifies_signature_and_rejects_corruption_or_version_replay() {
        assert_eq!(download_fixture(PAYLOAD, "1.7.0").unwrap(), PAYLOAD);
        assert!(download_fixture(b"corrupted package", "1.7.0").is_err());
        assert!(download_fixture(PAYLOAD, "9.9.9").is_err());
    }

    #[test]
    fn installation_waits_for_every_sidecar_and_blocks_new_work() {
        let state = UpdateRuntime::default();
        let first = state.start_backend().unwrap();
        let second = state.start_backend().unwrap();
        assert!(state.start_install().is_err());
        drop(first);
        assert!(state.start_install().is_err());
        drop(second);
        let install = state.start_install().unwrap();
        assert!(state.start_backend().is_err());
        assert!(state.start_install().is_err());
        drop(install);
        assert!(state.start_backend().is_ok());
    }

    #[test]
    fn failed_operations_release_the_update_lock() {
        let state = UpdateRuntime::default();
        let operation = state.start_operation().unwrap();
        assert!(state.start_operation().is_err());
        drop(operation);
        assert!(state.start_operation().is_ok());
    }
}
