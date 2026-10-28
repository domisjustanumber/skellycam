//! nusb_pr233_probe: can the nusb PR #233 isochronous API stream UVC MJPEG on Windows/WinUSB?
//! Same UVC logic as uvc_iso (src/uvc.rs included by path): GET_DESCRIPTOR -> parse -> probe/commit
//! -> alt -> iso IN transfers -> payload-header parse + frame assembly.
//! Build: cd research/usb_cameras/rust/nusb_pr233_probe && cargo build --release
//! Run:   nusb_pr233_probe --vid 046d --pid 0843 [--width 1280 --height 720 --fps 30] [--alt device|payload:N|N]
//!        [--seconds 10] [--queue 8] [--pkts 32] --out DIR        (wrap in tools/camlock.py)
#[path = "../../uvc_iso/src/uvc.rs"]
mod uvc;

use nusb::transfer::{ControlIn, ControlOut, ControlType, In, IsoLayout, IsoPacketStatus, Isochronous, Recipient, TransferError};
use nusb::MaybeFuture;
use serde_json::json;
use std::collections::HashMap;
use std::time::{Duration, Instant};
use uvc::*;

fn arg(m: &HashMap<String, String>, k: &str, d: &str) -> String {
    m.get(k).cloned().unwrap_or_else(|| d.to_string())
}

fn main() {
    let v: Vec<String> = std::env::args().skip(1).collect();
    let mut m = HashMap::new();
    for w in v.chunks(2) {
        if let [k, val] = w {
            m.insert(k.trim_start_matches("--").to_string(), val.clone());
        }
    }
    let out = std::path::PathBuf::from(arg(&m, "out", "nusb_pr233_out"));
    std::fs::create_dir_all(&out).unwrap();
    let mut res = json!({"test": "nusb_pr233_uvc_stream", "command": std::env::args().collect::<Vec<_>>().join(" "),
        "environment": {"nusb": "git zibo-chen/nusb@81ce16fa (kevinmehall/nusb PR #233, closed unmerged)", "os": std::env::consts::OS}});
    if let Err(e) = run(&m, &mut res) {
        res["error"] = json!(e);
        eprintln!("error: {e}");
    }
    let p = out.join("summary.json");
    std::fs::write(&p, serde_json::to_string_pretty(&res).unwrap()).unwrap();
    println!("{}", p.display());
}

fn ue(stage: &'static str) -> impl Fn(nusb::Error) -> String {
    move |x| format!("{stage}: {x}")
}
fn te(stage: &'static str) -> impl Fn(TransferError) -> String {
    move |x| format!("{stage}: {x:?}")
}

fn run(m: &HashMap<String, String>, res: &mut serde_json::Value) -> Result<(), String> {
    let vid = u16::from_str_radix(&arg(m, "vid", "046d"), 16).map_err(|x| x.to_string())?;
    let pid = u16::from_str_radix(&arg(m, "pid", "0843"), 16).map_err(|x| x.to_string())?;
    let w: u16 = arg(m, "width", "1280").parse().map_err(|_| "width")?;
    let h: u16 = arg(m, "height", "720").parse().map_err(|_| "height")?;
    let fps: u32 = arg(m, "fps", "30").parse().map_err(|_| "fps")?;
    let seconds: f64 = arg(m, "seconds", "10").parse().map_err(|_| "seconds")?;
    let queue: usize = arg(m, "queue", "8").parse().map_err(|_| "queue")?;
    let pkts: usize = arg(m, "pkts", "32").parse().map_err(|_| "pkts")?;
    let policy = AltPolicy::parse(&arg(m, "alt", "device"))?;
    let t = Duration::from_secs(2);

    let info = nusb::list_devices().wait().map_err(ue("list_devices"))?
        .find(|d| d.vendor_id() == vid && d.product_id() == pid).ok_or("device not found")?;
    let dev = info.open().wait().map_err(ue("open"))?;
    res["open"] = json!("ok");
    // Device-level control transfers are not available on Windows in nusb; use the cached descriptor.
    let raw = dev.active_configuration().map_err(|x| format!("active_configuration: {x}"))?.as_bytes().to_vec();
    let u = UvcInfo::parse(&raw).ok_or("no UVC VC interface")?;
    let (vs, fmt, fr) = u.find_mjpeg(w, h).ok_or("no MJPEG format/frame")?;
    let (vs, fmt, fr) = (vs.clone(), fmt.clone(), fr.clone());
    let want = (10_000_000f64 / fps as f64).round() as u32;
    let interval = *fr.intervals.iter().min_by_key(|&&i| (i as i64 - want as i64).abs()).unwrap_or(&fr.default_interval);
    let _vc = dev.detach_and_claim_interface(u.vc_interface).wait().map_err(ue("claim VC"))?;
    let vsi = dev.detach_and_claim_interface(vs.interface).wait().map_err(ue("claim VS"))?;
    res["claim"] = json!("ok");
    vsi.set_alt_setting(0).wait().map_err(ue("set_alt 0"))?;
    let plen = u.probe_len();
    let pc = ProbeCommit { bm_hint: 1, format_index: fmt.index, frame_index: fr.index, frame_interval: interval, ..Default::default() };
    let probe_bytes = pc.to_bytes(plen);
    vsi.control_out(ControlOut { control_type: ControlType::Class, recipient: Recipient::Interface, request: SET_CUR, value: (VS_PROBE as u16) << 8, index: vs.interface as u16, data: &probe_bytes }, t)
        .wait().map_err(te("PROBE SET_CUR"))?;
    let got = vsi.control_in(ControlIn { control_type: ControlType::Class, recipient: Recipient::Interface, request: GET_CUR, value: (VS_PROBE as u16) << 8, index: vs.interface as u16, length: plen as u16 }, t)
        .wait().map_err(te("PROBE GET_CUR"))?;
    vsi.control_out(ControlOut { control_type: ControlType::Class, recipient: Recipient::Interface, request: SET_CUR, value: (VS_COMMIT as u16) << 8, index: vs.interface as u16, data: &got }, t)
        .wait().map_err(te("COMMIT SET_CUR"))?;
    let neg = ProbeCommit::from_bytes(&got);
    res["probe_commit"] = json!({"requested": pc.to_json(), "negotiated": neg.to_json()});
    let alt = policy.choose(&vs.alts, neg.max_payload_transfer_size).cloned().ok_or("no iso alt")?;
    res["alt_selected"] = json!({"alt": alt.alt, "bytes_per_interval": alt.bytes_per_interval});
    vsi.set_alt_setting(alt.alt).wait().map_err(ue("set_alt"))?;
    let mut ep = vsi.endpoint::<Isochronous, In>(alt.ep_addr).map_err(ue("endpoint"))?;
    res["endpoint_max_payload_per_interval"] = json!(ep.max_payload_per_interval());
    let layout = IsoLayout::new(pkts, alt.bytes_per_interval as usize).map_err(|x| format!("layout: {x:?}"))?;

    let mut rejected = vec![];
    let mut accepted = 0usize;
    for i in 0..queue {
        let tr = ep.allocate_iso(layout).map_err(ue("allocate_iso"))?;
        match ep.submit(tr) {
            Ok(()) => accepted += 1,
            Err(se) => rejected.push(json!({"index": i, "error": format!("{:?}", se.error())})),
        }
    }
    res["initial_queue"] = json!({"requested": queue, "accepted": accepted, "rejected": rejected});

    let mut asm = Assembler::new((w as usize * h as usize * 2).max(fr.max_frame_buffer as usize));
    let mut frames: Vec<AssembledFrame> = vec![];
    let (mut completions, mut packets, mut ok_pkts, mut err_pkts, mut notexec, mut resubmit_err, mut max_pending) = (0u64, 0u64, 0u64, 0u64, 0u64, 0u64, 0usize);
    let mut nvalid = 0usize;
    let mut arrivals: Vec<i64> = vec![];
    // --raw-mjpeg FILE: frames concatenated; frames_nusb.jsonl in --out gives sizes (decode_mjpeg_check.py)
    let mut raw = m.get("raw-mjpeg").map(|p| std::io::BufWriter::new(std::fs::File::create(p).unwrap()));
    let mut fl = std::io::BufWriter::new(std::fs::File::create(std::path::Path::new(&arg(m, "out", "nusb_pr233_out")).join("frames_nusb.jsonl")).unwrap());
    let t0 = Instant::now();
    while t0.elapsed().as_secs_f64() < seconds {
        max_pending = max_pending.max(ep.pending());
        let Some(c) = ep.wait_next_complete(t) else {
            res["timeout_waiting_for_completion"] = json!(true);
            break;
        };
        let host = t0.elapsed().as_nanos() as i64;
        completions += 1;
        if let Err(x) = c.status() {
            res["last_completion_error"] = json!(format!("{x:?}"));
        }
        let mut done = vec![];
        for p in c.packets() {
            packets += 1;
            match p.status() {
                IsoPacketStatus::Success => {
                    ok_pkts += 1;
                    asm.push(p.data(), host, host, &mut done)
                }
                IsoPacketStatus::NotExecuted => notexec += 1,
                _ => err_pkts += 1,
            }
        }
        for mut f in done {
            if let Some(w) = raw.as_mut() {
                use std::io::Write;
                let _ = w.write_all(&f.data);
                let _ = writeln!(fl, "{}", json!({"seq": f.seq, "payload_bytes": f.data.len(), "uvc_pts": f.pts, "host_arrival_ns": host, "uvc_scr_sof": f.first_scr.map(|x| x.1)}));
            }
            let (s, eo) = jpeg_markers(&f.data);
            if s && eo && !f.err {
                nvalid += 1;
            }
            arrivals.push(host);
            f.data = vec![];
            frames.push(f);
        }
        if ep.submit(c.into_transfer()).is_err() {
            resubmit_err += 1;
        }
    }
    let wall = t0.elapsed().as_secs_f64();
    ep.cancel_all();
    drop(ep);
    let _ = vsi.set_alt_setting(0).wait();
    let period = u.clock_frequency as f64 * interval as f64 / 1e7;
    let pts: Vec<u32> = frames.iter().filter_map(|f| f.pts).collect();
    let gaps = pts.windows(2).filter(|w| w[1].wrapping_sub(w[0]) as f64 >= 1.5 * period).count();
    let fps_meas = if arrivals.len() > 31 { (arrivals.len() - 31) as f64 / ((arrivals[arrivals.len() - 1] - arrivals[30]) as f64 / 1e9) } else { 0.0 };
    res["results"] = json!({"frames": frames.len(), "valid_jpeg_soi_eoi": nvalid, "fps_after_skip30": fps_meas, "completions": completions,
        "packets": packets, "packets_ok": ok_pkts, "packets_error": err_pkts, "packets_not_executed": notexec, "resubmit_errors": resubmit_err,
        "max_pending_observed": max_pending, "payloads": asm.stats_payloads, "bad_headers": asm.stats_bad_headers, "empty_packets": asm.stats_empty_packets,
        "err_flag_payloads": asm.stats_err_flag, "pts_gaps_ge_1p5_period": gaps, "expected_period_ticks": period, "wall_s": wall});
    Ok(())
}
