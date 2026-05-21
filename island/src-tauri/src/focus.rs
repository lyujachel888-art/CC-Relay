use windows::core::PCWSTR;
use windows::Win32::Foundation::HWND;
use windows::Win32::UI::WindowsAndMessaging::{
    FindWindowW, IsIconic, SetForegroundWindow, ShowWindow, SW_RESTORE,
};

#[tauri::command]
pub fn focus_terminal(project: String) -> Result<(), String> {
    let title = format!("cc-bridge-wrapper-{}", project);
    let wide: Vec<u16> = title.encode_utf16().chain(Some(0)).collect();

    unsafe {
        let hwnd: HWND = FindWindowW(PCWSTR::null(), PCWSTR(wide.as_ptr()))
            .map_err(|e| format!("FindWindowW failed: {e}"))?;
        if hwnd.0.is_null() {
            return Err(format!("Window not found: {}", title));
        }
        if IsIconic(hwnd).as_bool() {
            let _ = ShowWindow(hwnd, SW_RESTORE);
        }
        if !SetForegroundWindow(hwnd).as_bool() {
            return Err(format!("SetForegroundWindow failed for {}", title));
        }
    }
    Ok(())
}
