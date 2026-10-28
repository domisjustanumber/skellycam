//! Minimal USB backend abstraction so the UVC logic in uvc.rs / main.rs is written once.
//! Two implementations: `rawusb` (pure Rust; WinUSB / usbfs / IOKit) and `libusb`
//! (libusb1-sys, vendored libusb 1.0.27: WinUSB / usbfs / IOKit).

use std::sync::Arc;

pub type Res<T> = Result<T, String>;

#[derive(Debug, Clone)]
pub struct DevSummary {
    pub vid: u16,
    pub pid: u16,
    pub bus: u8,
    pub address: u8,
    pub port_path: Vec<u8>,
    pub speed: String,
    pub serial: Option<String>,
    pub raw_config: Option<Vec<u8>>,
    pub raw_config_error: Option<String>,
}

/// Called on the backend's event thread for every completed iso transfer:
/// (host_ns at completion, whole transfer buffer, per-packet (actual_length, ok), packet stride)
pub type IsoSink = Arc<dyn Fn(i64, &[u8], &[(u32, bool)], usize) + Send + Sync>;

pub trait IsoStream: Send {
    fn stop(self: Box<Self>) -> serde_json::Value;
}

pub trait Dev: Send + Sync {
    fn summary(&self) -> DevSummary;
    fn raw_config(&self) -> Res<Vec<u8>>;
    fn claim(&self, intf: u8) -> Res<()>;
    fn set_alt(&self, intf: u8, alt: u8) -> Res<()>;
    fn ctrl_in(&self, rt: u8, req: u8, val: u16, idx: u16, len: usize) -> Res<Vec<u8>>;
    fn ctrl_out(&self, rt: u8, req: u8, val: u16, idx: u16, data: &[u8]) -> Res<()>;
    fn start_iso(&self, ep: u8, pkt_len: usize, npkts: usize, nxfers: usize, sink: IsoSink) -> Res<Box<dyn IsoStream>>;
}

pub trait Backend {
    fn name(&self) -> &'static str;
    fn list(&self) -> Res<Vec<DevSummary>>;
    fn open(&self, vid: u16, pid: u16, serial: Option<&str>, port_path: Option<&[u8]>) -> Res<Box<dyn Dev>>;
}

pub fn port_path_str(p: &[u8]) -> String {
    p.iter().map(|x| x.to_string()).collect::<Vec<_>>().join(".")
}
