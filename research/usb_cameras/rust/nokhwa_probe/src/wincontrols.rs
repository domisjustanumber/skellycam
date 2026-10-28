//! Windows-only: set exposure / white balance to MANUAL via IAMCameraControl / IAMVideoProcAmp
//! on a separately activated IMFMediaSource, because nokhwa 0.10.11's `set_control` re-uses the
//! control's *current* auto/manual flag and so can never switch a control from auto to manual
//! (nokhwa-bindings-windows-0.4.6 src/lib.rs, set_control: `let flag = current_value.flag()...`).
//! UVC control values live in the device, so they persist after this source is shut down;
//! the capture run reads them back through nokhwa to confirm.

use serde_json::{json, Value};
use std::mem::MaybeUninit;
use std::slice::from_raw_parts;
use windows::core::{Interface, PWSTR};
use windows::Win32::Media::DirectShow::{
    CameraControl_Exposure, CameraControl_Flags_Manual, IAMCameraControl, IAMVideoProcAmp,
    VideoProcAmp_Flags_Manual, VideoProcAmp_WhiteBalance, VideoProcAmp_Gain,
};
use windows::Win32::Media::MediaFoundation::{
    IMFActivate, IMFAttributes, IMFMediaSource, MFCreateAttributes, MFEnumDeviceSources,
    MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE, MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID,
    MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK,
};

fn enum_activates() -> windows::core::Result<Vec<IMFActivate>> {
    unsafe {
        let mut attr: Option<IMFAttributes> = None;
        MFCreateAttributes(&mut attr, 1)?;
        let attr = attr.unwrap();
        attr.SetGUID(
            &MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE,
            &MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID,
        )?;
        let mut count = 0u32;
        let mut arr: MaybeUninit<*mut Option<IMFActivate>> = MaybeUninit::uninit();
        MFEnumDeviceSources(&attr, arr.as_mut_ptr(), &mut count)?;
        let mut out = vec![];
        if count > 0 {
            for a in from_raw_parts(arr.assume_init(), count as usize).iter().flatten() {
                out.push(a.clone());
            }
        }
        Ok(out)
    }
}

fn symlink_of(a: &IMFActivate) -> String {
    unsafe {
        let mut p = PWSTR::null();
        let mut n = 0u32;
        if a
            .GetAllocatedString(&MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK, &mut p, &mut n)
            .is_ok()
        {
            p.to_string().unwrap_or_default()
        } else {
            String::new()
        }
    }
}

/// `exposure`: IAMCameraControl exposure value (log2 seconds, e.g. -7 = 1/128 s).
/// `wb`: white balance in Kelvin. `gain`: optional gain. Returns a JSON report of what was read back.
pub fn set_manual(symlink: &str, exposure: Option<i32>, wb: Option<i32>, gain: Option<i32>) -> Value {
    let mut rep = json!({"symlink": symlink, "method": "IMFMediaSource QueryInterface IAMCameraControl/IAMVideoProcAmp, then Shutdown"});
    let r: windows::core::Result<()> = (|| unsafe {
        let acts = enum_activates()?;
        let act = acts
            .into_iter()
            .find(|a| symlink_of(a).eq_ignore_ascii_case(symlink))
            .ok_or_else(|| windows::core::Error::new(windows::core::HRESULT(-1), "symlink not found"))?;
        let src: IMFMediaSource = act.ActivateObject()?;
        let cc: IAMCameraControl = src.cast()?;
        let pa: IAMVideoProcAmp = src.cast()?;
        if let Some(e) = exposure {
            let (mut mn, mut mx, mut st, mut df, mut fl) = (0, 0, 0, 0, 0);
            let _ = cc.GetRange(CameraControl_Exposure.0, &mut mn, &mut mx, &mut st, &mut df, &mut fl);
            let set = cc.Set(CameraControl_Exposure.0, e, CameraControl_Flags_Manual.0);
            let (mut v, mut f) = (0, 0);
            let _ = cc.Get(CameraControl_Exposure.0, &mut v, &mut f);
            rep["exposure"] = json!({"requested": e, "range": [mn, mx, st, df], "set_ok": set.is_ok(),
                "set_err": set.err().map(|x| x.to_string()), "readback": v, "readback_flags": f});
        }
        if let Some(w) = wb {
            let (mut mn, mut mx, mut st, mut df, mut fl) = (0, 0, 0, 0, 0);
            let _ = pa.GetRange(VideoProcAmp_WhiteBalance.0, &mut mn, &mut mx, &mut st, &mut df, &mut fl);
            let set = pa.Set(VideoProcAmp_WhiteBalance.0, w, VideoProcAmp_Flags_Manual.0);
            let (mut v, mut f) = (0, 0);
            let _ = pa.Get(VideoProcAmp_WhiteBalance.0, &mut v, &mut f);
            rep["white_balance"] = json!({"requested": w, "range": [mn, mx, st, df], "set_ok": set.is_ok(),
                "set_err": set.err().map(|x| x.to_string()), "readback": v, "readback_flags": f});
        }
        if let Some(g) = gain {
            let set = pa.Set(VideoProcAmp_Gain.0, g, VideoProcAmp_Flags_Manual.0);
            let (mut v, mut f) = (0, 0);
            let _ = pa.Get(VideoProcAmp_Gain.0, &mut v, &mut f);
            rep["gain"] = json!({"requested": g, "set_ok": set.is_ok(), "readback": v, "readback_flags": f});
        }
        let _ = src.Shutdown();
        let _ = act.ShutdownObject();
        Ok(())
    })();
    if let Err(e) = r {
        rep["error"] = json!(e.to_string());
    }
    rep
}

/// Read current exposure/wb through a fresh source (for after-run verification).
pub fn read_back(symlink: &str) -> Value {
    let r: windows::core::Result<Value> = (|| unsafe {
        let acts = enum_activates()?;
        let act = acts
            .into_iter()
            .find(|a| symlink_of(a).eq_ignore_ascii_case(symlink))
            .ok_or_else(|| windows::core::Error::new(windows::core::HRESULT(-1), "symlink not found"))?;
        let src: IMFMediaSource = act.ActivateObject()?;
        let cc: IAMCameraControl = src.cast()?;
        let pa: IAMVideoProcAmp = src.cast()?;
        let (mut ev, mut ef, mut wv, mut wf) = (0, 0, 0, 0);
        let _ = cc.Get(CameraControl_Exposure.0, &mut ev, &mut ef);
        let _ = pa.Get(VideoProcAmp_WhiteBalance.0, &mut wv, &mut wf);
        let _ = src.Shutdown();
        let _ = act.ShutdownObject();
        Ok(json!({"exposure": ev, "exposure_flags": ef, "white_balance": wv, "white_balance_flags": wf,
                  "flags_legend": "1=auto 2=manual"}))
    })();
    r.unwrap_or_else(|e| json!({"error": e.to_string()}))
}

pub fn co_init_mta() -> String {
    use windows::Win32::System::Com::{CoInitializeEx, COINIT_MULTITHREADED};
    let hr = unsafe { CoInitializeEx(None, COINIT_MULTITHREADED) };
    format!("{:?}", hr)
}
