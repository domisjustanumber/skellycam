//! rawusb 0.1.7 backend (pure Rust, no C). Isochronous transfers: Linux usbfs, macOS IOKit
//! (crate docs call macOS iso "experimental"), Windows WinUSB ReadIsochPipeAsap (needs the
//! device/interface bound to WinUSB).

use crate::hostclock::host_ns;
use crate::usb::*;
use rawusb::types::{ControlSetup, TransferStatus};
use rawusb::{Context, Device, DeviceHandle, Transfer};
use serde_json::json;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;

pub struct RawUsb {
    ctx: Context,
}

impl RawUsb {
    pub fn new() -> Res<Self> {
        Ok(RawUsb { ctx: Context::new().map_err(|e| format!("rawusb Context::new: {e}"))? })
    }
}

fn summarize(d: &Device) -> DevSummary {
    let (raw, err) = match d.active_config_descriptor() {
        Ok(c) => (Some(c.raw().to_vec()), None),
        Err(e) => (None, Some(e.to_string())),
    };
    DevSummary {
        vid: d.vendor_id(),
        pid: d.product_id(),
        bus: d.bus_number(),
        address: d.address(),
        port_path: d.port_numbers().to_vec(),
        speed: format!("{:?}", d.speed()),
        serial: d.serial_number().map(|s| s.to_string()),
        raw_config: raw,
        raw_config_error: err,
    }
}

impl Backend for RawUsb {
    fn name(&self) -> &'static str {
        "rawusb-0.1.7"
    }
    fn list(&self) -> Res<Vec<DevSummary>> {
        Ok(self.ctx.devices().map_err(|e| e.to_string())?.iter().map(summarize).collect())
    }
    fn open(&self, vid: u16, pid: u16, serial: Option<&str>, port_path: Option<&[u8]>) -> Res<Box<dyn Dev>> {
        let devs = self.ctx.devices().map_err(|e| e.to_string())?;
        let d = devs
            .into_iter()
            .find(|d| {
                d.vendor_id() == vid
                    && d.product_id() == pid
                    && serial.map(|s| d.serial_number() == Some(s)).unwrap_or(true)
                    && port_path.map(|p| d.port_numbers() == p).unwrap_or(true)
            })
            .ok_or_else(|| format!("device {vid:04x}:{pid:04x} not found"))?;
        let h = d.open().map_err(|e| format!("open: {e}"))?;
        h.set_auto_detach_kernel_driver(true);
        Ok(Box::new(RawDev { dev: d, h }))
    }
}

pub struct RawDev {
    dev: Device,
    h: DeviceHandle,
}

impl Dev for RawDev {
    fn summary(&self) -> DevSummary {
        summarize(&self.dev)
    }
    fn raw_config(&self) -> Res<Vec<u8>> {
        self.dev.active_config_descriptor().map(|c| c.raw().to_vec()).map_err(|e| e.to_string())
    }
    fn claim(&self, intf: u8) -> Res<()> {
        self.h.claim_interface(intf).map_err(|e| format!("claim_interface({intf}): {e}"))
    }
    fn set_alt(&self, intf: u8, alt: u8) -> Res<()> {
        self.h.set_alternate_setting(intf, alt).map_err(|e| format!("set_alternate_setting({intf},{alt}): {e}"))
    }
    fn ctrl_in(&self, rt: u8, req: u8, val: u16, idx: u16, len: usize) -> Res<Vec<u8>> {
        let mut b = vec![0u8; len];
        let n = self.h.control_read(rt, req, val, idx, &mut b, Duration::from_secs(2)).map_err(|e| e.to_string())?;
        b.truncate(n);
        Ok(b)
    }
    fn ctrl_out(&self, rt: u8, req: u8, val: u16, idx: u16, data: &[u8]) -> Res<()> {
        self.h.control_write(rt, req, val, idx, data, Duration::from_secs(2)).map(|_| ()).map_err(|e| e.to_string())
    }
    fn start_iso(&self, ep: u8, pkt_len: usize, npkts: usize, nxfers: usize, sink: IsoSink) -> Res<Box<dyn IsoStream>> {
        let stop = Arc::new(AtomicBool::new(false));
        let completed = Arc::new(AtomicU64::new(0));
        let failed = Arc::new(AtomicU64::new(0));
        let mut xfers = vec![];
        for _ in 0..nxfers {
            let t = Transfer::isochronous(&self.h, ep, pkt_len, npkts);
            let (stop2, sink2, comp2, fail2) = (stop.clone(), sink.clone(), completed.clone(), failed.clone());
            t.set_callback(move |t: &Transfer| {
                let host = host_ns();
                let st = t.status();
                if st == TransferStatus::Completed {
                    comp2.fetch_add(1, Ordering::Relaxed);
                    let lens: Vec<(u32, bool)> = t.iso_packets().iter().map(|p| (p.actual_length, p.status == TransferStatus::Completed)).collect();
                    if let Ok(buf) = t.buffer() {
                        sink2(host, &buf[..], &lens, pkt_len);
                    }
                } else {
                    fail2.fetch_add(1, Ordering::Relaxed);
                }
                if !stop2.load(Ordering::Relaxed) && st != TransferStatus::NoDevice && st != TransferStatus::Cancelled {
                    let _ = t.submit();
                }
            })
            .map_err(|e| e.to_string())?;
            xfers.push(t);
        }
        for t in &xfers {
            t.submit().map_err(|e| format!("submit iso: {e}"))?;
        }
        let _ = ControlSetup::SIZE;
        Ok(Box::new(RawStream { xfers, stop, completed, failed }))
    }
}

struct RawStream {
    xfers: Vec<Transfer>,
    stop: Arc<AtomicBool>,
    completed: Arc<AtomicU64>,
    failed: Arc<AtomicU64>,
}

impl IsoStream for RawStream {
    fn stop(self: Box<Self>) -> serde_json::Value {
        self.stop.store(true, Ordering::SeqCst);
        for t in &self.xfers {
            let _ = t.cancel();
        }
        for t in &self.xfers {
            let _ = t.wait(Some(Duration::from_secs(2)));
        }
        json!({"transfers_completed": self.completed.load(Ordering::SeqCst), "transfers_failed": self.failed.load(Ordering::SeqCst)})
    }
}
