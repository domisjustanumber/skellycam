//! libusb backend via libusb1-sys 0.7.0 (feature `vendored` builds libusb 1.0.27 from source with
//! the cc crate, so no system libusb is needed on Windows/macOS; on Linux it needs libudev-dev or
//! falls back to netlink). rusb 0.9.4's *safe* API has no isochronous transfers, so this uses
//! the raw libusb async API: libusb_alloc_transfer(n_iso) + libusb_fill_iso_transfer.
//! libusb 1.0.27 Windows backend: iso via WinUsb_ReadIsochPipeAsap (Windows 8.1+), see
//! libusb/os/windows_winusb.c in the vendored source.

use crate::hostclock::host_ns;
use crate::usb::*;
use libusb1_sys as ffi;
use libusb1_sys::constants::*;
use serde_json::json;
use std::ffi::CStr;
use std::os::raw::{c_int, c_uint, c_void};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;

fn err(rc: c_int) -> String {
    unsafe { CStr::from_ptr(ffi::libusb_error_name(rc)).to_string_lossy().into_owned() }
}

struct Ctx(*mut ffi::libusb_context);
unsafe impl Send for Ctx {}
unsafe impl Sync for Ctx {}

pub struct LibUsb {
    ctx: Arc<Ctx>,
}

impl LibUsb {
    pub fn new() -> Res<Self> {
        let mut c = std::ptr::null_mut();
        let rc = unsafe { ffi::libusb_init(&mut c) };
        if rc != 0 {
            return Err(format!("libusb_init: {}", err(rc)));
        }
        Ok(LibUsb { ctx: Arc::new(Ctx(c)) })
    }
}

/// Rebuild a raw configuration descriptor from libusb's parsed tree (interfaces + class-specific
/// `extra` blobs + endpoints + endpoint extras). Order of class-specific blocks is preserved
/// within each interface, which is all uvc::UvcInfo::parse needs.
unsafe fn rebuild_raw(cfg: *const ffi::libusb_config_descriptor) -> Vec<u8> {
    unsafe {
        let c = &*cfg;
        let mut v = vec![c.bLength, c.bDescriptorType, 0, 0, c.bNumInterfaces, c.bConfigurationValue, c.iConfiguration, c.bmAttributes, c.bMaxPower];
        if !c.extra.is_null() && c.extra_length > 0 {
            v.extend_from_slice(std::slice::from_raw_parts(c.extra, c.extra_length as usize));
        }
        for i in 0..c.bNumInterfaces as usize {
            let itf = &*c.interface.add(i);
            for a in 0..itf.num_altsetting as usize {
                let d = &*itf.altsetting.add(a);
                v.extend_from_slice(&[9, 4, d.bInterfaceNumber, d.bAlternateSetting, d.bNumEndpoints, d.bInterfaceClass, d.bInterfaceSubClass, d.bInterfaceProtocol, d.iInterface]);
                if !d.extra.is_null() && d.extra_length > 0 {
                    v.extend_from_slice(std::slice::from_raw_parts(d.extra, d.extra_length as usize));
                }
                for e in 0..d.bNumEndpoints as usize {
                    let ep = &*d.endpoint.add(e);
                    let m = ep.wMaxPacketSize.to_le_bytes();
                    v.extend_from_slice(&[7, 5, ep.bEndpointAddress, ep.bmAttributes, m[0], m[1], ep.bInterval]);
                    if !ep.extra.is_null() && ep.extra_length > 0 {
                        v.extend_from_slice(std::slice::from_raw_parts(ep.extra, ep.extra_length as usize));
                    }
                }
            }
        }
        let n = (v.len() as u16).to_le_bytes();
        v[2] = n[0];
        v[3] = n[1];
        v
    }
}

fn speed_name(s: c_int) -> String {
    match s {
        LIBUSB_SPEED_LOW => "Low",
        LIBUSB_SPEED_FULL => "Full",
        LIBUSB_SPEED_HIGH => "High",
        LIBUSB_SPEED_SUPER => "Super",
        LIBUSB_SPEED_SUPER_PLUS => "SuperPlus",
        _ => "Unknown",
    }
    .into()
}

unsafe fn summarize(dev: *mut ffi::libusb_device, h: Option<*mut ffi::libusb_device_handle>) -> DevSummary {
    unsafe {
        let mut dd = std::mem::zeroed::<ffi::libusb_device_descriptor>();
        ffi::libusb_get_device_descriptor(dev, &mut dd);
        let mut ports = [0u8; 8];
        let n = ffi::libusb_get_port_numbers(dev, ports.as_mut_ptr(), 8);
        let mut cfg: *const ffi::libusb_config_descriptor = std::ptr::null();
        let rc = ffi::libusb_get_active_config_descriptor(dev, &mut cfg);
        let (raw, raw_err) = if rc == 0 {
            let r = rebuild_raw(cfg);
            ffi::libusb_free_config_descriptor(cfg);
            (Some(r), None)
        } else {
            (None, Some(err(rc)))
        };
        let serial = h.and_then(|h| {
            if dd.iSerialNumber == 0 {
                return None;
            }
            let mut b = [0u8; 256];
            let n = ffi::libusb_get_string_descriptor_ascii(h, dd.iSerialNumber, b.as_mut_ptr(), 256);
            (n > 0).then(|| String::from_utf8_lossy(&b[..n as usize]).into_owned())
        });
        DevSummary {
            vid: dd.idVendor,
            pid: dd.idProduct,
            bus: ffi::libusb_get_bus_number(dev),
            address: ffi::libusb_get_device_address(dev),
            port_path: if n > 0 { ports[..n as usize].to_vec() } else { vec![] },
            speed: speed_name(ffi::libusb_get_device_speed(dev)),
            serial,
            raw_config: raw,
            raw_config_error: raw_err,
        }
    }
}

impl Backend for LibUsb {
    fn name(&self) -> &'static str {
        "libusb1-sys-0.7.0(libusb-1.0.27)"
    }
    fn list(&self) -> Res<Vec<DevSummary>> {
        unsafe {
            let mut list: *const *mut ffi::libusb_device = std::ptr::null();
            let n = ffi::libusb_get_device_list(self.ctx.0, &mut list);
            if n < 0 {
                return Err(err(n as c_int));
            }
            let mut out = vec![];
            for i in 0..n as usize {
                out.push(summarize(*list.add(i), None));
            }
            ffi::libusb_free_device_list(list, 1);
            Ok(out)
        }
    }
    fn open(&self, vid: u16, pid: u16, serial: Option<&str>, port_path: Option<&[u8]>) -> Res<Box<dyn Dev>> {
        unsafe {
            let mut list: *const *mut ffi::libusb_device = std::ptr::null();
            let n = ffi::libusb_get_device_list(self.ctx.0, &mut list);
            if n < 0 {
                return Err(err(n as c_int));
            }
            let mut found = None;
            let mut last_err = String::from("not found");
            for i in 0..n as usize {
                let d = *list.add(i);
                let s = summarize(d, None);
                if s.vid != vid || s.pid != pid || port_path.map(|p| s.port_path != p).unwrap_or(false) {
                    continue;
                }
                let mut h = std::ptr::null_mut();
                let rc = ffi::libusb_open(d, &mut h);
                if rc != 0 {
                    last_err = format!("libusb_open: {}", err(rc));
                    continue;
                }
                let s = summarize(d, Some(h));
                if let Some(want) = serial {
                    if s.serial.as_deref() != Some(want) {
                        ffi::libusb_close(h);
                        continue;
                    }
                }
                ffi::libusb_ref_device(d);
                ffi::libusb_set_auto_detach_kernel_driver(h, 1);
                found = Some(LDev { ctx: self.ctx.clone(), dev: d as usize, h: h as usize, claimed: std::sync::Mutex::new(vec![]) });
                break;
            }
            ffi::libusb_free_device_list(list, 1);
            found.map(|d| Box::new(d) as Box<dyn Dev>).ok_or(last_err)
        }
    }
}

pub struct LDev {
    ctx: Arc<Ctx>,
    dev: usize,
    h: usize,
    claimed: std::sync::Mutex<Vec<u8>>,
}

impl LDev {
    fn h(&self) -> *mut ffi::libusb_device_handle {
        self.h as *mut _
    }
}

impl Drop for LDev {
    fn drop(&mut self) {
        unsafe {
            for i in self.claimed.lock().unwrap().iter() {
                ffi::libusb_release_interface(self.h(), *i as c_int);
            }
            ffi::libusb_close(self.h());
            ffi::libusb_unref_device(self.dev as *mut _);
        }
    }
}

impl Dev for LDev {
    fn summary(&self) -> DevSummary {
        unsafe { summarize(self.dev as *mut _, Some(self.h())) }
    }
    fn raw_config(&self) -> Res<Vec<u8>> {
        // Real raw bytes straight from the device: GET_DESCRIPTOR(CONFIGURATION, 0).
        let hdr = self.ctrl_in(0x80, 0x06, 0x0200, 0, 9)?;
        if hdr.len() < 4 {
            return Err("short config header".into());
        }
        let total = u16::from_le_bytes([hdr[2], hdr[3]]) as usize;
        self.ctrl_in(0x80, 0x06, 0x0200, 0, total)
    }
    fn claim(&self, intf: u8) -> Res<()> {
        let rc = unsafe { ffi::libusb_claim_interface(self.h(), intf as c_int) };
        if rc != 0 {
            return Err(format!("libusb_claim_interface({intf}): {}", err(rc)));
        }
        self.claimed.lock().unwrap().push(intf);
        Ok(())
    }
    fn set_alt(&self, intf: u8, alt: u8) -> Res<()> {
        let rc = unsafe { ffi::libusb_set_interface_alt_setting(self.h(), intf as c_int, alt as c_int) };
        if rc != 0 {
            return Err(format!("libusb_set_interface_alt_setting({intf},{alt}): {}", err(rc)));
        }
        Ok(())
    }
    fn ctrl_in(&self, rt: u8, req: u8, val: u16, idx: u16, len: usize) -> Res<Vec<u8>> {
        let mut b = vec![0u8; len];
        let rc = unsafe { ffi::libusb_control_transfer(self.h(), rt, req, val, idx, b.as_mut_ptr(), len as u16, 2000) };
        if rc < 0 {
            return Err(err(rc));
        }
        b.truncate(rc as usize);
        Ok(b)
    }
    fn ctrl_out(&self, rt: u8, req: u8, val: u16, idx: u16, data: &[u8]) -> Res<()> {
        let mut d = data.to_vec();
        let rc = unsafe { ffi::libusb_control_transfer(self.h(), rt, req, val, idx, d.as_mut_ptr(), d.len() as u16, 2000) };
        if rc < 0 {
            return Err(err(rc));
        }
        Ok(())
    }
    fn start_iso(&self, ep: u8, pkt_len: usize, npkts: usize, nxfers: usize, sink: IsoSink) -> Res<Box<dyn IsoStream>> {
        let shared = Arc::new(Shared { stop: AtomicBool::new(false), inflight: AtomicU64::new(0), completed: AtomicU64::new(0), failed: AtomicU64::new(0), sink, pkt_len });
        let mut xfers = vec![];
        let mut bufs: Vec<Vec<u8>> = vec![];
        for _ in 0..nxfers {
            let mut buf = vec![0u8; pkt_len * npkts];
            unsafe {
                let t = ffi::libusb_alloc_transfer(npkts as c_int);
                if t.is_null() {
                    return Err("libusb_alloc_transfer failed".into());
                }
                ffi::libusb_fill_iso_transfer(t, self.h(), ep, buf.as_mut_ptr(), buf.len() as c_int, npkts as c_int, iso_cb, Arc::as_ptr(&shared) as *mut c_void, 0);
                ffi::libusb_set_iso_packet_lengths(t, pkt_len as c_uint);
                xfers.push(t as usize);
            }
            bufs.push(buf);
        }
        for &t in &xfers {
            let rc = unsafe { ffi::libusb_submit_transfer(t as *mut _) };
            if rc != 0 {
                return Err(format!("libusb_submit_transfer: {}", err(rc)));
            }
            shared.inflight.fetch_add(1, Ordering::SeqCst);
        }
        // event thread
        let ctx = self.ctx.clone();
        let sh2 = shared.clone();
        let ev = std::thread::spawn(move || {
            let tv = libc::timeval { tv_sec: 0, tv_usec: 100_000 };
            while sh2.inflight.load(Ordering::SeqCst) > 0 {
                unsafe { ffi::libusb_handle_events_timeout_completed(ctx.0, &tv, std::ptr::null_mut()) };
            }
        });
        Ok(Box::new(LStream { shared, xfers, _bufs: bufs, ev: Some(ev) }))
    }
}

struct Shared {
    stop: AtomicBool,
    inflight: AtomicU64,
    completed: AtomicU64,
    failed: AtomicU64,
    sink: IsoSink,
    pkt_len: usize,
}

extern "system" fn iso_cb(t: *mut ffi::libusb_transfer) {
    let host = host_ns();
    unsafe {
        let sh = &*((*t).user_data as *const Shared);
        let st = (*t).status;
        if st == LIBUSB_TRANSFER_COMPLETED {
            sh.completed.fetch_add(1, Ordering::Relaxed);
            let n = (*t).num_iso_packets as usize;
            let descs = std::slice::from_raw_parts((*t).iso_packet_desc.as_ptr(), n);
            let lens: Vec<(u32, bool)> = descs.iter().map(|d| (d.actual_length, d.status == LIBUSB_TRANSFER_COMPLETED)).collect();
            let buf = std::slice::from_raw_parts((*t).buffer, sh.pkt_len * n);
            (sh.sink)(host, buf, &lens, sh.pkt_len);
        } else {
            sh.failed.fetch_add(1, Ordering::Relaxed);
        }
        let resubmit = !sh.stop.load(Ordering::SeqCst) && st != LIBUSB_TRANSFER_NO_DEVICE && st != LIBUSB_TRANSFER_CANCELLED;
        if !(resubmit && ffi::libusb_submit_transfer(t) == 0) {
            sh.inflight.fetch_sub(1, Ordering::SeqCst);
        }
    }
}

struct LStream {
    shared: Arc<Shared>,
    xfers: Vec<usize>,
    _bufs: Vec<Vec<u8>>,
    ev: Option<std::thread::JoinHandle<()>>,
}
unsafe impl Send for LStream {}

impl IsoStream for LStream {
    fn stop(mut self: Box<Self>) -> serde_json::Value {
        self.shared.stop.store(true, Ordering::SeqCst);
        for &t in &self.xfers {
            unsafe { ffi::libusb_cancel_transfer(t as *mut _) };
        }
        if let Some(ev) = self.ev.take() {
            let _ = ev.join();
        }
        for &t in &self.xfers {
            unsafe { ffi::libusb_free_transfer(t as *mut _) };
        }
        json!({"transfers_completed": self.shared.completed.load(Ordering::SeqCst), "transfers_failed": self.shared.failed.load(Ordering::SeqCst)})
    }
}
