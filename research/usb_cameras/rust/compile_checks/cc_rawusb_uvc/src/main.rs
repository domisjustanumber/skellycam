// rawusb's built-in UVC class helper (uvc feature): MJPEG via Camera::start.
fn main() {
    let ctx = rawusb::Context::new().unwrap();
    for d in ctx.devices().unwrap() {
        if let Ok(cam) = rawusb::uvc::Camera::open(&d) {
            if let Some(r) = cam.find_format(*b"MJPG", 1280, 720) {
                if let Ok(s) = cam.start(&r) { let _ = s.next_frame(std::time::Duration::from_secs(2)); }
            }
        }
    }
}
