//! Platform-independent UVC pieces: descriptor parsing, probe/commit encoding, payload-header
//! parsing (FID/EOF/PTS/SCR) and frame reassembly. No OS calls here: this whole file is shared
//! across Windows (WinUSB), Linux (usbfs) and macOS (IOKit).
//! Reference: USB Device Class Definition for Video Devices 1.5 (UVC 1.5), §2.4.3.3 (payload
//! header), §3.7/3.9 (descriptors), §4.3.1.1 (probe/commit).

#![allow(dead_code)]

use serde_json::{json, Value};

fn le16(b: &[u8], o: usize) -> u16 {
    u16::from_le_bytes([b[o], b[o + 1]])
}
fn le32(b: &[u8], o: usize) -> u32 {
    u32::from_le_bytes([b[o], b[o + 1], b[o + 2], b[o + 3]])
}

#[derive(Debug, Clone, Default)]
pub struct FrameDesc {
    pub index: u8,
    pub width: u16,
    pub height: u16,
    pub max_frame_buffer: u32,
    pub default_interval: u32,
    pub intervals: Vec<u32>, // discrete, or [min,max,step] when continuous
    pub continuous: bool,
}

#[derive(Debug, Clone, Default)]
pub struct FormatDesc {
    pub index: u8,
    pub kind: String, // "MJPEG" | "UNCOMPRESSED:<fourcc>" | "FRAME_BASED:<fourcc>"
    pub frames: Vec<FrameDesc>,
}

#[derive(Debug, Clone, Default)]
pub struct AltSetting {
    pub alt: u8,
    pub ep_addr: u8,
    pub ep_type: u8, // 1 = iso, 2 = bulk
    pub w_max_packet_size: u16,
    pub bytes_per_interval: u32, // HS: (mps & 0x7ff) * (1 + mult); SS: companion wBytesPerInterval
    pub b_interval: u8,
    pub ss_max_burst: Option<u8>,
    pub ss_mult: Option<u8>,
}

#[derive(Debug, Clone, Default)]
pub struct StreamingIf {
    pub interface: u8,
    pub endpoint: u8,
    pub formats: Vec<FormatDesc>,
    pub alts: Vec<AltSetting>,
}

#[derive(Debug, Clone, Default)]
pub struct UvcInfo {
    pub vc_interface: u8,
    pub bcd_uvc: u16,
    pub clock_frequency: u32,
    pub camera_terminal_id: Option<u8>,
    pub processing_unit_id: Option<u8>,
    pub ct_controls_bitmap: u32,
    pub pu_controls_bitmap: u32,
    pub streaming: Vec<StreamingIf>,
}

impl UvcInfo {
    /// Parse a raw configuration descriptor (as returned by GET_DESCRIPTOR(CONFIGURATION)).
    pub fn parse(raw: &[u8]) -> Option<UvcInfo> {
        let mut info = UvcInfo::default();
        let mut found_vc = false;
        let mut cur_if: Option<(u8, u8, u8, u8)> = None; // (num, alt, class, subclass)
        let mut i = 0usize;
        while i + 2 <= raw.len() {
            let len = raw[i] as usize;
            if len < 2 || i + len > raw.len() {
                break;
            }
            let d = &raw[i..i + len];
            let dtype = d[1];
            match dtype {
                0x04 if len >= 9 => {
                    cur_if = Some((d[2], d[3], d[5], d[6]));
                    if d[5] == 0x0E && d[6] == 0x02 {
                        let num = d[2];
                        if !info.streaming.iter().any(|s| s.interface == num) {
                            info.streaming.push(StreamingIf { interface: num, ..Default::default() });
                        }
                    }
                }
                0x05 if len >= 7 => {
                    if let Some((num, alt, 0x0E, 0x02)) = cur_if {
                        let mps = le16(d, 4);
                        let ep_type = d[3] & 0x03;
                        let bpi = (mps as u32 & 0x7ff) * (1 + ((mps as u32 >> 11) & 0x3));
                        if let Some(s) = info.streaming.iter_mut().find(|s| s.interface == num) {
                            s.alts.push(AltSetting { alt, ep_addr: d[2], ep_type, w_max_packet_size: mps, bytes_per_interval: bpi, b_interval: d[6], ss_max_burst: None, ss_mult: None });
                        }
                    }
                }
                0x30 if len >= 6 => {
                    // SuperSpeed endpoint companion follows the endpoint it describes.
                    if let Some((num, _, 0x0E, 0x02)) = cur_if {
                        if let Some(s) = info.streaming.iter_mut().find(|s| s.interface == num) {
                            if let Some(a) = s.alts.last_mut() {
                                a.ss_max_burst = Some(d[2]);
                                a.ss_mult = Some(d[3] & 0x3);
                                let w = le16(d, 4) as u32;
                                if w > 0 {
                                    a.bytes_per_interval = w;
                                }
                            }
                        }
                    }
                }
                0x24 => {
                    if let Some((num, _alt, 0x0E, sub)) = cur_if {
                        let subtype = d[2];
                        if sub == 0x01 {
                            match subtype {
                                0x01 if len >= 12 => {
                                    found_vc = true;
                                    info.vc_interface = num;
                                    info.bcd_uvc = le16(d, 3);
                                    info.clock_frequency = le32(d, 7);
                                }
                                0x02 if len >= 8 => {
                                    // input terminal; ITT_CAMERA = 0x0201
                                    if le16(d, 4) == 0x0201 {
                                        info.camera_terminal_id = Some(d[3]);
                                        if len >= 15 {
                                            let n = d[14] as usize;
                                            let mut bm = 0u32;
                                            for k in 0..n.min(3) {
                                                if 15 + k < len {
                                                    bm |= (d[15 + k] as u32) << (8 * k);
                                                }
                                            }
                                            info.ct_controls_bitmap = bm;
                                        }
                                    }
                                }
                                0x05 if len >= 8 => {
                                    info.processing_unit_id = Some(d[3]);
                                    let n = d[7] as usize;
                                    let mut bm = 0u32;
                                    for k in 0..n.min(3) {
                                        if 8 + k < len {
                                            bm |= (d[8 + k] as u32) << (8 * k);
                                        }
                                    }
                                    info.pu_controls_bitmap = bm;
                                }
                                _ => {}
                            }
                        } else if sub == 0x02 {
                            let s = info.streaming.iter_mut().find(|s| s.interface == num);
                            if let Some(s) = s {
                                match subtype {
                                    0x01 if len >= 7 => s.endpoint = d[6],
                                    0x06 if len >= 5 => s.formats.push(FormatDesc { index: d[3], kind: "MJPEG".into(), frames: vec![] }),
                                    0x04 if len >= 21 => {
                                        let fcc = String::from_utf8_lossy(&d[5..9]).to_string();
                                        s.formats.push(FormatDesc { index: d[3], kind: format!("UNCOMPRESSED:{fcc}"), frames: vec![] })
                                    }
                                    0x10 if len >= 21 => {
                                        let fcc = String::from_utf8_lossy(&d[5..9]).to_string();
                                        s.formats.push(FormatDesc { index: d[3], kind: format!("FRAME_BASED:{fcc}"), frames: vec![] })
                                    }
                                    0x05 | 0x07 if len >= 26 => {
                                        let n = d[25] as usize;
                                        let mut iv = vec![];
                                        let cont = n == 0;
                                        let cnt = if cont { 3 } else { n };
                                        for k in 0..cnt {
                                            if 26 + 4 * k + 4 <= len {
                                                iv.push(le32(d, 26 + 4 * k));
                                            }
                                        }
                                        let f = FrameDesc { index: d[3], width: le16(d, 5), height: le16(d, 7), max_frame_buffer: le32(d, 17), default_interval: le32(d, 21), intervals: iv, continuous: cont };
                                        if let Some(fm) = s.formats.last_mut() {
                                            fm.frames.push(f);
                                        }
                                    }
                                    0x11 if len >= 26 => {
                                        let n = d[21] as usize;
                                        let cont = n == 0;
                                        let cnt = if cont { 3 } else { n };
                                        let mut iv = vec![];
                                        for k in 0..cnt {
                                            if 26 + 4 * k + 4 <= len {
                                                iv.push(le32(d, 26 + 4 * k));
                                            }
                                        }
                                        let f = FrameDesc { index: d[3], width: le16(d, 5), height: le16(d, 7), max_frame_buffer: 0, default_interval: le32(d, 17), intervals: iv, continuous: cont };
                                        if let Some(fm) = s.formats.last_mut() {
                                            fm.frames.push(f);
                                        }
                                    }
                                    _ => {}
                                }
                            }
                        }
                    }
                }
                _ => {}
            }
            i += len;
        }
        if found_vc {
            Some(info)
        } else {
            None
        }
    }

    pub fn to_json(&self) -> Value {
        json!({
            "vc_interface": self.vc_interface,
            "bcdUVC": format!("{:x}.{:02x}", self.bcd_uvc >> 8, self.bcd_uvc & 0xff),
            "dwClockFrequency": self.clock_frequency,
            "camera_terminal_id": self.camera_terminal_id,
            "processing_unit_id": self.processing_unit_id,
            "ct_bmControls": format!("{:#x}", self.ct_controls_bitmap),
            "pu_bmControls": format!("{:#x}", self.pu_controls_bitmap),
            "streaming": self.streaming.iter().map(|s| json!({
                "interface": s.interface,
                "endpoint": format!("{:#04x}", s.endpoint),
                "alt_settings": s.alts.iter().map(|a| json!({
                    "alt": a.alt, "ep": format!("{:#04x}", a.ep_addr),
                    "type": match a.ep_type { 1 => "iso", 2 => "bulk", 3 => "interrupt", _ => "control" },
                    "wMaxPacketSize": format!("{:#06x}", a.w_max_packet_size),
                    "bytes_per_interval": a.bytes_per_interval,
                    "ss_max_burst": a.ss_max_burst, "ss_mult": a.ss_mult, "bInterval": a.b_interval,
                })).collect::<Vec<_>>(),
                "formats": s.formats.iter().map(|f| json!({
                    "index": f.index, "kind": f.kind,
                    "frames": f.frames.iter().map(|fr| json!({
                        "index": fr.index, "w": fr.width, "h": fr.height,
                        "max_frame_buffer": fr.max_frame_buffer,
                        "default_interval_100ns": fr.default_interval,
                        "intervals_100ns": fr.intervals, "continuous": fr.continuous,
                    })).collect::<Vec<_>>(),
                })).collect::<Vec<_>>(),
            })).collect::<Vec<_>>(),
        })
    }

    pub fn find_mjpeg(&self, w: u16, h: u16) -> Option<(&StreamingIf, &FormatDesc, &FrameDesc)> {
        for s in &self.streaming {
            for f in &s.formats {
                if f.kind == "MJPEG" {
                    for fr in &f.frames {
                        if fr.width == w && fr.height == h {
                            return Some((s, f, fr));
                        }
                    }
                }
            }
        }
        None
    }

    pub fn probe_len(&self) -> usize {
        match self.bcd_uvc {
            0x0000..=0x010F => 26,
            0x0110..=0x014F => 34,
            _ => 48,
        }
    }
}

/// VS probe/commit control block (UVC 1.5 table 4-75).
#[derive(Debug, Clone, Default)]
pub struct ProbeCommit {
    pub bm_hint: u16,
    pub format_index: u8,
    pub frame_index: u8,
    pub frame_interval: u32,
    pub key_frame_rate: u16,
    pub p_frame_rate: u16,
    pub comp_quality: u16,
    pub comp_window_size: u16,
    pub delay: u16,
    pub max_video_frame_size: u32,
    pub max_payload_transfer_size: u32,
    pub clock_frequency: u32,
    pub framing_info: u8,
    pub preferred_version: u8,
    pub min_version: u8,
    pub max_version: u8,
}

impl ProbeCommit {
    pub fn to_bytes(&self, len: usize) -> Vec<u8> {
        let mut b = vec![0u8; len.max(26)];
        b[0..2].copy_from_slice(&self.bm_hint.to_le_bytes());
        b[2] = self.format_index;
        b[3] = self.frame_index;
        b[4..8].copy_from_slice(&self.frame_interval.to_le_bytes());
        b[8..10].copy_from_slice(&self.key_frame_rate.to_le_bytes());
        b[10..12].copy_from_slice(&self.p_frame_rate.to_le_bytes());
        b[12..14].copy_from_slice(&self.comp_quality.to_le_bytes());
        b[14..16].copy_from_slice(&self.comp_window_size.to_le_bytes());
        b[16..18].copy_from_slice(&self.delay.to_le_bytes());
        b[18..22].copy_from_slice(&self.max_video_frame_size.to_le_bytes());
        b[22..26].copy_from_slice(&self.max_payload_transfer_size.to_le_bytes());
        if len >= 34 {
            b[26..30].copy_from_slice(&self.clock_frequency.to_le_bytes());
            b[30] = self.framing_info;
            b[31] = self.preferred_version;
            b[32] = self.min_version;
            b[33] = self.max_version;
        }
        b.truncate(len);
        b
    }
    pub fn from_bytes(b: &[u8]) -> ProbeCommit {
        let g16 = |o: usize| if b.len() >= o + 2 { le16(b, o) } else { 0 };
        let g32 = |o: usize| if b.len() >= o + 4 { le32(b, o) } else { 0 };
        let g8 = |o: usize| b.get(o).copied().unwrap_or(0);
        ProbeCommit {
            bm_hint: g16(0), format_index: g8(2), frame_index: g8(3), frame_interval: g32(4),
            key_frame_rate: g16(8), p_frame_rate: g16(10), comp_quality: g16(12), comp_window_size: g16(14),
            delay: g16(16), max_video_frame_size: g32(18), max_payload_transfer_size: g32(22),
            clock_frequency: g32(26), framing_info: g8(30), preferred_version: g8(31), min_version: g8(32), max_version: g8(33),
        }
    }
    pub fn to_json(&self) -> Value {
        json!({"bmHint": self.bm_hint, "bFormatIndex": self.format_index, "bFrameIndex": self.frame_index,
            "dwFrameInterval": self.frame_interval, "wCompQuality": self.comp_quality, "wDelay_ms": self.delay,
            "dwMaxVideoFrameSize": self.max_video_frame_size, "dwMaxPayloadTransferSize": self.max_payload_transfer_size,
            "dwClockFrequency": self.clock_frequency, "bmFramingInfo": self.framing_info})
    }
}

// --- class-specific request constants ---
pub const SET_CUR: u8 = 0x01;
pub const GET_CUR: u8 = 0x81;
pub const GET_MIN: u8 = 0x82;
pub const GET_MAX: u8 = 0x83;
pub const GET_DEF: u8 = 0x87;
pub const VS_PROBE: u8 = 0x01;
pub const VS_COMMIT: u8 = 0x02;
pub const RT_CLASS_IF_OUT: u8 = 0x21;
pub const RT_CLASS_IF_IN: u8 = 0xA1;
pub const CT_AE_MODE: u8 = 0x02;
pub const CT_EXPOSURE_TIME_ABSOLUTE: u8 = 0x04;
pub const PU_WB_TEMPERATURE: u8 = 0x0A;
pub const PU_WB_TEMPERATURE_AUTO: u8 = 0x0B;
pub const PU_GAIN: u8 = 0x04;

/// Alternate-setting policy: this is the app-level equivalent of uvcvideo's bandwidth choice
/// (and of `quirks=128`, which only rewrites dwMaxPayloadTransferSize for uncompressed formats).
#[derive(Debug, Clone)]
pub enum AltPolicy {
    /// smallest iso alt whose bytes/interval >= the device's committed dwMaxPayloadTransferSize
    /// (what Linux uvcvideo does by default); falls back to the largest.
    Device,
    /// smallest iso alt whose bytes/interval >= this many bytes (app-chosen bandwidth)
    Payload(u32),
    /// exact alternate setting number
    Exact(u8),
}

impl AltPolicy {
    pub fn parse(s: &str) -> Result<AltPolicy, String> {
        if s == "device" || s == "auto" {
            Ok(AltPolicy::Device)
        } else if let Some(v) = s.strip_prefix("payload:") {
            v.parse().map(AltPolicy::Payload).map_err(|e| format!("{e}"))
        } else {
            s.parse().map(AltPolicy::Exact).map_err(|e| format!("bad --alt {s}: {e}"))
        }
    }
    pub fn choose<'a>(&self, alts: &'a [AltSetting], committed_payload: u32) -> Option<&'a AltSetting> {
        let mut iso: Vec<&AltSetting> = alts.iter().filter(|a| a.ep_type == 1 && a.bytes_per_interval > 0).collect();
        iso.sort_by_key(|a| a.bytes_per_interval);
        match self {
            AltPolicy::Exact(n) => alts.iter().find(|a| a.alt == *n),
            AltPolicy::Device => iso.iter().find(|a| a.bytes_per_interval >= committed_payload).or(iso.last()).copied(),
            AltPolicy::Payload(p) => iso.iter().find(|a| a.bytes_per_interval >= *p).or(iso.last()).copied(),
        }
    }
}

/// One parsed payload (one iso packet).
#[derive(Debug, Clone, Copy, Default)]
pub struct PayloadHeader {
    pub hlen: u8,
    pub fid: u8,
    pub eof: bool,
    pub err: bool,
    pub still: bool,
    pub eoh: bool,
    pub pts: Option<u32>,
    pub scr_stc: Option<u32>,
    pub scr_sof: Option<u16>,
}

pub fn parse_header(p: &[u8]) -> Option<PayloadHeader> {
    if p.len() < 2 {
        return None;
    }
    let hlen = p[0] as usize;
    if hlen < 2 || hlen > p.len() {
        return None;
    }
    let f = p[1];
    // bit 7 EOH "should" be set, but the C930e (bcdUVC 1.00) sends 0x0c/0x0d/0x0e/0x0f headers
    // with EOH clear (phase 2, results/windows/Gerald/phase2_rust_uvc_iso). Linux uvcvideo and
    // libuvc do not check EOH either; we only record whether it was set.
    let mut h = PayloadHeader { hlen: hlen as u8, fid: f & 1, eof: f & 2 != 0, err: f & 0x40 != 0, still: f & 0x20 != 0, eoh: f & 0x80 != 0, ..Default::default() };
    let mut o = 2;
    if f & 0x04 != 0 && hlen >= o + 4 {
        h.pts = Some(le32(p, o));
        o += 4;
    }
    if f & 0x08 != 0 && hlen >= o + 6 {
        h.scr_stc = Some(le32(p, o));
        h.scr_sof = Some(le16(p, o + 4) & 0x7ff);
    }
    Some(h)
}

#[derive(Debug, Clone, Default)]
pub struct AssembledFrame {
    pub seq: u64,
    pub data: Vec<u8>,
    pub fid: u8,
    pub pts: Option<u32>,
    pub first_scr: Option<(u32, u16)>,
    pub last_scr: Option<(u32, u16)>,
    pub payloads: u32,
    pub err: bool,
    pub ended_by_eof: bool,
    /// host time of the transfer completion containing the first / last payload
    pub first_xfer_host_ns: i64,
    pub last_xfer_host_ns: i64,
    /// host time estimated for the first payload's (micro)frame: completion time minus the
    /// number of service intervals between that packet and the end of its transfer
    pub first_packet_est_host_ns: i64,
    pub last_packet_est_host_ns: i64,
}

/// Linux-style reassembly: FID toggle or EOF ends a frame; header-only payloads after EOF with
/// the same FID are ignored; the first (possibly partial) frame is discarded.
#[derive(Default)]
pub struct Assembler {
    cur: Option<AssembledFrame>,
    last_fid: Option<u8>,
    after_eof: bool,
    synced: bool,
    seq: u64,
    pub max_frame: usize,
    pub stats_payloads: u64,
    pub stats_bad_headers: u64,
    pub stats_empty_packets: u64,
    pub stats_err_flag: u64,
    pub stats_no_eoh: u64,
    pub stats_overflow: u64,
    pub stats_discarded_partial: u64,
}

impl Assembler {
    pub fn new(max_frame: usize) -> Self {
        Assembler { max_frame, ..Default::default() }
    }

    /// Feed one iso packet. `xfer_host_ns` = completion time of its transfer,
    /// `est_host_ns` = estimated time of its (micro)frame. Returns a finished frame if any.
    pub fn push(&mut self, p: &[u8], xfer_host_ns: i64, est_host_ns: i64, out: &mut Vec<AssembledFrame>) {
        if p.is_empty() {
            self.stats_empty_packets += 1;
            return;
        }
        let Some(h) = parse_header(p) else {
            self.stats_bad_headers += 1;
            return;
        };
        self.stats_payloads += 1;
        if !h.eoh {
            self.stats_no_eoh += 1;
        }
        if h.err {
            self.stats_err_flag += 1;
        }
        let data = &p[h.hlen as usize..];
        let fid_changed = self.last_fid.map(|f| f != h.fid).unwrap_or(false);
        self.last_fid = Some(h.fid);
        if fid_changed {
            self.after_eof = false;
            if let Some(f) = self.cur.take() {
                self.finish(f, out);
            }
            self.synced = true;
        } else if self.after_eof {
            // trailing header-only payloads of the frame that already ended
            return;
        }
        if data.is_empty() && self.cur.is_none() && !h.eof {
            return;
        }
        let f = self.cur.get_or_insert_with(|| AssembledFrame {
            fid: h.fid,
            first_xfer_host_ns: xfer_host_ns,
            first_packet_est_host_ns: est_host_ns,
            ..Default::default()
        });
        f.payloads += 1;
        f.err |= h.err;
        if f.pts.is_none() {
            f.pts = h.pts;
        }
        if let (Some(s), Some(o)) = (h.scr_stc, h.scr_sof) {
            if f.first_scr.is_none() {
                f.first_scr = Some((s, o));
            }
            f.last_scr = Some((s, o));
        }
        if f.data.len() + data.len() <= self.max_frame {
            f.data.extend_from_slice(data);
        } else {
            self.stats_overflow += 1;
            f.err = true;
        }
        f.last_xfer_host_ns = xfer_host_ns;
        f.last_packet_est_host_ns = est_host_ns;
        if h.eof {
            let mut f = self.cur.take().unwrap();
            f.ended_by_eof = true;
            self.after_eof = true;
            self.synced = true;
            self.finish(f, out);
        }
    }

    fn finish(&mut self, mut f: AssembledFrame, out: &mut Vec<AssembledFrame>) {
        if !self.synced {
            self.stats_discarded_partial += 1;
            return;
        }
        if f.data.is_empty() {
            return;
        }
        f.seq = self.seq;
        self.seq += 1;
        out.push(f);
    }
}

pub fn jpeg_markers(b: &[u8]) -> (bool, bool) {
    let soi = b.len() >= 2 && b[0] == 0xFF && b[1] == 0xD8;
    let tail = &b[b.len().saturating_sub(64)..];
    let eoi = tail.windows(2).any(|w| w == [0xFF, 0xD9]);
    (soi, eoi)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pkt(fid: u8, eof: bool, pts: Option<u32>, scr: Option<(u32, u16)>, data: &[u8]) -> Vec<u8> {
        let mut flags = 0x80 | fid;
        if eof {
            flags |= 2;
        }
        let mut h = vec![0u8, 0u8];
        if let Some(p) = pts {
            flags |= 4;
            h.extend_from_slice(&p.to_le_bytes());
        }
        if let Some((s, o)) = scr {
            flags |= 8;
            h.extend_from_slice(&s.to_le_bytes());
            h.extend_from_slice(&o.to_le_bytes());
        }
        h[0] = h.len() as u8;
        h[1] = flags;
        h.extend_from_slice(data);
        h
    }

    #[test]
    fn header_parse() {
        let p = pkt(1, true, Some(0x11223344), Some((0x55667788, 0x0123)), &[1, 2, 3]);
        let h = parse_header(&p).unwrap();
        assert_eq!(h.hlen, 12);
        assert_eq!(h.fid, 1);
        assert!(h.eof);
        assert_eq!(h.pts, Some(0x11223344));
        assert_eq!(h.scr_stc, Some(0x55667788));
        assert_eq!(h.scr_sof, Some(0x123));
    }

    #[test]
    fn header_without_eoh_accepted() {
        // C930e header as captured: len 12, flags 0x0c (PTS|SCR, EOH clear)
        let p = [0x0c, 0x0c, 0x84, 0x35, 0xcc, 0xf8, 0xf4, 0x23, 0xda, 0xf8, 0x67, 0x02, 0xff, 0xd8];
        let h = parse_header(&p).unwrap();
        assert!(!h.eoh);
        assert_eq!(h.pts, Some(0xf8cc3584));
        assert_eq!(h.scr_stc, Some(0xf8da23f4));
        assert_eq!(h.scr_sof, Some(0x267));
    }

    #[test]
    fn assembler_fid_and_eof() {
        let mut a = Assembler::new(1 << 20);
        let mut out = vec![];
        // partial frame (fid 0) then full frame fid 1 with EOF, then trailing header-only, then fid 0 frame ended by toggle
        a.push(&pkt(0, false, Some(1), None, &[9, 9]), 0, 0, &mut out);
        a.push(&pkt(1, false, Some(2), Some((100, 5)), &[0xFF, 0xD8]), 1, 1, &mut out);
        a.push(&pkt(1, true, Some(2), Some((120, 6)), &[0xFF, 0xD9]), 2, 2, &mut out);
        a.push(&pkt(1, false, Some(2), None, &[]), 3, 3, &mut out);
        a.push(&pkt(0, false, Some(3), None, &[0xFF, 0xD8, 0xFF, 0xD9]), 4, 4, &mut out);
        a.push(&pkt(1, false, Some(4), None, &[0xFF, 0xD8]), 5, 5, &mut out);
        assert_eq!(a.stats_discarded_partial, 1);
        assert_eq!(out.len(), 2);
        assert_eq!(out[0].data, vec![0xFF, 0xD8, 0xFF, 0xD9]);
        assert_eq!(out[0].pts, Some(2));
        assert_eq!(out[0].first_scr, Some((100, 5)));
        assert_eq!(out[0].last_scr, Some((120, 6)));
        assert!(out[0].ended_by_eof);
        assert_eq!(out[1].pts, Some(3));
        assert!(!out[1].ended_by_eof);
    }

    #[test]
    fn alt_policy() {
        let alts = vec![
            AltSetting { alt: 0, ep_type: 1, bytes_per_interval: 0, ..Default::default() },
            AltSetting { alt: 1, ep_type: 1, bytes_per_interval: 192, ..Default::default() },
            AltSetting { alt: 2, ep_type: 1, bytes_per_interval: 1024, ..Default::default() },
            AltSetting { alt: 3, ep_type: 1, bytes_per_interval: 3072, ..Default::default() },
        ];
        assert_eq!(AltPolicy::Device.choose(&alts, 3000).unwrap().alt, 3);
        assert_eq!(AltPolicy::Payload(800).choose(&alts, 3000).unwrap().alt, 2);
        assert_eq!(AltPolicy::Exact(1).choose(&alts, 3000).unwrap().alt, 1);
        assert_eq!(AltPolicy::Device.choose(&alts, 9000).unwrap().alt, 3);
    }

    #[test]
    fn probe_roundtrip() {
        let p = ProbeCommit { bm_hint: 1, format_index: 2, frame_index: 3, frame_interval: 333333, max_payload_transfer_size: 3072, clock_frequency: 48_000_000, ..Default::default() };
        let b = p.to_bytes(34);
        assert_eq!(b.len(), 34);
        let q = ProbeCommit::from_bytes(&b);
        assert_eq!(q.frame_interval, 333333);
        assert_eq!(q.max_payload_transfer_size, 3072);
        assert_eq!(q.clock_frequency, 48_000_000);
    }
}
