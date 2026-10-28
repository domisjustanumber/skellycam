//! uvc_iso: the single from-scratch UVC MJPEG streamer (raw USB isochronous transfers, Rust).
//! One UVC implementation (src/uvc.rs: descriptors, probe/commit, payload headers, frame
//! assembly) over two interchangeable USB backends (src/usb.rs trait):
//!   rawusb  (default, pure Rust 0.1.7: WinUSB WinUsb_ReadIsochPipeAsap / Linux usbfs / macOS IOKit)
//!   libusb  (--features libusb; libusb1-sys 0.7.0, vendored C libusb 1.0.27; needs a C compiler)
//! Covers: native MJPEG bytes (goal 1), per-frame PTS/SCR + host timestamps (goal 2),
//! app-chosen alternate setting = app-controlled USB bandwidth (goal 3), one code path per OS (goal 5).
//!
//! Build (from research/usb_cameras/rust; workspace target dir ./build):
//!   cargo build --release -p uvc_iso                       # rawusb only
//!   cargo build --release -p uvc_iso --features libusb     # rawusb + libusb
//! Run (wrap anything that opens a camera in tools/camlock.py on the shared Windows box):
//!   uvc_iso list   [--backend rawusb|libusb] [--out DIR]               (alias: descriptors; enumerates only)
//!   uvc_iso stream --vid 046d --pid 0843 [--serial S] [--port 1.4] [--width 1280 --height 720 --fps 30]
//!                  [--alt device|payload:BYTES|N] [--seconds 10] [--xfers 8 --pkts 32] [--save-samples 1]
//!                  [--exposure-100us 78] [--wb 4000] [--backend rawusb|libusb]
//!                  [--sof-instance 'USB\VID_046D&PID_0843&MI_00\...'] [--out DIR]   (alias: capture;
//!                  --transfers/--packets accepted for --xfers/--pkts)
//!   uvc_iso sof-calib --instance <PnP instance id of the WinUSB-bound interface>   (Windows only)
//! Requirements:
//!   Windows: the camera's video function bound to WinUSB (phase 2: Zadig or pnputil + INF). With
//!            usbvideo.sys bound, `stream` fails at open/claim; the error lands in summary.json.
//!   Linux  : write access to /dev/bus/usb/BBB/DDD (udev rule or sudo). Both backends auto-detach
//!            uvcvideo from the claimed interfaces while streaming. Run:
//!            cargo build --release -p uvc_iso [--features libusb] && ./build/release/uvc_iso list
//!   macOS  : same commands. Recent macOS keeps the device in the UVC assistant extension; claiming
//!            the VC/VS interfaces may need root or may fail (record the error; that is the finding).
//! Linux/macOS runners + instructions: platform/run_linux.sh, platform/run_macos.sh, platform/RUN_LINUX_MACOS.md;
//! Windows phase 2 (after WinUSB binding): platform/run_windows_phase2.sh.
//! Output: DIR/summary.json + DIR/frames_<vid>_<pid>.jsonl (README frame-log schema) + sample JPEGs.
//! Default DIR: research/usb_cameras/results/<os>/<host>/rust_uvc_iso_<cmd>_<backend>/<unix_ts>/

#[path = "../../nokhwa_probe/src/hostclock.rs"]
#[allow(dead_code)]
mod hostclock;
mod usb;
mod uvc;
#[cfg(feature = "rawusb")]
mod backend_rawusb;
#[cfg(feature = "libusb")]
mod backend_libusb;
#[cfg(windows)]
mod winsof;

use serde_json::{json, Value};
use std::collections::HashMap;
use std::io::Write;
use std::path::PathBuf;
use std::sync::{mpsc, Arc, Mutex};
use std::time::{Duration, Instant};
use usb::*;
use uvc::*;

fn hostname() -> String {
    std::process::Command::new("hostname").output().ok()
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().split('.').next().unwrap_or("").to_string())
        .filter(|s| !s.is_empty()).unwrap_or_else(|| "unknown".into())
}
fn platform() -> &'static str {
    std::env::consts::OS
}
fn stamp() -> String {
    let s = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs();
    format!("{s}")
}
fn default_out(test: &str) -> PathBuf {
    let cwd = std::env::current_dir().unwrap();
    let base = if cwd.join("research/usb_cameras").is_dir() {
        cwd.join("research/usb_cameras")
    } else if cwd.ends_with("uvc_iso") {
        cwd.join("../..")
    } else if cwd.ends_with("rust") {
        cwd.join("..")
    } else {
        cwd.clone()
    };
    base.join("results").join(platform()).join(hostname()).join(test).join(stamp())
}

struct Args(HashMap<String, String>, Vec<String>);
impl Args {
    fn parse() -> Args {
        let v: Vec<String> = std::env::args().skip(1).collect();
        let mut m = HashMap::new();
        let mut pos = vec![];
        let mut i = 0;
        while i < v.len() {
            if let Some(k) = v[i].strip_prefix("--") {
                let val = v.get(i + 1).filter(|x| !x.starts_with("--")).cloned();
                if val.is_some() {
                    i += 1;
                }
                m.insert(k.to_string(), val.unwrap_or_else(|| "true".into()));
            } else {
                pos.push(v[i].clone());
            }
            i += 1;
        }
        Args(m, pos)
    }
    fn get(&self, k: &str) -> Option<&str> {
        self.0.get(k).map(|s| s.as_str())
    }
    fn num<T: std::str::FromStr>(&self, k: &str, d: T) -> T {
        self.get(k).and_then(|s| s.parse().ok()).unwrap_or(d)
    }
    fn hex16(&self, k: &str) -> Option<u16> {
        self.get(k).and_then(|s| u16::from_str_radix(s.trim_start_matches("0x"), 16).ok())
    }
}

fn make_backend(name: &str) -> Res<Box<dyn Backend>> {
    match name {
        #[cfg(feature = "rawusb")]
        "rawusb" => Ok(Box::new(backend_rawusb::RawUsb::new()?)),
        #[cfg(feature = "libusb")]
        "libusb" => Ok(Box::new(backend_libusb::LibUsb::new()?)),
        other => Err(format!("backend '{other}' not compiled in (features: rawusb default, libusb optional)")),
    }
}

fn env_json(backend: &str) -> Value {
    let os_build = if cfg!(windows) {
        std::process::Command::new("cmd").args(["/c", "ver"]).output()
    } else {
        std::process::Command::new("uname").arg("-a").output()
    }
    .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
    .unwrap_or_default();
    json!({"os": platform(), "arch": std::env::consts::ARCH, "os_build": os_build, "backend": backend,
           "host_clock": hostclock::host_clock_name(), "uvc_iso_version": env!("CARGO_PKG_VERSION"),
           "features": {"rawusb": cfg!(feature = "rawusb"), "libusb": cfg!(feature = "libusb")},
           "profile": if cfg!(debug_assertions) {"debug"} else {"release"}})
}

/// HS periodic budget: USB 2.0 §5.7.4 limits periodic (iso+interrupt) to 80% of a microframe;
/// 60 MB/s * 125 us * 0.8 = 6000 bytes. Approximation for "how many of these alts fit on one HS bus".
const HS_PERIODIC_BYTES_PER_UFRAME: f64 = 6000.0;

fn cmd_list(a: &Args) -> Res<Value> {
    let bname = a.get("backend").unwrap_or("rawusb");
    let b = make_backend(bname)?;
    let t0 = hostclock::host_ns();
    let devs = b.list()?;
    let enum_ms = (hostclock::host_ns() - t0) as f64 / 1e6;
    let mut out = vec![];
    let mut non_uvc = vec![];
    for d in devs {
        let Some(u) = d.raw_config.as_ref().and_then(|r| UvcInfo::parse(r)) else {
            non_uvc.push(json!({"vid": format!("{:04x}", d.vid), "pid": format!("{:04x}", d.pid), "bus": d.bus,
                "port_path": port_path_str(&d.port_path), "speed": d.speed, "raw_config_len": d.raw_config.as_ref().map(|r| r.len()),
                "raw_config_error": d.raw_config_error}));
            continue;
        };
        let alts: Vec<Value> = u.streaming.iter().flat_map(|s| s.alts.iter().filter(|x| x.ep_type == 1 && x.bytes_per_interval > 0).map(|x| json!({
            "alt": x.alt, "bytes_per_interval": x.bytes_per_interval,
            "MB_per_s_at_1_per_uframe": x.bytes_per_interval as f64 * 8000.0 / 1e6,
            "approx_fraction_of_hs_periodic_budget": x.bytes_per_interval as f64 / HS_PERIODIC_BYTES_PER_UFRAME,
        })).collect::<Vec<_>>()).collect();
        out.push(json!({
            "vid": format!("{:04x}", d.vid), "pid": format!("{:04x}", d.pid), "bus": d.bus, "address": d.address,
            "port_path": port_path_str(&d.port_path), "speed": d.speed, "serial": d.serial,
            "raw_config_len": d.raw_config.as_ref().map(|r| r.len()),
            "uvc": u.to_json(), "iso_alt_bandwidth": alts,
        }));
    }
    Ok(json!({"test": format!("rust_uvc_iso_list_{bname}"), "platform": platform(), "hostname": hostname(),
        "utc_started_unix": stamp(), "command": std::env::args().collect::<Vec<_>>().join(" "),
        "environment": env_json(b.name()), "enumerate_ms": enum_ms, "non_uvc_devices": non_uvc, "uvc_devices": out}))
}

fn ctrl_report(dev: &dyn Dev, u: &UvcInfo, a: &Args) -> Value {
    let vc = u.vc_interface as u16;
    let mut r = json!({});
    if let Some(ct) = u.camera_terminal_id {
        let idx = ((ct as u16) << 8) | vc;
        if let Some(e) = a.get("exposure-100us").and_then(|s| s.parse::<u32>().ok()) {
            r["ae_mode_set_manual_err"] = json!(dev.ctrl_out(RT_CLASS_IF_OUT, SET_CUR, (CT_AE_MODE as u16) << 8, idx, &[0x01]).err());
            r["exposure_set_err"] = json!(dev.ctrl_out(RT_CLASS_IF_OUT, SET_CUR, (CT_EXPOSURE_TIME_ABSOLUTE as u16) << 8, idx, &e.to_le_bytes()).err());
        }
        r["ae_mode_cur"] = json!(dev.ctrl_in(RT_CLASS_IF_IN, GET_CUR, (CT_AE_MODE as u16) << 8, idx, 1).ok());
        r["exposure_100us_cur"] = json!(dev.ctrl_in(RT_CLASS_IF_IN, GET_CUR, (CT_EXPOSURE_TIME_ABSOLUTE as u16) << 8, idx, 4).ok().filter(|b| b.len() == 4).map(|b| u32::from_le_bytes([b[0], b[1], b[2], b[3]])));
    }
    if let Some(pu) = u.processing_unit_id {
        let idx = ((pu as u16) << 8) | vc;
        if let Some(k) = a.get("wb").and_then(|s| s.parse::<u16>().ok()) {
            r["wb_auto_off_err"] = json!(dev.ctrl_out(RT_CLASS_IF_OUT, SET_CUR, (PU_WB_TEMPERATURE_AUTO as u16) << 8, idx, &[0]).err());
            r["wb_set_err"] = json!(dev.ctrl_out(RT_CLASS_IF_OUT, SET_CUR, (PU_WB_TEMPERATURE as u16) << 8, idx, &k.to_le_bytes()).err());
        }
        r["wb_cur"] = json!(dev.ctrl_in(RT_CLASS_IF_IN, GET_CUR, (PU_WB_TEMPERATURE as u16) << 8, idx, 2).ok().filter(|b| b.len() == 2).map(|b| u16::from_le_bytes([b[0], b[1]])));
    }
    r
}

/// Fit host_time = a + b * device_ticks from (unwrapped STC, est host ns) pairs. Slope by least
/// squares; intercept set at the 2nd percentile of residuals (arrival delays are one-sided).
fn fit_dev_to_host(pairs: &[(f64, f64)]) -> Option<(f64, f64, Value)> {
    if pairs.len() < 20 {
        return None;
    }
    let n = pairs.len() as f64;
    let mx = pairs.iter().map(|p| p.0).sum::<f64>() / n;
    let my = pairs.iter().map(|p| p.1).sum::<f64>() / n;
    let sxy: f64 = pairs.iter().map(|p| (p.0 - mx) * (p.1 - my)).sum();
    let sxx: f64 = pairs.iter().map(|p| (p.0 - mx).powi(2)).sum();
    let b = sxy / sxx;
    let mut res: Vec<f64> = pairs.iter().map(|p| p.1 - (my + b * (p.0 - mx))).collect();
    res.sort_by(|x, y| x.partial_cmp(y).unwrap());
    let q = |f: f64| res[((res.len() - 1) as f64 * f) as usize];
    let a = my - b * mx + q(0.02);
    Some((a, b, json!({"n": pairs.len(), "ns_per_tick": b, "implied_device_clock_hz": 1e9 / b,
        "residual_ns_p02": q(0.02), "residual_ns_p50": q(0.5), "residual_ns_p98": q(0.98)})))
}

/// Process CPU time (user + kernel) in ns: GetProcessTimes on Windows, getrusage elsewhere.
fn process_cpu_ns() -> i64 {
    #[cfg(windows)]
    unsafe {
        use windows::Win32::Foundation::FILETIME;
        use windows::Win32::System::Threading::{GetCurrentProcess, GetProcessTimes};
        let (mut c, mut e, mut k, mut u) = (FILETIME::default(), FILETIME::default(), FILETIME::default(), FILETIME::default());
        if GetProcessTimes(GetCurrentProcess(), &mut c, &mut e, &mut k, &mut u).is_ok() {
            let f = |t: FILETIME| (((t.dwHighDateTime as u64) << 32) | t.dwLowDateTime as u64) as i64 * 100;
            return f(k) + f(u);
        }
        -1
    }
    #[cfg(not(windows))]
    unsafe {
        let mut r: libc::rusage = std::mem::zeroed();
        if libc::getrusage(libc::RUSAGE_SELF, &mut r) == 0 {
            let tv = |t: libc::timeval| t.tv_sec as i64 * 1_000_000_000 + t.tv_usec as i64 * 1000;
            return tv(r.ru_utime) + tv(r.ru_stime);
        }
        -1
    }
}

fn cmd_stream(a: &Args) -> Res<Value> {
    let bname = a.get("backend").unwrap_or("rawusb").to_string();
    let b = make_backend(&bname)?;
    let vid = a.hex16("vid").ok_or("--vid required (hex)")?;
    let pid = a.hex16("pid").ok_or("--pid required (hex)")?;
    let port: Option<Vec<u8>> = a.get("port").map(|s| s.split('.').filter_map(|x| x.parse().ok()).collect());
    let (w, h, fps) = (a.num("width", 1280u16), a.num("height", 720u16), a.num("fps", 30u32));
    let seconds: f64 = a.num("seconds", 10.0);
    let policy = AltPolicy::parse(a.get("alt").unwrap_or("device"))?;
    let nx = a.get("xfers").or(a.get("transfers")).and_then(|s| s.parse().ok()).unwrap_or(8usize);
    let np = a.get("pkts").or(a.get("packets")).and_then(|s| s.parse().ok()).unwrap_or(32usize);
    let save_samples: usize = a.num("save-samples", 1);
    let out = a.get("out").map(PathBuf::from).unwrap_or_else(|| { let p = default_out(&format!("rust_uvc_iso_stream_{bname}")); let n = format!("{}_{vid:04x}_{pid:04x}", p.file_name().unwrap().to_string_lossy()); p.with_file_name(n) });
    std::fs::create_dir_all(&out).map_err(|e| e.to_string())?;
    let mut res = json!({"test": format!("rust_uvc_iso_stream_{bname}"), "platform": platform(), "hostname": hostname(),
        "utc_started_unix": stamp(), "command": std::env::args().collect::<Vec<_>>().join(" "),
        "environment": env_json(b.name()),
        "settings": {"vid": format!("{vid:04x}"), "pid": format!("{pid:04x}"), "width": w, "height": h, "fps": fps,
                     "alt_policy": format!("{policy:?}"), "xfers": nx, "pkts_per_xfer": np, "seconds": seconds, "save_samples": save_samples,
                     "exposure_100us": a.get("exposure-100us"), "wb": a.get("wb")}});
    let fail = |mut res: Value, out: &PathBuf, stage: &str, e: String| -> Res<Value> {
        res["error"] = json!({"stage": stage, "message": e});
        let _ = std::fs::write(out.join("summary.json"), serde_json::to_string_pretty(&res).unwrap());
        Err(format!("{stage}: {e}"))
    };

    #[cfg(windows)]
    if let Some(inst) = a.get("sof-instance") {
        res["sof_calibration_before"] = winsof::calibrate(inst, 400);
    }

    let dev = match b.open(vid, pid, a.get("serial"), port.as_deref()) {
        Ok(d) => d,
        Err(e) => return fail(res, &out, "open", e),
    };
    let summ = dev.summary();
    res["device"] = json!({"bus": summ.bus, "address": summ.address, "port_path": port_path_str(&summ.port_path), "speed": summ.speed, "serial": summ.serial});
    let raw = match dev.raw_config().or_else(|e| summ.raw_config.clone().ok_or(e)) {
        Ok(r) => r,
        Err(e) => return fail(res, &out, "raw_config", e),
    };
    let Some(u) = UvcInfo::parse(&raw) else { return fail(res, &out, "parse", "no UVC VC interface".into()) };
    res["device"]["dwClockFrequency"] = json!(u.clock_frequency);
    res["device"]["bcdUVC"] = json!(format!("{:x}", u.bcd_uvc));
    let Some((vs, fmt, fr)) = u.find_mjpeg(w, h) else { return fail(res, &out, "format", format!("no MJPEG {w}x{h}")) };
    let (vs, fmt, fr) = (vs.clone(), fmt.clone(), fr.clone());
    let want = (10_000_000f64 / fps as f64).round() as u32;
    let interval = if fr.continuous { want } else { *fr.intervals.iter().min_by_key(|&&i| (i as i64 - want as i64).abs()).unwrap_or(&fr.default_interval) };

    if let Err(e) = dev.claim(u.vc_interface) { return fail(res, &out, "claim_vc", e) }
    if let Err(e) = dev.claim(vs.interface) { return fail(res, &out, "claim_vs", e) }
    let _ = dev.set_alt(vs.interface, 0);
    res["controls"] = ctrl_report(dev.as_ref(), &u, a);

    // ---- probe / commit (UVC 1.5 §4.3.1.1) ----
    let plen = u.probe_len();
    let pc = ProbeCommit { bm_hint: 1, format_index: fmt.index, frame_index: fr.index, frame_interval: interval, ..Default::default() };
    let t0 = hostclock::host_ns();
    if let Err(e) = dev.ctrl_out(RT_CLASS_IF_OUT, SET_CUR, (VS_PROBE as u16) << 8, vs.interface as u16, &pc.to_bytes(plen)) { return fail(res, &out, "probe_set", e) }
    let got = match dev.ctrl_in(RT_CLASS_IF_IN, GET_CUR, (VS_PROBE as u16) << 8, vs.interface as u16, plen) { Ok(g) => g, Err(e) => return fail(res, &out, "probe_get", e) };
    let neg = ProbeCommit::from_bytes(&got);
    if let Err(e) = dev.ctrl_out(RT_CLASS_IF_OUT, SET_CUR, (VS_COMMIT as u16) << 8, vs.interface as u16, &got) { return fail(res, &out, "commit", e) }
    res["probe_commit"] = json!({"requested": pc.to_json(), "negotiated": neg.to_json(), "len": plen, "ms": (hostclock::host_ns() - t0) as f64 / 1e6});

    // ---- app-controlled alternate setting (= bandwidth reservation) ----
    let Some(alt) = policy.choose(&vs.alts, neg.max_payload_transfer_size).cloned() else { return fail(res, &out, "alt", "no iso alt setting".into()) };
    res["alt_selected"] = json!({"alt": alt.alt, "bytes_per_interval": alt.bytes_per_interval, "device_requested_payload": neg.max_payload_transfer_size,
        "all_iso_alts": vs.alts.iter().filter(|x| x.ep_type == 1).map(|x| json!([x.alt, x.bytes_per_interval])).collect::<Vec<_>>()});
    if let Err(e) = dev.set_alt(vs.interface, alt.alt) { return fail(res, &out, "set_alt", e) }

    let svc_ns: i64 = {
        let base = if summ.speed == "Full" || summ.speed == "Low" { 1_000_000 } else { 125_000 };
        base << (alt.b_interval.max(1) - 1).min(15)
    };
    let max_frame = (neg.max_video_frame_size.max(fr.max_frame_buffer).max(w as u32 * h as u32 * 2)) as usize;
    let asm = Arc::new(Mutex::new(Assembler::new(max_frame)));
    let (tx, rx) = mpsc::channel::<AssembledFrame>();
    let tx = Mutex::new(tx);
    let asm2 = asm.clone();
    let xfer_stats = Arc::new(Mutex::new((0u64, 0u64, 0u64))); // transfers, packets, packets_with_err
    let xs2 = xfer_stats.clone();
    // Debug aid: UVC_ISO_DUMP_PKTS=N prints the first N non-empty packets (index, length, status,
    // first 16 bytes) to stderr.
    let dump_left = Arc::new(Mutex::new(std::env::var("UVC_ISO_DUMP_PKTS").ok().and_then(|v| v.parse::<usize>().ok()).unwrap_or(0)));
    let sink: IsoSink = Arc::new(move |host: i64, buf: &[u8], lens: &[(u32, bool)], stride: usize| {
        {
            let mut left = dump_left.lock().unwrap();
            if *left > 0 {
                for (i, (len, ok)) in lens.iter().enumerate() {
                    if *len > 0 && *left > 0 {
                        *left -= 1;
                        let off = i * stride;
                        let b = &buf[off.min(buf.len())..(off + 16).min(buf.len())];
                        eprintln!("pkt {i:>3}/{} len={len} ok={ok} stride={stride} buflen={} bytes={:02x?}", lens.len(), buf.len(), b);
                    }
                }
            }
        }
        let mut done = vec![];
        let mut a = asm2.lock().unwrap();
        let n = lens.len() as i64;
        for (i, (len, ok)) in lens.iter().enumerate() {
            let off = i * stride;
            let l = (*len as usize).min(stride);
            let est = host - (n - 1 - i as i64) * svc_ns;
            if *ok && off + l <= buf.len() {
                a.push(&buf[off..off + l], host, est, &mut done);
            }
        }
        drop(a);
        let mut s = xs2.lock().unwrap();
        s.0 += 1;
        s.1 += n as u64;
        s.2 += lens.iter().filter(|x| !x.1).count() as u64;
        drop(s);
        let tx = tx.lock().unwrap();
        for f in done {
            let _ = tx.send(f);
        }
    });
    let t_start = hostclock::host_ns();
    let cpu_start = process_cpu_ns();
    let stream = match dev.start_iso(alt.ep_addr, alt.bytes_per_interval as usize, np, nx, sink) { Ok(s) => s, Err(e) => { let _ = dev.set_alt(vs.interface, 0); return fail(res, &out, "start_iso", e) } };
    let deadline = Instant::now() + Duration::from_secs_f64(seconds);
    let mut frames: Vec<AssembledFrame> = vec![];
    let mut first_frame_ns = None;
    let mut saved = 0usize;
    let mut meta = vec![];
    // --raw-mjpeg FILE: every assembled frame's bytes, concatenated in frames_*.jsonl order
    // (offsets = running sum of payload_bytes), for an offline decode check.
    let mut raw_out = match a.get("raw-mjpeg") {
        Some(p) => Some(std::io::BufWriter::new(std::fs::File::create(p).map_err(|e| format!("--raw-mjpeg {p}: {e}"))?)),
        None => None,
    };
    while Instant::now() < deadline {
        match rx.recv_timeout(Duration::from_millis(200)) {
            Ok(mut f) => {
                first_frame_ns.get_or_insert(hostclock::host_ns());
                let (soi, eoi) = jpeg_markers(&f.data);
                // skip the first 30 frames (exposure settling) unless the run is too short to reach them
                if saved < save_samples && soi && eoi && !f.err && (f.seq >= 30 || seconds < 2.0) {
                    let _ = std::fs::write(out.join(format!("sample_{saved}.jpg")), &f.data);
                    saved += 1;
                }
                if let Some(w) = raw_out.as_mut() {
                    let _ = w.write_all(&f.data);
                }
                meta.push((f.data.len(), soi, eoi));
                f.data = vec![]; // keep memory bounded
                frames.push(f);
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {}
            Err(_) => break,
        }
    }
    let (cpu_end, t_end) = (process_cpu_ns(), hostclock::host_ns());
    if let Some(mut w) = raw_out.take() {
        let _ = w.flush();
    }
    res["raw_mjpeg"] = json!(a.get("raw-mjpeg"));
    res["stream_stats"] = stream.stop();
    let _ = dev.set_alt(vs.interface, 0);
    #[cfg(windows)]
    if let Some(inst) = a.get("sof-instance") {
        // The WinUSB file stays open until the device handle AND the backend context are gone
        // (rawusb's Context keeps the handle registered with its IOCP); dropping only `dev` gave
        // "CreateFileW ... Access is denied" here in phase 2. Drop both, then retry briefly.
        drop(dev);
        drop(b);
        let mut cal = winsof::calibrate(inst, 400);
        for i in 0..10 {
            if cal.get("error").is_none() {
                break;
            }
            std::thread::sleep(Duration::from_millis(100));
            cal = winsof::calibrate(inst, 400);
            cal["retries"] = json!(i + 1);
        }
        res["sof_calibration_after"] = cal;
    }

    // ---- device clock -> host clock from SCR (STC) vs estimated packet arrival ----
    let hz = if neg.clock_frequency != 0 { neg.clock_frequency } else { u.clock_frequency } as f64;
    let mut pairs = vec![];
    let mut unwrap_base = 0i64;
    let mut last_stc: Option<u32> = None;
    let mut stc_un: Vec<Option<f64>> = vec![];
    for f in &frames {
        if let Some((stc, _sof)) = f.first_scr {
            if let Some(l) = last_stc {
                if stc < l && l - stc > 0x8000_0000 {
                    unwrap_base += 1 << 32;
                }
            }
            last_stc = Some(stc);
            let x = (unwrap_base + stc as i64) as f64;
            pairs.push((x, f.first_packet_est_host_ns as f64));
            stc_un.push(Some(x));
        } else {
            stc_un.push(None);
        }
    }
    let fit = fit_dev_to_host(&pairs);
    res["device_clock_fit"] = fit.as_ref().map(|f| f.2.clone()).unwrap_or(Value::Null);
    res["device_clock_fit_note"] = json!("host = a + b*STC; STC from first SCR of each frame, host = estimated (micro)frame time of that packet (transfer completion - packets_after*service_interval); intercept at 2nd percentile residual. PTS mapped with same fit (PTS-STC difference taken modulo 2^32).");

    let tag = format!("{:04x}_{:04x}", vid, pid);
    let mut fl = std::io::BufWriter::new(std::fs::File::create(out.join(format!("frames_{tag}.jsonl"))).map_err(|e| e.to_string())?);
    let key = format!("usb:{:04x}:{:04x}:bus{}:port{}:serial={}", vid, pid, summ.bus, port_path_str(&summ.port_path), summ.serial.clone().unwrap_or_default());
    let mut lat = vec![];
    for (i, f) in frames.iter().enumerate() {
        let (len, soi, eoi) = meta[i];
        let pts_host = match (fit.as_ref(), f.pts, f.first_scr, stc_un[i]) {
            (Some((a0, b0, _)), Some(pts), Some((stc, _)), Some(xu)) => {
                let d = pts.wrapping_sub(stc) as i32 as f64; // PTS precedes STC: negative ticks
                Some((a0 + b0 * (xu + d)) as i64)
            }
            _ => None,
        };
        if let Some(p) = pts_host {
            lat.push((f.last_xfer_host_ns - p) as f64 / 1e6);
        }
        let row = json!({
            "camera_key": key, "backend": format!("uvc_iso-{bname}"), "seq": f.seq,
            "host_arrival_ns": f.last_xfer_host_ns,
            "os_timestamp_ns": pts_host,
            "os_timestamp_source": if pts_host.is_some() {"UVC PTS mapped to host clock via SCR-STC/packet-arrival fit (uvc_iso)"} else {"none"},
            "uvc_pts": f.pts, "uvc_scr_stc": f.first_scr.map(|s| s.0), "uvc_scr_sof": f.first_scr.map(|s| s.1),
            "device_clock_hz": hz as u64, "payload_bytes": len, "is_valid_jpeg": soi && eoi && !f.err,
            "first_payload_host_ns": f.first_xfer_host_ns, "first_packet_est_host_ns": f.first_packet_est_host_ns,
            "last_packet_est_host_ns": f.last_packet_est_host_ns, "last_scr_stc": f.last_scr.map(|s| s.0), "last_scr_sof": f.last_scr.map(|s| s.1),
            "payloads": f.payloads, "uvc_err": f.err, "ended_by_eof": f.ended_by_eof,
        });
        writeln!(fl, "{row}").map_err(|e| e.to_string())?;
    }
    fl.flush().map_err(|e| e.to_string())?;
    let a_ = asm.lock().unwrap();
    let x = xfer_stats.lock().unwrap();
    let nvalid = meta.iter().filter(|m| m.1 && m.2).count();
    let arr: Vec<i64> = frames.iter().map(|f| f.last_xfer_host_ns).collect();
    let fps_meas = if arr.len() > 31 { (arr.len() - 31) as f64 / ((arr[arr.len() - 1] - arr[30]) as f64 / 1e9) } else { 0.0 };
    lat.sort_by(|x, y| x.partial_cmp(y).unwrap());
    // Frame-loss detectors. `seq` is assigned by the Assembler, so seq gaps are 0 by construction;
    // missing frames show as PTS steps of >= 1.5 frame periods (device clock) or host-arrival
    // intervals >= 1.5 periods.
    let period_ticks = hz * interval as f64 / 1e7;
    let pts_v: Vec<u32> = frames.iter().filter_map(|f| f.pts).collect();
    let pts_d: Vec<f64> = pts_v.windows(2).map(|w| w[1].wrapping_sub(w[0]) as f64).collect();
    let pts_gaps = pts_d.iter().filter(|d| **d >= 1.5 * period_ticks).count();
    let pts_missing: f64 = pts_d.iter().filter(|d| **d >= 1.5 * period_ticks).map(|d| (d / period_ticks).round() - 1.0).sum();
    let period_ns = interval as f64 * 100.0;
    let arr_gaps = arr.windows(2).filter(|w| (w[1] - w[0]) as f64 >= 1.5 * period_ns).count();
    let wall = (t_end - t_start) as f64;
    res["results"] = json!({
        "frames": frames.len(), "valid_jpeg": nvalid, "fps_host_after_skip30": fps_meas,
        "time_to_first_frame_ms": first_frame_ns.map(|t| (t - t_start) as f64 / 1e6),
        "payloads": a_.stats_payloads, "bad_headers": a_.stats_bad_headers, "empty_packets": a_.stats_empty_packets,
        "err_flag_payloads": a_.stats_err_flag, "payloads_without_eoh_bit": a_.stats_no_eoh, "overflows": a_.stats_overflow, "discarded_partial": a_.stats_discarded_partial,
        "transfers": x.0, "packets": x.1, "packets_with_error_status": x.2,
        "latency_arrival_minus_pts_ms": if lat.is_empty() { Value::Null } else { json!({"min": lat[0], "p50": lat[lat.len()/2], "max": lat[lat.len()-1]}) },
        "frames_file": format!("frames_{tag}.jsonl"),
        "pts_gaps_ge_1p5_period": pts_gaps, "pts_missing_frames_est": pts_missing,
        "pts_delta_ticks_min": pts_d.iter().cloned().fold(f64::INFINITY, f64::min), "pts_delta_ticks_max": pts_d.iter().cloned().fold(0f64, f64::max),
        "expected_period_ticks": period_ticks,
        "host_arrival_gaps_ge_1p5_period": arr_gaps,
        "cpu": {"process_cpu_ns": cpu_end - cpu_start, "wall_ns": wall, "percent_of_one_core": if cpu_start >= 0 && wall > 0.0 { 100.0 * (cpu_end - cpu_start) as f64 / wall } else { -1.0 },
                "method": if cfg!(windows) {"GetProcessTimes (kernel+user) delta over start_iso..stop window"} else {"getrusage(RUSAGE_SELF) delta"}},
    });
    res["out_dir"] = json!(out.display().to_string());
    Ok(res)
}

fn main() {
    let a = Args::parse();
    let cmd = a.1.first().cloned().unwrap_or_else(|| "list".into());
    let r = match cmd.as_str() {
        "list" | "descriptors" => cmd_list(&a),
        "stream" | "capture" => cmd_stream(&a),
        #[cfg(windows)]
        "sof-calib" => a.get("instance").map(|i| Ok(json!({"test": "rust_uvc_iso_sof_calib", "platform": platform(), "hostname": hostname(), "result": winsof::calibrate(i, 1000)}))).unwrap_or(Err("--instance required".into())),
        other => Err(format!("unknown command {other}")),
    };
    match r {
        Ok(v) => {
            let out = a.get("out").map(PathBuf::from)
                .or_else(|| v["out_dir"].as_str().map(PathBuf::from))
                .unwrap_or_else(|| default_out(v["test"].as_str().unwrap_or("rust_uvc_iso")));
            let _ = std::fs::create_dir_all(&out);
            let p = out.join("summary.json");
            std::fs::write(&p, serde_json::to_string_pretty(&v).unwrap()).unwrap();
            println!("{}", p.display());
        }
        Err(e) => {
            eprintln!("error: {e}");
            std::process::exit(1);
        }
    }
}
