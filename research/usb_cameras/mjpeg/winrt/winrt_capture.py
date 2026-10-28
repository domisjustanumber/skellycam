# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "winrt-runtime>=2.0", "winrt-Windows.Media.Capture>=2.0", "winrt-Windows.Media.Capture.Frames>=2.0",
#   "winrt-Windows.Media.MediaProperties>=2.0", "winrt-Windows.Foundation>=2.0", "winrt-Windows.Foundation.Collections>=2.0",
#   "winrt-Windows.Storage.Streams>=2.0", "winrt-Windows.Devices.Enumeration>=2.0", "winrt-Windows.Graphics.Imaging>=2.0",
#   "psutil>=5.9", "pillow>=10", "simplejpeg>=1.7",
# ]
# ///
"""WinRT Windows.Media.Capture MediaFrameReader in MJPG subtype: are compressed buffers delivered?

  uv run --script research/usb_cameras/winrt_capture.py --list
  uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/mjpeg/winrt/winrt_capture.py \
      --dev vid_046d&pid_085c [--dev ...] --size 1280x720 --fps 30 --seconds 10 --run-dir <scratch> [--acq buffered|realtime]

For each frame: MediaFrameReference.SystemRelativeTime (QPC-relative TimeSpan; python winrt exposes it
as datetime.timedelta = 1 us resolution), Duration, Format.Subtype, whether BufferMediaFrame and/or
VideoMediaFrame.SoftwareBitmap are present, and the bytes of BufferMediaFrame.Buffer if present.
Frame properties (MF sample attributes as a GUID-keyed map) are dumped for the first frames.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mjpeg_common as mc  # noqa: E402

from winrt.windows.media.capture import (MediaCapture, MediaCaptureInitializationSettings, MediaCaptureMemoryPreference,  # noqa: E402
                                         MediaCaptureSharingMode, StreamingCaptureMode)
from winrt.windows.media.capture.frames import (MediaFrameReaderAcquisitionMode, MediaFrameSourceGroup,  # noqa: E402
                                                MediaFrameSourceKind)

ap = argparse.ArgumentParser()
ap.add_argument("--list", action="store_true")
ap.add_argument("--dev", action="append", default=[])
ap.add_argument("--mode", action="append", default=[], help="per --dev (same order) WxH@FPS; overrides --size/--fps")
ap.add_argument("--size", default="1280x720")
ap.add_argument("--fps", type=float, default=30)
ap.add_argument("--seconds", type=float, default=10)
ap.add_argument("--warmup", type=float, default=2)
ap.add_argument("--acq", choices=["buffered", "realtime"], default="buffered")
ap.add_argument("--subtype", default="MJPG")
ap.add_argument("--run-dir")
ap.add_argument("--prop-dump", type=int, default=3)
ap.add_argument("--reader-subtype", default=None, help="outputSubtype passed to CreateFrameReaderAsync; 'none' = omit (native); default = --subtype")
ap.add_argument("--memory", choices=["cpu", "auto"], default="cpu")
a = ap.parse_args()
W, H = map(int, a.size.lower().split("x"))


def td_to_ns(td) -> int | None:
    if td is None:
        return None
    if hasattr(td, "duration"):  # raw TimeSpan struct
        return int(td.duration) * 100
    return (td.days * 86400 + td.seconds) * 1_000_000_000 + td.microseconds * 1000


def propval(v):
    try:
        if isinstance(v, (int, float, str, bool)) or v is None:
            return v
        return repr(v)[:120]
    except Exception as e:
        return f"<{e!r}>"


async def list_groups():
    groups = await MediaFrameSourceGroup.find_all_async()
    out = []
    for g in groups:
        out.append({"display_name": g.display_name, "id": g.id,
                    "sources": [{"id": s.id, "kind": int(s.source_kind), "stream_type": int(s.media_stream_type),
                                 "device_id": s.device_information.id if s.device_information else None} for s in g.source_infos]})
    return out


async def main():
    if a.list:
        print(json.dumps(await list_groups(), indent=1))
        return
    writer = mc.RunWriter(Path(a.run_dir))
    groups = await MediaFrameSourceGroup.find_all_async()
    lock = threading.Lock()
    cams = []
    started = mc.utc_now()
    errors = []
    if a.mode and len(a.mode) != len(a.dev):
        raise SystemExit("error: give one --mode per --dev")
    for idx, want in enumerate(a.dev):
        cw, ch, cfps = W, H, a.fps
        if a.mode:
            sz, fr = a.mode[idx].split("@")
            cw, ch = map(int, sz.lower().split("x"))
            cfps = float(fr)
        g = next((g for g in groups if want.lower() in g.id.lower() or want.lower() in g.display_name.lower()
                  or any(s.device_information and want.lower() in s.device_information.id.lower() for s in g.source_infos)), None)
        if g is None:
            raise SystemExit(f"error: no MediaFrameSourceGroup matches {want!r}")
        st = MediaCaptureInitializationSettings()
        st.source_group = g
        st.sharing_mode = MediaCaptureSharingMode.EXCLUSIVE_CONTROL
        st.memory_preference = MediaCaptureMemoryPreference.CPU if a.memory == "cpu" else MediaCaptureMemoryPreference.AUTO
        st.streaming_capture_mode = StreamingCaptureMode.VIDEO
        cap = MediaCapture()
        await cap.initialize_async(st)
        src = None
        for key in cap.frame_sources.keys():
            s = cap.frame_sources[key]
            if s.info.source_kind == MediaFrameSourceKind.COLOR:
                src = s
                break
        if src is None:
            raise SystemExit(f"error: no color source in {g.display_name}")
        fmts = []
        chosen = None
        for f in src.supported_formats:
            fr = f.frame_rate
            fps = fr.numerator / fr.denominator if fr.denominator else 0
            fmts.append(f"{f.subtype} {f.video_format.width}x{f.video_format.height}@{fps:.2f}")
            if chosen is None and f.subtype.upper() == a.subtype.upper() and f.video_format.width == cw and f.video_format.height == ch and abs(fps - cfps) < 0.5:
                chosen = f
        if chosen is None:
            raise SystemExit(f"error: {g.display_name} has no {a.subtype} {cw}x{ch}@{cfps}; formats={sorted(set(fmts))}")
        await src.set_format_async(chosen)
        rsub = a.subtype if a.reader_subtype is None else a.reader_subtype
        reader = await (cap.create_frame_reader_async(src) if rsub.lower() == "none" else cap.create_frame_reader_async(src, rsub))
        reader.acquisition_mode = MediaFrameReaderAcquisitionMode.BUFFERED if a.acq == "buffered" else MediaFrameReaderAcquisitionMode.REALTIME
        info = {"idx": idx, "name": g.display_name, "group_id": g.id, "source_id": src.info.id,
                "device_id": src.info.device_information.id if src.info.device_information else None,
                "chosen_format": f"{chosen.subtype} {cw}x{ch}@{chosen.frame_rate.numerator}/{chosen.frame_rate.denominator}",
                "requested_mode": {"width": cw, "height": ch, "fps": cfps}, "handler_calls": 0, "handler_exceptions": 0, "handler_exception_first": None,
                "current_format_subtype": src.current_format.subtype, "reader_output_subtype": rsub, "memory_preference": a.memory, "acquisition_mode": a.acq, "acquire_errors": 0, "acquire_error_first": None,
                "frames": 0, "frames_with_buffer": 0, "frames_with_softwarebitmap": 0, "frame_subtypes": {}, "property_dumps": [], "null_refs": 0}
        state = {"seq": 0}

        def on_frame(sender, args, idx=idx, info=info, state=state):
            info["handler_calls"] += 1
            try:
                handle_frame(sender, idx, info, state)
            except BaseException as e:  # exceptions in WinRT event callbacks are otherwise swallowed silently
                info["handler_exceptions"] += 1
                info["handler_exception_first"] = info["handler_exception_first"] or repr(e)

        def handle_frame(sender, idx, info, state):
            try:
                ref = sender.try_acquire_latest_frame()
            except OSError as e:
                info["acquire_errors"] += 1
                info["acquire_error_first"] = info["acquire_error_first"] or repr(e)
                return
            t = time.perf_counter_ns()
            if ref is None:
                info["null_refs"] += 1
                return
            try:
                sub = ref.format.subtype
                info["frame_subtypes"][sub] = info["frame_subtypes"].get(sub, 0) + 1
                bmf = ref.buffer_media_frame
                vmf = ref.video_media_frame
                sb = vmf.software_bitmap if vmf is not None else None
                payload = b""
                if bmf is not None and bmf.buffer is not None:
                    payload = bytes(memoryview(bmf.buffer))
                    info["frames_with_buffer"] += 1
                if sb is not None:
                    info["frames_with_softwarebitmap"] += 1
                if len(info["property_dumps"]) < a.prop_dump:
                    try:
                        info["property_dumps"].append({str(k): propval(ref.properties[k]) for k in ref.properties.keys()})
                    except Exception as e:
                        info["property_dumps"].append({"error": repr(e)})
                srt = td_to_ns(ref.system_relative_time)
                with lock:
                    writer.add(idx, {"camera_key": info["device_id"] or info["name"], "backend": "winrt-mediaframereader", "seq": state["seq"],
                                     "host_arrival_ns": t, "os_timestamp_ns": srt,
                                     "os_timestamp_source": "MediaFrameReference.SystemRelativeTime (QPC-relative, us resolution via timedelta)",
                                     "duration_ns": td_to_ns(ref.duration), "frame_subtype": sub, "has_buffer_media_frame": bmf is not None,
                                     "has_software_bitmap": sb is not None,
                                     "sb_format": (f"{int(sb.bitmap_pixel_format)} {sb.pixel_width}x{sb.pixel_height}" if sb is not None else None),
                                     "uvc_pts": None, "uvc_scr_stc": None, "uvc_scr_sof": None, "device_clock_hz": None,
                                     "payload_bytes": len(payload), "is_valid_jpeg": None}, payload)
                state["seq"] += 1
                info["frames"] = state["seq"]
            except Exception as e:
                errors.append(f"{info['name']}: {e!r}")
            finally:
                ref.close()

        reader.add_frame_arrived(on_frame)
        status = await reader.start_async()
        info["start_status"] = int(status)
        cams.append((cap, reader, info))
    await asyncio.sleep(a.warmup)
    cpu = mc.CpuWindow({"frameserver": mc.frameserver_pid()})
    cpu.start()
    w0 = time.perf_counter_ns()
    await asyncio.sleep(a.seconds)
    w1 = time.perf_counter_ns()
    cpu_res = cpu.stop()
    for cap, reader, info in cams:
        await reader.stop_async()
        reader.close()
        cap.close()
    infos = [c[2] for c in cams]
    any_sb = any(i["frames_with_softwarebitmap"] for i in infos)
    all_buf = all(i["frames_with_buffer"] == i["frames"] and i["frames"] > 0 for i in infos)
    subs = {k for i in infos for k in i["frame_subtypes"]}
    jpeg_subs = {"MJPG", "JPEG"}
    any_frames = any(i["frames"] for i in infos)
    meta = {"backend": "winrt-mediaframereader", "utc_started": started, "command": sys.argv, "environment": mc.environment(),
            "requested": {"subtype": a.subtype, "width": W, "height": H, "fps": a.fps},
            # source format is MJPG on the device; if frames arrive with a raw subtype (NV12...), the pipeline decoded them
            "decoded_by_pipeline": (True if (any_sb or (subs - jpeg_subs)) else (False if all_buf else None)) if any_frames else None,
            "delivered_codecs": sorted(subs), "silent_format_fallback": bool(subs - jpeg_subs) if any_frames else None,
            "payload_is_jpeg": bool(subs) and subs <= jpeg_subs and all_buf,
            "decode_evidence": f"frames_with_buffer={[i['frames_with_buffer'] for i in infos]} frames_with_softwarebitmap={[i['frames_with_softwarebitmap'] for i in infos]} subtypes={[i['frame_subtypes'] for i in infos]}",
            "cpu": cpu_res, "cameras": infos, "errors": errors[:50]}
    writer.flush(meta, w0, w1)
    print(json.dumps({"cameras": [{k: i[k] for k in ("name", "frames", "handler_calls", "handler_exceptions", "handler_exception_first", "acquire_errors", "acquire_error_first", "reader_output_subtype", "frames_with_buffer", "frames_with_softwarebitmap", "frame_subtypes", "chosen_format", "current_format_subtype")} for i in infos], "cpu": cpu_res, "errors": errors[:5]}, default=str))


asyncio.run(main())
