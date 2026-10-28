// rusb 0.9.4's safe API has no isochronous transfer (DeviceHandle offers read/write_bulk,
// _interrupt, _control only). Iso is reachable only through the raw libusb1-sys FFI that rusb
// re-exports as rusb::ffi, against vendored libusb 1.0.27 (which implements WinUSB iso via
// WinUsb_ReadIsochPipeAsap). This compiles a minimal iso submission path.
use rusb::ffi;
use rusb::UsbContext;
extern "system" fn cb(t: *mut ffi::libusb_transfer) {
    unsafe {
        let n = (*t).num_iso_packets;
        let _ = n;
        ffi::libusb_submit_transfer(t);
    }
}
fn main() {
    let ctx = rusb::Context::new().unwrap();
    let v = unsafe { ffi::libusb_get_version() };
    println!("libusb {}.{}.{}", unsafe { (*v).major }, unsafe { (*v).minor }, unsafe { (*v).micro });
    let Some(dev) = ctx.devices().unwrap().iter().find(|d| d.device_descriptor().map(|x| x.class_code() == 0xEF).unwrap_or(false)) else { return };
    let Ok(h) = dev.open() else { return };
    let _ = h.claim_interface(1);
    let _ = h.set_alternate_setting(1, 1);
    unsafe {
        let t = ffi::libusb_alloc_transfer(32);
        let mut buf = vec![0u8; 3072 * 32];
        ffi::libusb_fill_iso_transfer(t, h.as_raw(), 0x81, buf.as_mut_ptr(), buf.len() as i32, 32, cb, std::ptr::null_mut(), 1000);
        ffi::libusb_set_iso_packet_lengths(t, 3072);
        ffi::libusb_submit_transfer(t);
    }
}
