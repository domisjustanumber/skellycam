//! Windows only: map the USB (micro)frame counter to QueryPerformanceCounter using
//! WinUsb_GetCurrentFrameNumber (returns frame number + the QPC value at which it was read).
//! This is the host-side half of UVC SCR clock recovery (SCR = device STC + 11-bit SOF).
//! Needs a WinUSB-bound interface; it opens the device's WinUSB interface path itself, so it
//! runs *before/after* streaming (WinUSB allows one open at a time).
//! Device interface path: HKLM\SYSTEM\CurrentControlSet\Enum\<instance>\Device Parameters\
//! DeviceInterfaceGUIDs (written by the WinUSB INF / Zadig) -> CM_Get_Device_Interface_ListW.

use serde_json::{json, Value};
use windows::core::{GUID, PCWSTR};
use windows::Win32::Devices::DeviceAndDriverInstallation::{CM_Get_Device_Interface_ListW, CM_Get_Device_Interface_List_SizeW, CM_GET_DEVICE_INTERFACE_LIST_PRESENT, CR_SUCCESS};
use windows::Win32::Devices::Usb::{WinUsb_Free, WinUsb_GetCurrentFrameNumber, WinUsb_Initialize, WINUSB_INTERFACE_HANDLE};
use windows::Win32::Foundation::{CloseHandle, GENERIC_READ, GENERIC_WRITE};
use windows::Win32::Storage::FileSystem::{CreateFileW, FILE_FLAG_OVERLAPPED, FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL};
use windows::Win32::System::Registry::{RegGetValueW, HKEY_LOCAL_MACHINE, RRF_RT_REG_MULTI_SZ, RRF_RT_REG_SZ};

fn wide(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(std::iter::once(0)).collect()
}

fn interface_guids(instance: &str) -> Result<Vec<GUID>, String> {
    let key = wide(&format!("SYSTEM\\CurrentControlSet\\Enum\\{instance}\\Device Parameters"));
    let mut out = vec![];
    for name in ["DeviceInterfaceGUIDs", "DeviceInterfaceGUID"] {
        let n = wide(name);
        let mut buf = vec![0u16; 1024];
        let mut sz = (buf.len() * 2) as u32;
        let rc = unsafe { RegGetValueW(HKEY_LOCAL_MACHINE, PCWSTR(key.as_ptr()), PCWSTR(n.as_ptr()), RRF_RT_REG_MULTI_SZ | RRF_RT_REG_SZ, None, Some(buf.as_mut_ptr() as *mut _), Some(&mut sz)) };
        if rc.is_ok() {
            let s = String::from_utf16_lossy(&buf[..(sz as usize / 2)]);
            for g in s.split('\0').filter(|x| x.len() >= 36) {
                let g = g.trim_matches(|c| c == '{' || c == '}');
                if let Ok(u) = GUID::try_from(g) {
                    out.push(u);
                }
            }
        }
    }
    if out.is_empty() {
        Err(format!("no DeviceInterfaceGUID(s) under HKLM\\...\\Enum\\{instance}\\Device Parameters (is the device bound to WinUSB?)"))
    } else {
        Ok(out)
    }
}

/// GUID_DEVINTERFACE_USB_DEVICE. The Microsoft inbox winusb.inf ("WinUsb Device", class USBDevice)
/// writes no DeviceInterfaceGUIDs; the only interface is this one, and WinUsb_Initialize accepts it.
const GUID_DEVINTERFACE_USB_DEVICE: GUID = GUID::from_u128(0xa5dcbf10_6530_11d2_901f_00c04fb951ed);

fn interface_paths(instance: &str) -> Result<Vec<String>, String> {
    let mut paths = vec![];
    let inst = wide(instance);
    let mut guids = interface_guids(instance).unwrap_or_default();
    guids.push(GUID_DEVINTERFACE_USB_DEVICE);
    for g in guids {
        let mut len = 0u32;
        unsafe {
            if CM_Get_Device_Interface_List_SizeW(&mut len, &g, PCWSTR(inst.as_ptr()), CM_GET_DEVICE_INTERFACE_LIST_PRESENT) != CR_SUCCESS {
                continue;
            }
            let mut buf = vec![0u16; len as usize];
            if CM_Get_Device_Interface_ListW(&g, PCWSTR(inst.as_ptr()), &mut buf, CM_GET_DEVICE_INTERFACE_LIST_PRESENT) != CR_SUCCESS {
                continue;
            }
            for p in String::from_utf16_lossy(&buf).split('\0').filter(|s| !s.is_empty()) {
                paths.push(p.to_string());
            }
        }
    }
    if paths.is_empty() {
        Err("no present WinUSB device interface".into())
    } else {
        Ok(paths)
    }
}

/// Sample (frame_number, qpc) `n` times. Returns JSON with samples and a least-squares fit
/// frame_number = a + b * qpc_seconds (b should be 1000/s for the 1 ms frame counter).
pub fn calibrate(instance: &str, n: usize) -> Value {
    let paths = match interface_paths(instance) {
        Ok(p) => p,
        Err(e) => return json!({"error": e}),
    };
    let path = wide(&paths[0]);
    unsafe {
        let h = match CreateFileW(PCWSTR(path.as_ptr()), (GENERIC_READ | GENERIC_WRITE).0, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OVERLAPPED, None) {
            Ok(h) => h,
            Err(e) => return json!({"error": format!("CreateFileW({}): {e}", paths[0])}),
        };
        let mut wh = WINUSB_INTERFACE_HANDLE::default();
        if let Err(e) = WinUsb_Initialize(h, &mut wh) {
            let _ = CloseHandle(h);
            return json!({"error": format!("WinUsb_Initialize: {e}")});
        }
        let freq = crate::hostclock::qpc_freq() as f64;
        let mut samples = vec![];
        for _ in 0..n {
            let mut fnum = 0u32;
            let mut ts = 0i64;
            if WinUsb_GetCurrentFrameNumber(wh, &mut fnum, &mut ts).is_ok() {
                samples.push((fnum, ts));
            }
            std::thread::sleep(std::time::Duration::from_micros(700));
        }
        let _ = WinUsb_Free(wh);
        let _ = CloseHandle(h);
        if samples.len() < 2 {
            return json!({"error": "WinUsb_GetCurrentFrameNumber returned no samples"});
        }
        // unwrap 32-bit frame counter and fit
        let t0 = samples[0].1;
        let f0 = samples[0].0;
        let xs: Vec<f64> = samples.iter().map(|s| (s.1 - t0) as f64 / freq).collect();
        let ys: Vec<f64> = samples.iter().map(|s| s.0.wrapping_sub(f0) as f64).collect();
        let nn = xs.len() as f64;
        let mx = xs.iter().sum::<f64>() / nn;
        let my = ys.iter().sum::<f64>() / nn;
        let sxy: f64 = xs.iter().zip(&ys).map(|(x, y)| (x - mx) * (y - my)).sum();
        let sxx: f64 = xs.iter().map(|x| (x - mx).powi(2)).sum();
        let b = sxy / sxx;
        let a = my - b * mx;
        let resid: Vec<f64> = xs.iter().zip(&ys).map(|(x, y)| y - (a + b * x)).collect();
        let rmax = resid.iter().fold(0f64, |m, r| m.max(r.abs()));
        json!({
            "interface_path": paths[0],
            "n": samples.len(),
            "qpc_frequency": freq,
            "first": {"frame": f0, "qpc": t0},
            "last": {"frame": samples.last().unwrap().0, "qpc": samples.last().unwrap().1},
            "fit_frames_per_s": b,
            "fit_intercept_frames": a,
            "fit_max_abs_residual_frames": rmax,
            "note": "frame = f0 + a + b*(qpc - qpc0)/freq; frame counter is 1 ms (USB frames); SCR SOF is its low 11 bits",
        })
    }
}
