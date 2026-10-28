// uvc 0.2.0 = safe wrapper over libuvc (vendored via uvc-src). Minimal MJPEG stream + PTS access.
fn main() {
    let ctx = uvc::Context::new().expect("ctx");
    for d in ctx.devices().expect("devs") {
        let desc = d.description().unwrap();
        println!("{:04x}:{:04x} serial={:?}", desc.vendor_id, desc.product_id, desc.serial_number);
    }
    let Ok(dev) = ctx.find_device(None, None, None) else { return };
    let Ok(h) = dev.open() else { return };
    let fmt = uvc::StreamFormat { width: 1280, height: 720, fps: 30, format: uvc::FrameFormat::MJPEG };
    let mut sh = h.get_stream_handle_with_format(fmt).unwrap();
    let _s = sh.start_stream(|f, _| { let _ = (f.to_bytes().len(), f.sequence()); }, ()).unwrap();
}
