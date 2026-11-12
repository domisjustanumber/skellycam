"""Compatibility checks for one output MKV (JPEG video + audio): ffprobe, PyAV/FFmpeg decode, OpenCV, VLC, ffplay.

check(path, case, twin=None) -> dict
  case: dict(start_frame, src_fps, out_fps, flash_frames (source indices), channels)
  twin: path of the video-only twin (same JPEGs) for OpenCV pixel comparison.
"""
import fractions, glob, hashlib, json, math, os, re, shutil, subprocess, sys, tempfile

import av
import cv2
import numpy as np
from scipy.io import wavfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

VLC = r"C:\Program Files\VideoLAN\VLC\vlc.exe"


def expected_src_index(case, k):
    src, out = fractions.Fraction(case["src_fps"]), fractions.Fraction(case["out_fps"])
    return case["start_frame"] + math.floor(fractions.Fraction(k) * src / out)


def burst_times(case, first_slot=0):
    """Expected burst onsets in output seconds, relative to output slot `first_slot`."""
    src, out = fractions.Fraction(case["src_fps"]), fractions.Fraction(case["out_fps"])
    return [float(fractions.Fraction(f - case["start_frame"]) / src - fractions.Fraction(first_slot) / out)
            for f in case["flash_frames"] if f >= case["start_frame"]]


def ffprobe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-show_entries",
                        "stream=index,codec_name,codec_type,sample_rate,channels,channel_layout,start_time,nb_read_packets,bits_per_raw_sample,sample_fmt"
                        ":format=duration,nb_streams", "-of", "json", path], capture_output=True, text=True)
    j = json.loads(r.stdout)
    return dict(streams=j["streams"], format=j["format"], stderr=r.stderr.strip()[:300])


def ffmpeg_decode(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", "0", "-f", "null", "-"], capture_output=True, text=True)
    return dict(rc=r.returncode, error_lines=len([l for l in r.stderr.splitlines() if l.strip()]), stderr=r.stderr[:300])


def pyav_check(path, case):
    res = {}
    with av.open(path) as c:
        nums = [C.read_frame_number(f.to_ndarray(format="bgr24")) for f in c.decode(c.streams.video[0])]
    res["video_frames"] = len(nums)
    res["video_frame_exact"] = f"{sum(1 for k, n in enumerate(nums) if n == expected_src_index(case, k))}/{len(nums)}"
    with av.open(path) as c:
        if not c.streams.audio:
            return res
        a = c.streams.audio[0]
        sr = a.rate
        chunks, first_pts = [], None
        for fr in c.decode(a):
            if first_pts is None:
                first_pts = float(fr.pts * fr.time_base)
            x = fr.to_ndarray()
            if fr.format.is_packed:
                x = x.reshape(-1, fr.layout.nb_channels).T
            x = x.astype(np.float64)
            if fr.format.name.startswith("s16"): x /= 32768
            elif fr.format.name.startswith("s32"): x /= 2 ** 31
            chunks.append(x)
    x = np.concatenate(chunks, axis=1)
    res["audio_first_frame_pts_s"] = first_pts
    res["audio_decoded_samples"] = int(x.shape[1])
    res["audio_channels_decoded"] = int(x.shape[0])
    # a leading negative pts means the first decoded samples precede video frame 0
    lead = int(round(-first_pts * sr)) if first_pts and first_pts < 0 else 0
    xl = x[:, lead:] if lead > 0 else x
    res["audio_leading_samples_dropped"] = lead
    times = burst_times(case)
    res["sync_L"] = C.sync_errors_t(xl[0], sr, times, C.F_L, 1.0)
    if x.shape[0] == 2:
        res["sync_R"] = C.sync_errors_t(xl[1], sr, times, C.F_R, -1.0)
        # channel identity: L burst energy on R should be small
        res["channel_identity"] = channel_identity(xl, sr, times)
    return res


def channel_identity(x, sr, times):
    """For each channel, peak |matched filter| with the 3 kHz (L) and 1.5 kHz (R) bursts, summed over bursts.
    L should be dominated by 3 kHz, R by 1.5 kHz; a downmix or swap shows up here."""
    tl, tr = C.burst(sr, C.F_L), C.burst(sr, C.F_R)
    out = {}
    for ch, name in ((0, "L"), (1, "R")):
        el = er = 0.0
        for t in times:
            e = int(round(t * sr))
            seg = x[ch, max(0, e - 200):e + 200 + len(tl)]
            if len(seg) < len(tl): continue
            el += float(np.abs(np.correlate(seg, tl, "valid")).max()); er += float(np.abs(np.correlate(seg, tr, "valid")).max())
        out[name] = dict(f3k=round(el, 2), f1k5=round(er, 2))
    out["ok"] = out["L"]["f3k"] > 5 * out["L"]["f1k5"] and out["R"]["f1k5"] > 5 * out["R"]["f3k"]
    return out


def opencv_check(path, twin=None, n_seeks=11):
    def frames_and_seeks(p):
        cap = cv2.VideoCapture(p, cv2.CAP_FFMPEG)
        cnt = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        hashes = []
        while True:
            ok, fr = cap.read()
            if not ok: break
            hashes.append(hashlib.sha1(fr.tobytes()).hexdigest()[:12])
        seeks = []
        for t in np.linspace(0, len(hashes) - 1, n_seeks).astype(int):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t))
            ok, fr = cap.read()
            seeks.append((int(t), C.read_frame_number(fr) if ok else None, hashlib.sha1(fr.tobytes()).hexdigest()[:12] if ok else None))
        cap.release()
        return cnt, hashes, seeks
    cnt, hashes, seeks = frames_and_seeks(path)
    res = dict(cap_prop_frame_count=cnt, frames_read=len(hashes),
               seeks_match_sequential=f"{sum(1 for t, n, h in seeks if h == hashes[t])}/{len(seeks)}")
    if twin:
        c2, h2, s2 = frames_and_seeks(twin)
        res["twin_frame_count"] = c2
        res["pixels_identical_to_video_only_twin"] = f"{sum(1 for a, b in zip(hashes, h2) if a == b)}/{len(h2)}"
        res["seeks_identical_to_twin"] = f"{sum(1 for a, b in zip(seeks, s2) if a == b)}/{len(s2)}"
    return res


def vlc_run(path, case, start_time=None, timeout=60):
    # VLC 3.0.24 hung (no log) when launched with forward-slash paths or CREATE_NO_WINDOW; use native paths
    d = os.path.normpath(tempfile.mkdtemp(prefix="vlc_", dir=os.environ.get("VLC_TMP")))
    path = os.path.normpath(path)
    wav = os.path.join(d, "out.wav"); log = os.path.join(d, "vlc.log")
    args = [VLC, "-I", "dummy", "--vout=dummy", "--play-and-exit", "--no-loop",
            "--aout=afile", f"--audiofile-file={wav}", "--audiofile-wav",
            "--video-filter=scene", "--scene-format=png", "--scene-ratio=1", f"--scene-path={d}", "--scene-prefix=f",
            "--verbose=2", "--file-logging", f"--logfile={log}"]
    if start_time:
        args.append(f"--start-time={start_time}")
    args.append(path)
    try:
        p = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        rc = p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        rc = "timeout"
    pngs = sorted(glob.glob(os.path.join(d, "f*.png")))
    nums = [C.read_frame_number(cv2.imread(p)) for p in pngs]
    res = dict(rc=rc, pngs=len(pngs), first_frame_number=nums[0] if nums else None,
               last_frame_number=nums[-1] if nums else None)
    if nums:
        exp = [expected_src_index(case, k) for k in range(10000)]
        inv = {s: k for k, s in reversed(list(enumerate(exp)))}
        # VLC's scene filter sometimes writes one stale pre-seek frame (slot 0) before the seek lands
        stale = 1 if (start_time and len(nums) > 1 and nums[1] - nums[0] > 2) else 0
        res["stale_first_png"] = bool(stale)
        first_slot = inv.get(nums[stale])
        res["first_slot"] = first_slot
        res["first_frame_after_seek"] = nums[stale]
        res["monotonic"] = all(b >= a for a, b in zip(nums, nums[1:]))
    txt = open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else ""
    res["log"] = dict(
        demux_mkv="mkv demux" in txt or "matroska" in txt.lower(),
        opus_decoder=bool(re.search(r"using audio decoder module \"opus\"", txt)),
        flac_decoder=bool(re.search(r"using audio decoder module \"flac\"", txt)),
        avcodec_audio=bool(re.search(r"using audio decoder module \"avcodec\"", txt)),
        audio_decoder_lines=re.findall(r"using audio decoder module \"([^\"]+)\"", txt)[:2],
        video_decoder_lines=re.findall(r"using video decoder module \"([^\"]+)\"", txt)[:2],
        too_late=len(re.findall(r"too late", txt)), mkv_error=len(re.findall(r"mkv error", txt, re.I)),
        discontinuity=len(re.findall(r"discontinuity", txt, re.I)),
        errors=len(re.findall(r" error: ", txt)))
    if os.path.exists(wav) and os.path.getsize(wav) > 100:
        sr, x = wavfile.read(wav)
        x = x.astype(np.float64)
        if x.ndim == 1: x = x[:, None]
        if np.issubdtype(x.dtype, np.integer) or np.abs(x).max() > 2: x /= 32768
        res["wav"] = dict(rate=int(sr), channels=int(x.shape[1]), seconds=round(x.shape[0] / sr, 3))
        if nums and res.get("first_slot") is not None:
            times = burst_times(case, res["first_slot"])
            res["sync_L_vs_first_png"] = C.sync_errors_t(x[:, 0], sr, times, C.F_L, 1.0)
            if x.shape[1] >= 2 and case.get("channels", 2) == 2:
                res["sync_R_vs_first_png"] = C.sync_errors_t(x[:, 1], sr, times, C.F_R, -1.0)
    else:
        res["wav"] = None
    shutil.rmtree(d, ignore_errors=True)
    return res


def ffplay_run(path, timeout=60):
    env = dict(os.environ, SDL_AUDIODRIVER="dummy", SDL_VIDEODRIVER="dummy")
    try:
        p = subprocess.run(["ffplay", "-autoexit", "-loglevel", "warning", "-stats", path], env=env,
                           capture_output=True, text=True, timeout=timeout)
        err = p.stderr
        warn = [l for l in err.replace("\r", "\n").splitlines() if l.strip() and not re.match(r"^\s*-?\d+\.\d+ (A-V|M-A|M-V)", l.strip())]
        avlines = re.findall(r"(-?\d+\.\d+) A-V:\s*(-?\d+\.\d+)", err)
        return dict(rc=p.returncode, warnings=warn[:5],
                    last_av_diff_s=float(avlines[-1][1]) if avlines else None,
                    max_abs_av_diff_s=max(abs(float(b)) for a, b in avlines) if avlines else None,
                    clock_end_s=float(avlines[-1][0]) if avlines else None)
    except subprocess.TimeoutExpired:
        return dict(rc="timeout")


def check(path, case, twin=None, vlc=True, ffplay=True):
    out = dict(file=os.path.basename(path), ffprobe=ffprobe(path), ffmpeg_decode=ffmpeg_decode(path),
               pyav=pyav_check(path, case), opencv=opencv_check(path, twin))
    if vlc:
        out["vlc_play"] = vlc_run(path, case)
        out["vlc_seek_7s"] = vlc_run(path, case, start_time=7)
    if ffplay:
        out["ffplay"] = ffplay_run(path)
    return out
