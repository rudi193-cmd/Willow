// Willow Desktop — Tauri v2
// WebView wrapper for Willow (localhost:8420) with system tray and daemon lifecycle.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpStream;
use std::time::Duration;
use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem, Submenu},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, WebviewUrl, WebviewWindowBuilder,
};

// ── Health check ─────────────────────────────────────────────────────────────

fn is_willow_running() -> bool {
    TcpStream::connect_timeout(
        &"127.0.0.1:8420".parse().unwrap(),
        Duration::from_secs(1),
    )
    .is_ok()
}

fn wait_for_willow(seconds: u64) -> bool {
    for _ in 0..seconds {
        if is_willow_running() {
            return true;
        }
        std::thread::sleep(Duration::from_secs(1));
    }
    false
}

// ── Daemon status ───────────────────────────────────────────────────────────

fn fetch_daemon_status() -> Option<String> {
    let url = "http://127.0.0.1:8420/api/skills/status";
    let response = std::process::Command::new("curl")
        .args(["-s", "--connect-timeout", "2", url])
        .output()
        .ok()?;
    if response.status.success() {
        String::from_utf8(response.stdout).ok()
    } else {
        None
    }
}

fn daemon_summary() -> String {
    match fetch_daemon_status() {
        Some(json) => {
            // Parse daemon counts from JSON
            let alive = json.matches(": true").count();
            // Subtract 1 for "server": true at top level
            let daemon_alive = if alive > 0 { alive - 1 } else { 0 };
            let dead = json.matches(": false").count();
            let total = daemon_alive + dead;
            if total > 0 {
                format!("Daemons: {}/{} running", daemon_alive, total)
            } else {
                "Daemons: unknown".to_string()
            }
        }
        None => "Daemons: server offline".to_string(),
    }
}

// ── Willow startup ───────────────────────────────────────────────────────────

#[cfg(target_os = "windows")]
fn find_willow_bat() -> Option<std::path::PathBuf> {
    let exe_dir = std::env::current_exe().ok()?.parent()?.to_path_buf();
    let candidates = [
        exe_dir.join(r"..\..\..\Willow\start_daemons.bat"),
        std::path::PathBuf::from(
            r"C:\Users\Sean\Documents\GitHub\Willow\start_daemons.bat",
        ),
    ];
    for path in &candidates {
        if path.exists() {
            return Some(path.clone());
        }
    }
    None
}

#[cfg(target_os = "windows")]
fn try_start_willow() {
    // Start daemons first
    if let Some(bat) = find_willow_bat() {
        let _ = std::process::Command::new("cmd")
            .args(["/C", "start", "/MIN", bat.to_str().unwrap_or("")])
            .spawn();
    }
    // Start server
    let server_candidates = [
        std::path::PathBuf::from(r"C:\Users\Sean\Documents\GitHub\Willow\server.py"),
    ];
    for path in &server_candidates {
        if path.exists() {
            let _ = std::process::Command::new("cmd")
                .args(["/C", "start", "/MIN", "python", path.to_str().unwrap_or("")])
                .spawn();
            break;
        }
    }
}

#[cfg(not(target_os = "windows"))]
fn try_start_willow() {
    // Linux/WSL: try to start server.py in background
    let candidates = [
        std::path::PathBuf::from("/mnt/c/Users/Sean/Documents/GitHub/Willow/server.py"),
    ];
    for path in &candidates {
        if path.exists() {
            let _ = std::process::Command::new("python3")
                .arg(path)
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .spawn();
            break;
        }
    }
}

// ── Daemon control ──────────────────────────────────────────────────────────

#[cfg(target_os = "windows")]
fn try_start_daemons() {
    if let Some(bat) = find_willow_bat() {
        let _ = std::process::Command::new("cmd")
            .args(["/C", "start", "/MIN", bat.to_str().unwrap_or("")])
            .spawn();
    }
}

#[cfg(not(target_os = "windows"))]
fn try_start_daemons() {
    // Linux: daemons started via server.py internally
}

// ── Open URL in system browser ──────────────────────────────────────────────

#[cfg(target_os = "windows")]
fn open_url(url: &str) {
    let _ = std::process::Command::new("cmd")
        .args(["/C", "start", url])
        .spawn();
}

#[cfg(not(target_os = "windows"))]
fn open_url(url: &str) {
    let _ = std::process::Command::new("xdg-open").arg(url).spawn();
}

// ── Main ─────────────────────────────────────────────────────────────────────

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            // Start Willow if not already running
            if !is_willow_running() {
                try_start_willow();
                if !wait_for_willow(15) {
                    eprintln!("Willow did not start in time — opening anyway");
                }
            }

            // Build tray menu
            let show_item =
                MenuItem::with_id(app, "show", "Open Willow", true, None::<&str>)?;
            let dashboard_item =
                MenuItem::with_id(app, "dashboard", "Dashboard", true, None::<&str>)?;
            let journal_item =
                MenuItem::with_id(app, "journal", "Journal (Shiva)", true, None::<&str>)?;

            let sep1 = PredefinedMenuItem::separator(app)?;

            // Daemon submenu
            let status_label = daemon_summary();
            let daemon_status =
                MenuItem::with_id(app, "daemon_status", &status_label, false, None::<&str>)?;
            let daemon_start =
                MenuItem::with_id(app, "daemon_start", "Start Daemons", true, None::<&str>)?;
            let daemon_refresh =
                MenuItem::with_id(app, "daemon_refresh", "Refresh Status", true, None::<&str>)?;
            let daemon_menu = Submenu::with_items(
                app,
                "Daemons",
                true,
                &[&daemon_status, &daemon_start, &daemon_refresh],
            )?;

            let sep2 = PredefinedMenuItem::separator(app)?;
            let quit_item =
                MenuItem::with_id(app, "quit", "Quit Willow", true, None::<&str>)?;

            let menu = Menu::with_items(
                app,
                &[&show_item, &dashboard_item, &journal_item, &sep1, &daemon_menu, &sep2, &quit_item],
            )?;

            let _tray = TrayIconBuilder::new()
                .menu(&menu)
                .tooltip(&format!("Willow — {}", status_label))
                .on_menu_event(move |app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                    "dashboard" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.set_focus();
                            // Navigate to dashboard (panel opens via URL hash)
                            let _ = w.eval("window.location.hash = 'dashboard'");
                        }
                    }
                    "journal" => open_url("http://localhost:2121/journal/"),
                    "daemon_start" => try_start_daemons(),
                    "daemon_refresh" => {
                        let summary = daemon_summary();
                        eprintln!("Willow: {}", summary);
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                })
                .build(app)?;

            // Main window — loads Willow UI
            WebviewWindowBuilder::new(
                app,
                "main",
                WebviewUrl::External("http://localhost:8420".parse().unwrap()),
            )
            .title("Willow")
            .inner_size(1280.0, 860.0)
            .min_inner_size(800.0, 600.0)
            .center(true)
            .build()?;

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running willow");
}
