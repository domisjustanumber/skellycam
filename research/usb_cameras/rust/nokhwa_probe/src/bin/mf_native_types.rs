//! Windows-only: dump every *native* media type of every MF video capture device with the raw
//! MF_MT_SUBTYPE GUID, to explain which formats nokhwa's guid_to_frameformat() keeps or drops.
//! Opens each device (wrap in camlock). Writes summary.json to --out DIR or the default results dir.
//!   build/release/mf_native_types.exe [--out DIR]
#[cfg(not(windows))]
fn main() {
    eprintln!("mf_native_types is Windows-only");
}

#[cfg(windows)]
fn main() {
    use serde_json::json;
    use std::mem::MaybeUninit;
    use std::slice::from_raw_parts;
    use windows::core::{GUID, PWSTR};
    use windows::Win32::Media::MediaFoundation::*;
    use windows::Win32::System::Com::{CoInitializeEx, COINIT_MULTITHREADED};

    let argv: Vec<String> = std::env::args().collect();
    let out = argv
        .iter()
        .position(|a| a == "--out")
        .and_then(|i| argv.get(i + 1))
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| {
            let host = std::process::Command::new("hostname").output().map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string()).unwrap_or("unknown".into());
            let secs = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs();
            std::path::PathBuf::from(format!("research/usb_cameras/results/windows/{host}/rust_mf_native_types/{secs}"))
        });
    std::fs::create_dir_all(&out).unwrap();

    fn fourcc_of(g: &GUID) -> String {
        // MF video subtypes are FOURCC-based GUIDs {XXXXXXXX-0000-0010-8000-00AA00389B71}
        if g.data2 == 0 && g.data3 == 0x0010 && g.data4 == [0x80, 0x00, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71] {
            let b = g.data1.to_le_bytes();
            if b.iter().all(|c| c.is_ascii_graphic() || *c == b' ') {
                return String::from_utf8_lossy(&b).to_string();
            }
            return format!("D3DFMT_{}", g.data1);
        }
        format!("{g:?}")
    }

    unsafe {
        let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
        MFStartup(MF_API_VERSION, MFSTARTUP_NOSOCKET).unwrap();
        let mut attr: Option<IMFAttributes> = None;
        MFCreateAttributes(&mut attr, 1).unwrap();
        let attr = attr.unwrap();
        attr.SetGUID(&MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE, &MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID).unwrap();
        let mut count = 0u32;
        let mut arr: MaybeUninit<*mut Option<IMFActivate>> = MaybeUninit::uninit();
        MFEnumDeviceSources(&attr, arr.as_mut_ptr(), &mut count).unwrap();
        let acts: Vec<IMFActivate> = if count > 0 { from_raw_parts(arr.assume_init(), count as usize).iter().flatten().cloned().collect() } else { vec![] };
        let mut devs = vec![];
        for (i, a) in acts.iter().enumerate() {
            let gs = |k: &GUID| -> String {
                let mut p = PWSTR::null();
                let mut n = 0u32;
                if a.GetAllocatedString(k, &mut p, &mut n).is_ok() { p.to_string().unwrap_or_default() } else { String::new() }
            };
            let name = gs(&MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME);
            let link = gs(&MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK);
            let mut d = json!({"index": i, "name": name, "symlink": link});
            if !link.to_ascii_lowercase().contains("usb#") {
                d["skipped"] = json!("not a USB device");
                devs.push(d);
                continue;
            }
            let src: windows::core::Result<IMFMediaSource> = a.ActivateObject();
            let src = match src { Ok(s) => s, Err(e) => { d["error"] = json!(e.to_string()); devs.push(d); continue; } };
            for disable_converters in [true, false] {
                let mut ra: Option<IMFAttributes> = None;
                MFCreateAttributes(&mut ra, 1).unwrap();
                let ra = ra.unwrap();
                ra.SetUINT32(&MF_READWRITE_DISABLE_CONVERTERS, disable_converters as u32).unwrap();
                let rdr = match MFCreateSourceReaderFromMediaSource(&src, &ra) { Ok(r) => r, Err(e) => { d[format!("reader_error_dc{disable_converters}")] = json!(e.to_string()); continue; } };
                let mut counts = std::collections::BTreeMap::<String, u32>::new();
                let mut types = vec![];
                let mut k = 0u32;
                while let Ok(mt) = rdr.GetNativeMediaType(0xFFFF_FFFC, k) {
                    k += 1;
                    let sub = mt.GetGUID(&MF_MT_SUBTYPE).unwrap_or_default();
                    let fs = mt.GetUINT64(&MF_MT_FRAME_SIZE).unwrap_or(0);
                    let fr = mt.GetUINT64(&MF_MT_FRAME_RATE).unwrap_or(0);
                    let fcc = fourcc_of(&sub);
                    *counts.entry(fcc.clone()).or_default() += 1;
                    types.push(format!("{} {}x{} {}/{}", fcc, fs >> 32, fs as u32, fr >> 32, fr as u32));
                }
                d[format!("native_types_disable_converters_{disable_converters}")] = json!({"count": k, "by_subtype": counts, "types": types});
                drop(rdr);
            }
            let _ = src.Shutdown();
            let _ = a.ShutdownObject();
            devs.push(d);
        }
        let res = json!({"test": "rust_mf_native_types", "platform": "windows", "devices": devs,
            "note": "GetNativeMediaType on IMFSourceReader created from the device IMFMediaSource; fourcc decoded from MF FOURCC GUID"});
        std::fs::write(out.join("summary.json"), serde_json::to_string_pretty(&res).unwrap()).unwrap();
        println!("{}", out.join("summary.json").display());
    }
}
