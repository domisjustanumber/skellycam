# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1"]
# ///
"""Synthetic skellycam take for the playback A/V-sync test (2026-11-15). No camera or microphone is opened.

Video: per camera an MJPEG .mkv with index pts (pts = MKV index at time base 1/30, as plan WP 1.5) and one CSV timing
sidecar `<cam>.csv`: index,frame_number,arrival_ns,byte_offset,byte_size (arrival_ns since take start; offsets found by
scanning the finished MKV). Real frame rates differ from the nominal 30 (29.97, +50 ppm, 25.7 with drops), arrival times
jitter (N(0,1.5 ms) + 1 % spikes of 6-15 ms) and ~0.3 % of frames are dropped, so index pts are wrong and the player must
use the sidecar. Every frame carries a 20-bit barcode of its MKV index in rows 0-15 (16 px blocks); about once a second
every camera shows a white "flash" frame (the first frame at or after the event time).

Audio (mono, 48 kHz, s16 source): device sample n has host time t_a0 + n / f_eff with f_eff = 48000 * (1 + 10e-6)
(+10 ppm vs the host clock). Low noise (sd 100) plus a one-sample click of 29,000 at the host time of each camera-0 flash
frame (the frame's sidecar arrival time). Written as:
  <take>.audio.wav        PyAV wav muxer, rf64=auto
  <take>.audio.flac       PyAV native FLAC, frame_size=1024
  <take>.audio.m4a        Opus 128 kbit/s, fragmented MP4, one fragment per packet (pre-skip 312)
  <take>.audio_ps0.m4a    the same bytes with pre-skip patched to 0 (opus/preskip0.patch)
each with its own CSV sidecar `<audio file>.csv` (layout of results/audio_single_file/FINDINGS.md §3.1, mono) and the fit footer
(least squares of adc_ns on first_sample, rows after 2 s). The ps0 CSV says file_sample_offset=312
(file sample = device sample + 312).
Truth: truth.json (flash frames, click device samples, true audio clock, fitted values).

Usage: uv run --script gen_take.py short|long        (short = 60 s, 3 cameras; long = 3600 s, 1 camera)
Media go to <scratch>/audio_single_file/skellycam_playback/<take>/.
"""
import fractions
import json
import mmap
import os
import shutil
import sys
import time
import zlib

import av
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True  # keep opus/ free of __pycache__
sys.path.insert(0, os.path.join(HERE, "..", "opus"))
import preskip0  # noqa: E402  (its patch() is the lossless pre-skip 0 header patch)

SCRATCH = os.path.join(r"C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\ef960e37-035d-4929-84c6-9e035d622496"
                       r"\scratchpad\audio_single_file\skellycam_playback")
SR, BLOCK, CLICK, PPM = 48000, 1024, 29000, 10.0
F_EFF = SR * (1 + PPM * 1e-6)
T_A0 = 0.0373  # host time of device sample 0 (s)
W, H, FPS_NOM = 320, 240, 30
CAMS = {  # name: (real fps, first arrival s, drop probability)
    "cam0": (29.97, 0.061, 0.003),
    "cam1": (30.0 * (1 + 50e-6), 0.074, 0.003),
    "cam2": (25.7, 0.093, 0.003),
}


def cam_times(rng, fps, t_first, drop, dur):
    n = int((dur - t_first) * fps)
    k = np.arange(n)
    t = t_first + k / fps + rng.normal(0, 1.5e-3, n)
    spikes = rng.random(n) < 0.01
    t[spikes] += rng.uniform(6e-3, 15e-3, spikes.sum())
    keep = rng.random(n) > drop
    keep[0] = True
    k, t = k[keep], t[keep]
    for i in range(1, len(t)):  # arrivals are monotonic
        t[i] = max(t[i], t[i - 1] + 1e-3)
    return k, t


def frame_yuv(index, flash):
    y = np.full((H, W), 235 if flash else 60, np.uint8)
    for b in range(20):
        y[0:16, 16 * b:16 * b + 16] = 235 if (index >> b) & 1 else 16
    if flash:
        y[0:16, 16 * 20:] = 16  # keep the barcode row readable against the white frame
    uv = np.full((H // 2, W), 128, np.uint8)  # U then V, each H/2 x W/2, packed as yuv420p rows
    return np.vstack([y, uv])


def write_mkv(path, flash_set, n_frames):
    out = av.open(path, "w", format="matroska")
    st = out.add_stream("mjpeg", rate=FPS_NOM)
    st.width, st.height, st.pix_fmt = W, H, "yuvj420p"
    sizes = []
    tb = fractions.Fraction(1, FPS_NOM)
    for i in range(n_frames):
        fr = av.VideoFrame.from_ndarray(frame_yuv(i, i in flash_set), format="yuvj420p")
        fr.pts, fr.time_base = i, tb
        for p in st.encode(fr):
            p.time_base, p.pts, p.dts = tb, i, i  # fixed 1/fps time base, index pts
            sizes.append(p.size)
            out.mux(p)
    for p in st.encode(None):
        sizes.append(p.size)
        out.mux(p)
    out.close()
    assert len(sizes) == n_frames, (len(sizes), n_frames)
    offs = []
    with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as d:
        pos = 0
        for s in sizes:
            j = d.find(b"\xff\xd8\xff", pos)
            assert j >= 0 and d[j + s - 2:j + s] == b"\xff\xd9", (j, s)
            offs.append(j)
            pos = j + s
    return offs, sizes


class AudioWriter:
    def __init__(self, path, fmt, codec, copts, mopts):
        self.out = av.open(path, "w", format=fmt, options=mopts)
        self.st = self.out.add_stream(codec, rate=SR, layout="mono")
        self.st.codec_context.options = copts
        self.st.time_base = fractions.Fraction(1, SR)
        self.n = 0

    def write(self, block):
        fr = av.AudioFrame.from_ndarray(block.reshape(1, -1), format="s16", layout="mono")
        fr.sample_rate, fr.pts, fr.time_base = SR, self.n, fractions.Fraction(1, SR)
        self.n += len(block)
        for p in self.st.encode(fr):
            self.out.mux(p)

    def close(self):
        for p in self.st.encode(None):
            self.out.mux(p)
        self.out.close()


AUDIO = {  # key: (file suffix, container, codec, codec opts, muxer opts)
    "wav": (".audio.wav", "wav", "pcm_s16le", {}, {"rf64": "auto", "flush_packets": "1"}),
    "flac": (".audio.flac", "flac", "flac", {"frame_size": "1024"}, {"flush_packets": "1"}),
    "opus": (".audio.m4a", "mp4", "libopus",
             {"b": "128000", "frame_duration": "20", "application": "audio", "vbr": "on", "compression_level": "10"},
             {"flush_packets": "1", "movflags": "empty_moov+default_base_moof+frag_every_frame"}),
}


def csv_text(rows, fit, end, codec, container, extra):
    hdr = ["# skellycam_audio_timing=0", "# take_uuid=00000000-0000-4000-8000-000000000000", f"# sample_rate={SR}",
           "# channels=1", f"# codec={codec}", f"# container={container}", "# clock=QPC", "# clock_hz=10000000",
           "# host_ns_origin=take_start", "# sample_index_origin=first_sample_in_file", "# device=synthetic",
           "# host_api=WASAPI", f"# block={BLOCK}"] + [f"# {k}={v}" for k, v in extra.items()]
    body = []
    for b, (first, host, adc) in enumerate(rows):
        s = f"{b},{first},{BLOCK},{host},{adc},0"
        body.append(f"{s},{zlib.crc32(s.encode()):08x}")
    foot = [f"# fit segment=0 first_row={fit['first_row']} rows={fit['rows']} n0=0 t0_ns={fit['t0_ns']:.1f} "
            f"rate_hz={fit['rate_hz']:.6f} ppm={fit['ppm']:.3f} resid_p99_ns={fit['resid_p99_ns']:.0f}",
            f"# end rows={len(rows)} samples={end}"]
    return "\n".join(hdr + ["block,first_sample,n_samples,host_ns,adc_ns,flags,crc32"] + body + foot) + "\n"


def main(take):
    t_start = time.time()
    dur = 60.0 if take == "short" else 3600.0
    cams = CAMS if take == "short" else {"cam0": CAMS["cam0"]}
    out_dir = os.path.join(SCRATCH, take)
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(20261115)
    times = {c: cam_times(rng, *v, dur) for c, v in cams.items()}
    events = [j + 0.37 * np.sin(j) for j in range(1, int(dur) - 1)]  # irregular, about 1 s apart
    truth = dict(take=take, duration_s=dur, sr=SR, ppm=PPM, f_eff=F_EFF, t_a0=T_A0, cams={}, flashes=[])
    for c, (k, t) in times.items():
        flash = sorted({int(np.searchsorted(t, e)) for e in events if np.searchsorted(t, e) < len(t)})
        path = os.path.join(out_dir, f"{c}.mkv")
        offs, sizes = write_mkv(path, set(flash), len(t))
        with open(os.path.join(out_dir, f"{c}.csv"), "w", newline="\n") as f:
            f.write(f"# skellycam_video_timing=0\n# camera={c}\n# fps_nominal={FPS_NOM}\n# fps_real={cams[c][0]}\n"
                    "index,frame_number,arrival_ns,byte_offset,byte_size\n")
            for i in range(len(t)):
                f.write(f"{i},{k[i]},{round(t[i] * 1e9)},{offs[i]},{sizes[i]}\n")
        truth["cams"][c] = dict(file=f"{c}.mkv", csv=f"{c}.csv", frames=len(t), flash_index=flash,
                                fps_real=cams[c][0], mkv_bytes=os.path.getsize(path))
        print(c, len(t), "frames", os.path.getsize(path) // 1024, "KiB", round(time.time() - t_start, 1), "s", flush=True)
    t0 = times["cam0"][1]
    flash0 = truth["cams"]["cam0"]["flash_index"]
    click_t = np.array([t0[i] for i in flash0])
    click_n = np.round((click_t - T_A0) * F_EFF).astype(np.int64)
    truth["flashes"] = [dict(cam0_index=int(i), host_s=float(ts), device_sample=int(n))
                        for i, ts, n in zip(flash0, click_t, click_n)]
    n_total = int(np.ceil((dur + 0.5 - T_A0) * F_EFF / BLOCK)) * BLOCK
    x = np.clip(rng.normal(0, 100, n_total), -32768, 32767).astype(np.int16)
    x[click_n] = CLICK
    # CSV rows: adc_ns = true time of first sample + N(0, 0.7 ms); host_ns = callback = end of block + 2 ms + exp(1 ms)
    first = np.arange(0, n_total, BLOCK)
    adc_true = T_A0 + first / F_EFF
    adc = np.round((adc_true + rng.normal(0, 0.7e-3, len(first))) * 1e9).astype(np.int64)
    host = np.round((adc_true + BLOCK / F_EFF + 2e-3 + rng.exponential(1e-3, len(first))) * 1e9).astype(np.int64)
    sel = adc_true > 2.0
    slope, icpt = np.polyfit(first[sel].astype(np.float64), adc[sel].astype(np.float64), 1)
    resid = adc[sel] - (icpt + slope * first[sel])
    fit = dict(first_row=int(np.argmax(sel)), rows=int(sel.sum()), t0_ns=float(icpt), rate_hz=1e9 / slope,
               ppm=(1e9 / slope / SR - 1) * 1e6, resid_p99_ns=float(np.percentile(np.abs(resid), 99)))
    truth["fit"] = fit
    truth["fit_error_at_end_ms"] = float(((icpt + slope * n_total) / 1e9 - (T_A0 + n_total / F_EFF)) * 1e3)
    rows = list(zip(first.tolist(), host.tolist(), adc.tolist()))
    truth["audio"] = {}
    for key, (suffix, fmt, codec, copts, mopts) in AUDIO.items():
        path = os.path.join(out_dir, take + suffix)
        t1 = time.time()
        w = AudioWriter(path, fmt, codec, copts, mopts)
        for b in range(0, n_total, BLOCK):
            w.write(x[b:b + BLOCK])
        w.close()
        extra = {"pre_skip": 312, "opus_frame": 960, "bitrate": 128000} if key == "opus" else {}
        with open(path + ".csv", "w", newline="\n") as f:  # one CSV per audio file: <audio file>.csv
            f.write(csv_text(rows, fit, n_total, codec, fmt, extra))
        truth["audio"][key] = dict(file=os.path.basename(path), bytes=os.path.getsize(path), encode_s=round(time.time() - t1, 1))
        print(key, os.path.getsize(path) // 1024, "KiB", round(time.time() - t1, 1), "s", flush=True)
    ps0 = os.path.join(out_dir, take + ".audio_ps0.m4a")
    shutil.copyfile(os.path.join(out_dir, take + ".audio.m4a"), ps0)
    done = preskip0.patch(ps0)
    with open(ps0 + ".csv", "w", newline="\n") as f:
        f.write(csv_text(rows, fit, n_total, "libopus", "mp4",
                         {"pre_skip": 0, "opus_frame": 960, "bitrate": 128000, "file_sample_offset": 312}))
    truth["audio"]["opus_ps0"] = dict(file=os.path.basename(ps0), bytes=os.path.getsize(ps0), patch=done)
    truth["n_total"] = n_total
    json.dump(truth, open(os.path.join(out_dir, "truth.json"), "w"), indent=1)
    print("done", take, round(time.time() - t_start, 1), "s; fit", fit, "fit err at end ms", truth["fit_error_at_end_ms"])


if __name__ == "__main__":
    main(sys.argv[1])
