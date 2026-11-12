"""pymf: a pure-Python Media Foundation camera probe (comtypes + ctypes; no compiled extension).

It answers Dom's build-language question (docs/capture_stack_options_plan.md section 8): can the Windows capture
backend be native Python and still match the C++ probe ``native/wincam.exe``? It ports wincam's MF half one
function at a time, keeps wincam's JSON field names, and is compared with wincam by ``tests/w_pymf.py`` (W-PYMF).

Modules:
    parse.py    pure functions (no COM; any OS): JPEG checks, the KSCAMERA_METADATA_ITEMHEADER /
                KSSTREAM_UVC_METADATA walk, native-type selection, device matching, control tables, HRESULT names
    com.py      comtypes interface declarations (vtable order checked against the SDK headers; table in its
                docstring), GUIDs, PROPVARIANT / KS structs, MF / ole32 / kernel32 entry points
    bounded.py  bounded calls (worker thread + deadline), wincam's timed()
    mf.py       enumerate / activate / formats / controls / async capture session / safe close order
    cli.py      PEP 723 entry point: list, formats, controls, capture, cycle, multi (JSON close to wincam's)
    multi.py    several cameras in one process (one async reader + thread per camera; W-PYMF-ALL)
    framerec.py pure: multi's per-frame record file (frames.bin), fault kinds, control value rule, watchdog
    sdk_10.0.22621_reference.json   vtable orders and GUIDs extracted from the SDK 10.0.22621.0 headers

Run:
    uv run --script research/usb_cameras/suite/windows/pymf/cli.py list
    uv run --script research/usb_cameras/suite/windows/pymf/cli.py capture --device <MF symlink> --width 1280 \\
        --height 720 --fps 30 --seconds 5 --timeout-ms 5000 --out-dir <dir> --save every:10

Every camera-opening command must run under tools/camlock.py (the suite's ctx.camcmd does this).
"""
VERSION = "pymf 0.3 (2026-11-11)"
