// Control case for cc_nusb_iso_fail: same code with Bulk compiles.
use nusb::MaybeFuture;
fn main() {
    let Some(info) = nusb::list_devices().wait().unwrap().next() else { return };
    let dev = info.open().wait().unwrap();
    let intf = dev.claim_interface(1).wait().unwrap();
    let _ep = intf.endpoint::<nusb::transfer::Bulk, nusb::transfer::In>(0x81);
}
