// EXPECTED TO FAIL TO COMPILE: nusb 0.2.9 has no isochronous endpoint type.
use nusb::MaybeFuture;
// Interface::endpoint::<EpType, Dir>() requires EpType: EndpointType, which is sealed and only
// implemented by nusb::transfer::{Bulk, Interrupt} (src/transfer/mod.rs).
fn main() {
    let dev = nusb::list_devices().wait().unwrap().next().unwrap().open().wait().unwrap();
    let intf = dev.claim_interface(1).wait().unwrap();
    let _ep = intf.endpoint::<nusb::transfer::Isochronous, nusb::transfer::In>(0x81);
}
