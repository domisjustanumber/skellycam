//! nokhwa_probe: does nokhwa 0.10.11 deliver the camera's native MJPEG bytes without decoding,
//! what timestamp does it attach, and what device identity does it expose?
//!
//! Usage (from research/usb_cameras/rust):
//!   cargo run --release -p nokhwa_probe -- list [--out DIR]
//!   cargo run --release -p nokhwa_probe -- capture --cameras 0,1 --width 1280 --height 720 --fps 30
//!        --seconds 20 [--exposure -7 --wb 4000] [--decode-every 30] [--save-samples 1]
//!        [--coinit mta|none] [--out DIR]
//! On the shared Windows machine wrap capture in camlock:
//!   uv run --script research/usb_cameras/tools/camlock.py -- research/usb_cameras/rust/build/release/nokhwa_probe.exe capture ...
//!
//! Output: DIR/summary.json (+ DIR/frames_<cam>.jsonl per camera, README frame-log schema,
//! + DIR/sample_<cam>_<n>.jpg). Default DIR = research/usb_cameras/results/<platform>/<host>/rust_nokhwa_<mode>/<utc>.

mod hostclock;
#[cfg(windows)]
mod wincontrols;

use nokhwa::pixel_format::RgbFormat;
use nokhwa::utils::{
    ApiBackend, CameraFormat, CameraIndex, FrameFormat, KnownCameraControl, RequestedFormat,
    RequestedFormatType, Resolution,
};
use nokhwa::Camera;
use serde_json::{json, Value};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

static CAMERA_MATCH: std::sync::OnceLock<String> = std::sync::OnceLock::new();

fn platform() -> &'static str {
    match std::env::consts::OS {
        "windows" => "windows",
        "linux" => "linux",
        "macos" => "macos",
        o => o,
    }
}

fn backend_name() -> &'static str {
    match std::env::consts::OS {
        "windows" => "nokhwa-msmf",
        "linux" => "nokhwa-v4l2",
        "macos" => "nokhwa-avfoundation",
        _ => "nokhwa",
    }
}

fn hostname() -> String {
    // Same spelling as `hostname` / Python socket.gethostname() so results land next to other agents'.
    std::process::Command::new("hostname")
        .output()
        .ok()
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().split('.').next().unwrap_or("").to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| std::env::var("COMPUTERNAME").unwrap_or_else(|_| "unknown".into()))
}

fn os_build() -> String {
    let out = if cfg!(windows) {
        std::process::Command::new("cmd").args(["/c", "ver"]).output()
    } else {
        std::process::Command::new("uname").args(["-a"]).output()
    };
    out.map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_default()
}

fn utc_stamp() -> (String, String) {
    // Minimal UTC formatter (no chrono dependency).
    let s = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs() as i64;
    let days = s.div_euclid(86400);
    let sod = s.rem_euclid(86400);
    // civil from days (Howard Hinnant)
    let z = days + 719468;
    let era = z.div_euclid(146097);
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    let (hh, mm, ss) = (sod / 3600, (sod / 60) % 60, sod % 60);
    (
        format!("{y:04}-{m:02}-{d:02}T{hh:02}:{mm:02}:{ss:02}Z"),
        format!("{y:04}{m:02}{d:02}T{hh:02}{mm:02}{ss:02}Z"),
    )
}

fn default_out(mode: &str, stamp: &str) -> PathBuf {
    // binary may be run from repo root or from research/usb_cameras/rust
    let cwd = std::env::current_dir().unwrap();
    let base = if cwd.join("research/usb_cameras").is_dir() {
        cwd.join("research/usb_cameras")
    } else if cwd.join("../results").is_dir() || cwd.ends_with("rust") {
        cwd.join("..")
    } else {
        cwd.clone()
    };
    base.join("results")
        .join(platform())
        .join(hostname())
        .join(format!("rust_nokhwa_{mode}"))
        .join(stamp)
}

struct Args {
    mode: String,
    cameras: Option<Vec<u32>>,
    width: u32,
    height: u32,
    fps: u32,
    seconds: f64,
    exposure: Option<i32>,
    wb: Option<i32>,
    gain: Option<i32>,
    decode_every: u64,
    save_samples: u32,
    coinit: String,
    out: Option<PathBuf>,
    use_frame_raw: bool,
}

fn parse_args() -> Args {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    let mut a = Args {
        mode: argv.first().cloned().unwrap_or_else(|| "list".into()),
        cameras: None,
        width: 1280,
        height: 720,
        fps: 30,
        seconds: 20.0,
        exposure: None,
        wb: None,
        gain: None,
        decode_every: 30,
        save_samples: 1,
        coinit: "mta".into(),
        out: None,
        use_frame_raw: false,
    };
    let mut i = 1;
    let val = |i: usize| -> String {
        argv.get(i + 1).cloned().unwrap_or_else(|| {
            eprintln!("missing value for {}", argv[i]);
            std::process::exit(2)
        })
    };
    while i < argv.len() {
        match argv[i].as_str() {
            "--cameras" => {
                let v = val(i);
                if let Some(m) = v.strip_prefix("match:") {
                    // select by substring(s) of the MF symlink / V4L2 bus / AVF uniqueID, e.g. match:vid_046d&pid_085c,vid_1532
                    let _ = CAMERA_MATCH.set(m.to_ascii_lowercase());
                } else if v != "all" {
                    a.cameras = Some(v.split(',').map(|s| s.trim().parse().expect("camera index")).collect());
                }
                i += 1;
            }
            "--width" => { a.width = val(i).parse().unwrap(); i += 1; }
            "--height" => { a.height = val(i).parse().unwrap(); i += 1; }
            "--fps" => { a.fps = val(i).parse().unwrap(); i += 1; }
            "--seconds" => { a.seconds = val(i).parse().unwrap(); i += 1; }
            "--exposure" => { a.exposure = Some(val(i).parse().unwrap()); i += 1; }
            "--wb" => { a.wb = Some(val(i).parse().unwrap()); i += 1; }
            "--gain" => { a.gain = Some(val(i).parse().unwrap()); i += 1; }
            "--decode-every" => { a.decode_every = val(i).parse().unwrap(); i += 1; }
            "--save-samples" => { a.save_samples = val(i).parse().unwrap(); i += 1; }
            "--coinit" => { a.coinit = val(i); i += 1; }
            "--out" => { a.out = Some(PathBuf::from(val(i))); i += 1; }
            "--frame-raw" => { a.use_frame_raw = true; }
            "-h" | "--help" => {
                println!("see header of research/usb_cameras/rust/nokhwa_probe/src/main.rs");
                std::process::exit(0);
            }
            other => {
                eprintln!("unknown arg {other}");
                std::process::exit(2);
            }
        }
        i += 1;
    }
    a
}

fn environment() -> Value {
    json!({
        "os": std::env::consts::OS,
        "arch": std::env::consts::ARCH,
        "os_build": os_build(),
        "rustc": option_env!("RUSTC_VERSION_STR").unwrap_or("see build_info.json"),
        "nokhwa": "0.10.11",
        "nokhwa_features": ["input-native"],
        "nokhwa_default_features": false,
        "host_clock": hostclock::host_clock_name(),
        "qpc_frequency_hz": hostclock::qpc_freq(),
        "profile": if cfg!(debug_assertions) { "debug" } else { "release" },
    })
}

fn sanitize(s: &str) -> String {
    s.chars().map(|c| if c.is_ascii_alphanumeric() { c } else { '_' }).collect()
}

fn jpeg_markers(b: &[u8]) -> (bool, bool, usize) {
    let soi = b.len() >= 2 && b[0] == 0xFF && b[1] == 0xD8;
    // EOI may be followed by padding on some cameras: search the last 64 bytes.
    let tail = &b[b.len().saturating_sub(64)..];
    let mut eoi_pos = None;
    for k in (0..tail.len().saturating_sub(1)).rev() {
        if tail[k] == 0xFF && tail[k + 1] == 0xD9 {
            eoi_pos = Some(tail.len() - k - 2);
            break;
        }
    }
    (soi, eoi_pos.is_some(), eoi_pos.unwrap_or(usize::MAX))
}

fn try_decode(b: &[u8]) -> Result<(usize, usize), String> {
    let mut d = zune_jpeg::JpegDecoder::new(b);
    d.decode().map_err(|e| format!("{e:?}"))?;
    let (w, h) = d.dimensions().unwrap_or((0, 0));
    Ok((w, h))
}

fn stats(v: &[f64]) -> Value {
    if v.is_empty() {
        return Value::Null;
    }
    let mut s = v.to_vec();
    s.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let n = s.len() as f64;
    let mean = s.iter().sum::<f64>() / n;
    let sd = (s.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / n).sqrt();
    let p = |q: f64| s[((q * (s.len() - 1) as f64).round() as usize).min(s.len() - 1)];
    json!({"n": s.len(), "mean": mean, "std": sd, "min": s[0], "p01": p(0.01), "p50": p(0.5), "p99": p(0.99), "max": s[s.len()-1]})
}

fn list_mode(args: &Args) -> Value {
    let (utc, stamp) = utc_stamp();
    let out = args.out.clone().unwrap_or_else(|| default_out("list", &stamp));
    std::fs::create_dir_all(&out).unwrap();
    let t0 = hostclock::host_ns();
    let infos = nokhwa::query(ApiBackend::Auto);
    let query_ms = (hostclock::host_ns() - t0) as f64 / 1e6;
    let mut cams = vec![];
    match &infos {
        Ok(list) => {
            for info in list {
                let mut c = json!({
                    "index": info.index().to_string(),
                    "human_name": info.human_name(),
                    "description": info.description(),
                    "misc": info.misc(),
                });
                // Open each to enumerate formats (opens the device; needs camlock).
                let req = RequestedFormat::new::<RgbFormat>(RequestedFormatType::None);
                match Camera::new(info.index().clone(), req) {
                    Ok(mut cam) => {
                        let fmts = cam.compatible_camera_formats();
                        c["formats"] = match fmts {
                            Ok(f) => json!(f.iter().map(|f| format!("{}x{}@{} {}", f.width(), f.height(), f.frame_rate(), f.format())).collect::<Vec<_>>()),
                            Err(e) => json!(format!("error: {e}")),
                        };
                        c["opened_info_misc"] = json!(cam.info().misc());
                        let ctrls: Vec<Value> = [KnownCameraControl::Exposure, KnownCameraControl::WhiteBalance, KnownCameraControl::Gain]
                            .iter()
                            .map(|k| match cam.camera_control(*k) {
                                Ok(cc) => json!({"control": k.to_string(), "value": cc.value().to_string(), "flags": format!("{:?}", cc.flag())}),
                                Err(e) => json!({"control": k.to_string(), "error": e.to_string()}),
                            })
                            .collect();
                        c["controls"] = json!(ctrls);
                    }
                    Err(e) => c["open_error"] = json!(e.to_string()),
                }
                cams.push(c);
            }
        }
        Err(e) => cams.push(json!({"query_error": e.to_string()})),
    }
    let res = json!({
        "test": "rust_nokhwa_list",
        "platform": platform(),
        "hostname": hostname(),
        "utc_started": utc,
        "command": std::env::args().collect::<Vec<_>>().join(" "),
        "environment": environment(),
        "query_ms": query_ms,
        "cameras": cams,
    });
    std::fs::write(out.join("summary.json"), serde_json::to_string_pretty(&res).unwrap()).unwrap();
    println!("{}", out.join("summary.json").display());
    res
}

struct CamResult {
    summary: Value,
}

fn capture_one(
    idx: u32,
    args: &Args,
    out: &Path,
    coinit: &str,
    start_barrier: std::sync::Arc<std::sync::Barrier>,
) -> CamResult {
    let mut summary = json!({"index": idx});
    #[cfg(windows)]
    if coinit == "mta" {
        summary["coinit_hr"] = json!(wincontrols::co_init_mta());
    }
    let _ = coinit;
    let req_fmt = CameraFormat::new(Resolution::new(args.width, args.height), FrameFormat::MJPEG, args.fps);
    summary["requested_format"] = json!(format!("{}x{}@{} MJPEG (RequestedFormatType::Exact)", args.width, args.height, args.fps));
    let t_open0 = hostclock::host_ns();
    let cam = Camera::new(
        CameraIndex::Index(idx),
        RequestedFormat::new::<RgbFormat>(RequestedFormatType::Exact(req_fmt)),
    );
    let mut cam = match cam {
        Ok(c) => c,
        Err(e) => {
            summary["open_error"] = json!(e.to_string());
            start_barrier.wait();
            return CamResult { summary };
        }
    };
    summary["open_ms"] = json!((hostclock::host_ns() - t_open0) as f64 / 1e6);
    let info = cam.info().clone();
    let key = info.misc();
    summary["camera_key"] = json!(key);
    summary["human_name"] = json!(info.human_name());
    let f = cam.camera_format();
    summary["actual_format"] = json!(format!("{}x{}@{} {}", f.width(), f.height(), f.frame_rate(), f.format()));
    let ctrls: Vec<Value> = [KnownCameraControl::Exposure, KnownCameraControl::WhiteBalance, KnownCameraControl::Gain]
        .iter()
        .map(|k| match cam.camera_control(*k) {
            Ok(cc) => json!({"control": k.to_string(), "value": cc.value().to_string(), "flags": format!("{:?}", cc.flag())}),
            Err(e) => json!({"control": k.to_string(), "error": e.to_string()}),
        })
        .collect();
    summary["controls_via_nokhwa_after_open"] = json!(ctrls);

    start_barrier.wait();
    let wall_before = hostclock::wall_ns();
    let host_before = hostclock::host_ns();
    if let Err(e) = cam.open_stream() {
        summary["open_stream_error"] = json!(e.to_string());
        return CamResult { summary };
    }
    let wall_after = hostclock::wall_ns();
    let host_after = hostclock::host_ns();
    // nokhwa MSMF sets stream_epoch = SystemTime::now() inside start_stream; bracket it.
    let epoch_mid_wall = (wall_before + wall_after) / 2;
    summary["open_stream_bracket"] = json!({"wall_before_ns": wall_before, "wall_after_ns": wall_after,
        "host_before_ns": host_before, "host_after_ns": host_after});

    let tag = sanitize(&format!("{}_{}", idx, info.human_name()));
    let mut fl = std::io::BufWriter::new(std::fs::File::create(out.join(format!("frames_{tag}.jsonl"))).unwrap());
    let deadline = Instant::now() + Duration::from_secs_f64(args.seconds);
    let mut seq: u64 = 0;
    let mut saved = 0u32;
    let mut n_soi = 0u64;
    let mut n_eoi = 0u64;
    let mut n_dec_ok = 0u64;
    let mut n_dec_try = 0u64;
    let mut n_err = 0u64;
    let mut errs: Vec<String> = vec![];
    let mut arrivals: Vec<i64> = vec![];
    let mut sizes: Vec<f64> = vec![];
    let mut call_ms: Vec<f64> = vec![];
    let mut age_ms: Vec<f64> = vec![];
    let mut implied_sample_time_s: Vec<f64> = vec![];
    let mut ts_present = 0u64;
    let mut dims = None;
    while Instant::now() < deadline {
        let t_call = hostclock::host_ns();
        let (bytes, ts): (Vec<u8>, Option<Duration>) = if args.use_frame_raw {
            match cam.frame_raw() {
                Ok(b) => (b.into_owned(), None),
                Err(e) => { n_err += 1; if errs.len() < 5 { errs.push(e.to_string()); } continue; }
            }
        } else {
            match cam.frame() {
                Ok(b) => (b.buffer().to_vec(), b.capture_timestamp()),
                Err(e) => { n_err += 1; if errs.len() < 5 { errs.push(e.to_string()); } continue; }
            }
        };
        let host = hostclock::host_ns();
        let wall = hostclock::wall_ns();
        let (soi, eoi, eoi_from_end) = jpeg_markers(&bytes);
        n_soi += soi as u64;
        n_eoi += eoi as u64;
        let mut decoded: Option<bool> = None;
        if args.decode_every > 0 && seq % args.decode_every == 0 {
            n_dec_try += 1;
            match try_decode(&bytes) {
                Ok(d) => { n_dec_ok += 1; decoded = Some(true); dims = Some(d); }
                Err(e) => { decoded = Some(false); if errs.len() < 5 { errs.push(format!("decode seq {seq}: {e}")); } }
            }
        }
        if saved < args.save_samples && soi && eoi {
            let _ = std::fs::write(out.join(format!("sample_{tag}_{saved}.jpg")), &bytes);
            saved += 1;
        }
        // nokhwa capture_timestamp is a UNIX wallclock Duration. Map it onto the host clock via
        // the "age" method: host_ts = host_now - (wall_now - capture_ts).
        let (cap_unix_ns, os_ts_host, implied) = match ts {
            Some(d) => {
                ts_present += 1;
                let c = d.as_nanos() as i64;
                let age = wall - c;
                age_ms.push(age as f64 / 1e6);
                let implied = c - epoch_mid_wall; // == MF llTimestamp*100 on Windows
                implied_sample_time_s.push(implied as f64 / 1e9);
                // Windows: nokhwa adds the raw MF sample time (QPC domain, observed in run
                // 20261025T180337Z) to a wallclock epoch, so the recoverable quantity is
                // implied = capture_ts - epoch = MF llTimestamp*100 ns, already on the QPC clock.
                // Linux/macOS: nokhwa converts a monotonic timestamp to wallclock by the age method,
                // so we invert the age method.
                let os_host = if cfg!(windows) { implied } else { host - age };
                (Some(c), Some(os_host), Some(implied))
            }
            None => (None, None, None),
        };
        let rec = json!({
            "camera_key": key,
            "backend": backend_name(),
            "seq": seq,
            "host_arrival_ns": host,
            "os_timestamp_ns": os_ts_host,
            "os_timestamp_source": if ts.is_none() { "none" } else if cfg!(windows) { "MF IMFSample time (llTimestamp*100ns) recovered as nokhwa capture_ts - stream_epoch; QPC domain" } else { "nokhwa Buffer::capture_timestamp (wallclock) mapped back to host clock by inverse age method" },
            "uvc_pts": Value::Null, "uvc_scr_stc": Value::Null, "uvc_scr_sof": Value::Null, "device_clock_hz": Value::Null,
            "payload_bytes": bytes.len(),
            "is_valid_jpeg": if decoded == Some(false) { false } else { soi && eoi },
            "decoded": decoded,
            "eoi_bytes_from_end": if eoi { json!(eoi_from_end) } else { Value::Null },
            "wall_arrival_ns": wall,
            "nokhwa_capture_ts_unix_ns": cap_unix_ns,
            "implied_sample_time_ns": implied,
            "frame_call_ns": host - t_call,
        });
        writeln!(fl, "{}", rec).unwrap();
        arrivals.push(host);
        sizes.push(bytes.len() as f64);
        call_ms.push((host - t_call) as f64 / 1e6);
        seq += 1;
    }
    fl.flush().unwrap();
    let _ = cam.stop_stream();
    let skip = 30.min(arrivals.len());
    let intervals: Vec<f64> = arrivals[skip..].windows(2).map(|w| (w[1] - w[0]) as f64 / 1e6).collect();
    let dur_s = if arrivals.len() > skip + 1 { (arrivals[arrivals.len() - 1] - arrivals[skip]) as f64 / 1e9 } else { 0.0 };
    let fps = if dur_s > 0.0 { (arrivals.len() - skip - 1) as f64 / dur_s } else { 0.0 };
    summary["frames"] = json!(seq);
    summary["read_errors"] = json!(n_err);
    summary["errors_sample"] = json!(errs);
    summary["frames_with_soi"] = json!(n_soi);
    summary["frames_with_eoi"] = json!(n_eoi);
    summary["decode_attempted"] = json!(n_dec_try);
    summary["decode_ok"] = json!(n_dec_ok);
    summary["decoded_dimensions"] = json!(dims);
    summary["frames_with_capture_timestamp"] = json!(ts_present);
    summary["fps_host_arrival_after_skip30"] = json!(fps);
    summary["arrival_interval_ms"] = stats(&intervals);
    summary["payload_bytes"] = stats(&sizes);
    summary["frame_call_ms"] = stats(&call_ms);
    summary["capture_ts_age_ms_wall_minus_ts"] = stats(&age_ms);
    summary["implied_sample_time_s"] = stats(&implied_sample_time_s);
    summary["frames_file"] = json!(format!("frames_{tag}.jsonl"));
    CamResult { summary }
}

fn capture_mode(args: &Args) -> Value {
    let (utc, stamp) = utc_stamp();
    let n_cams_tag = args.cameras.as_ref().map(|c| c.iter().map(|x| x.to_string()).collect::<Vec<_>>().join("-")).unwrap_or("all".into());
    let out = args.out.clone().unwrap_or_else(|| default_out("capture", &format!("{stamp}_cams{n_cams_tag}_{}x{}", args.width, args.height)));
    std::fs::create_dir_all(&out).unwrap();
    let infos = nokhwa::query(ApiBackend::Auto).unwrap_or_default();
    let list: Vec<u32> = match &args.cameras {
        Some(v) => v.clone(),
        None => match CAMERA_MATCH.get() {
            Some(m) => infos.iter().enumerate()
                .filter(|(_, i)| m.split(',').any(|pat| i.misc().to_ascii_lowercase().contains(pat)))
                .map(|(k, _)| k as u32).collect(),
            None => (0..infos.len() as u32).collect(),
        },
    };
    if list.is_empty() {
        eprintln!("no cameras selected");
        std::process::exit(4);
    }
    let mut pre_controls = vec![];
    #[cfg(windows)]
    for &i in &list {
        if args.exposure.is_some() || args.wb.is_some() || args.gain.is_some() {
            if let Some(info) = infos.get(i as usize) {
                pre_controls.push(wincontrols::set_manual(&info.misc(), args.exposure, args.wb, args.gain));
            }
        }
    }
    let barrier = std::sync::Arc::new(std::sync::Barrier::new(list.len()));
    let mut handles = vec![];
    let args_ref: &'static Args = Box::leak(Box::new(Args { mode: args.mode.clone(), cameras: args.cameras.clone(), out: args.out.clone(), coinit: args.coinit.clone(), ..*args }));
    for &i in &list {
        let out = out.clone();
        let b = barrier.clone();
        let coinit = args.coinit.clone();
        handles.push(std::thread::spawn(move || capture_one(i, args_ref, &out, &coinit, b)));
    }
    let results: Vec<Value> = handles.into_iter().map(|h| match h.join() {
        Ok(r) => r.summary,
        Err(_) => json!({"thread_panic": true}),
    }).collect();
    let mut post_controls = vec![];
    #[cfg(windows)]
    for &i in &list {
        if let Some(info) = infos.get(i as usize) {
            post_controls.push(wincontrols::read_back(&info.misc()));
        }
    }
    let res = json!({
        "test": "rust_nokhwa_capture",
        "platform": platform(),
        "hostname": hostname(),
        "utc_started": utc,
        "command": std::env::args().collect::<Vec<_>>().join(" "),
        "environment": environment(),
        "settings": {"width": args.width, "height": args.height, "fps": args.fps, "seconds": args.seconds,
                     "exposure": args.exposure, "white_balance": args.wb, "gain": args.gain,
                     "decode_every": args.decode_every, "coinit": args.coinit, "api": if args.use_frame_raw {"frame_raw"} else {"frame"}},
        "query": infos.iter().map(|i| json!({"index": i.index().to_string(), "human_name": i.human_name(), "misc": i.misc()})).collect::<Vec<_>>(),
        "controls_set_before": pre_controls,
        "controls_read_after": post_controls,
        "cameras": results,
    });
    std::fs::write(out.join("summary.json"), serde_json::to_string_pretty(&res).unwrap()).unwrap();
    println!("{}", out.join("summary.json").display());
    res
}

impl Clone for Args {
    fn clone(&self) -> Self {
        Args { mode: self.mode.clone(), cameras: self.cameras.clone(), out: self.out.clone(), coinit: self.coinit.clone(), ..*self }
    }
}

fn main() {
    let args = parse_args();
    #[cfg(target_os = "macos")]
    {
        let (tx, rx) = std::sync::mpsc::channel();
        nokhwa::nokhwa_initialize(move |ok| { let _ = tx.send(ok); });
        let ok = rx.recv_timeout(Duration::from_secs(60)).unwrap_or(false);
        if !ok {
            eprintln!("camera permission not granted (System Settings > Privacy & Security > Camera)");
            std::process::exit(3);
        }
    }
    let res = match args.mode.as_str() {
        "list" => list_mode(&args),
        "capture" => capture_mode(&args),
        m => {
            eprintln!("unknown mode {m}; use list|capture");
            std::process::exit(2);
        }
    };
    let _ = res;
}
