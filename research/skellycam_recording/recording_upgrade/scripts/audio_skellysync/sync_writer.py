"""Prototype of the proposed skellysync Design A output pass: one PyAV pass per camera that writes
JPEG frames + the trimmed audio interleaved in one MKV, then rebuilds every offset by scanning the final file.

Rules it demonstrates:
  * the audio window is the video window: it starts at the source time of output frame 0
    (video stream start_time + start_frame / source_fps) and lasts frame_count / out_fps, in samples;
  * stream start times are honoured (audio and video may start at different times in a camera file);
  * video packets get a fixed 1/out_fps time base (sidecar FINDINGS section 1 pitfall);
    audio packets keep the encoder's 1/sample_rate time base, which the muxer rescales;
  * the output has exactly one video and one audio stream, chosen by the writer, so there is
    no default-stream selection to get wrong (the -map bug class cannot happen);
  * R1 (out_fps < source fps): video slots take the source frame at or before the slot time (PREV);
    audio is untouched by the frame-rate policy, it only depends on the time window;
  * after close(): scan the final bytes (all tracks), check every JPEG CRC, read the Segment UID,
    write an index JSON (prototype sidecar with a video table and an audio packet table), optionally embed it.

Usage (module): write_synced(src, dst, start_frame, frame_count, out_fps, acodec, ...)
"""
import fractions, json, math, os, sys, time

import av
import cv2
import numpy as np
from scipy import signal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common as C  # noqa: E402

SE = os.path.join(os.path.dirname(HERE), "sidecar_embedding")


def _decode_audio(c, astream):
    """Decode a whole audio stream to float32 (ch, n). Returns (array, first_sample_time_s Fraction, rate, gaps)."""
    chunks, t0, nxt, gaps = [], None, None, 0
    for fr in c.decode(astream):
        a = fr.to_ndarray()
        if fr.format.is_packed:
            a = a.reshape(-1, fr.layout.nb_channels).T
        a = a.astype(np.float32)
        if fr.format.name.startswith("s16"):
            a /= 32768.0
        elif fr.format.name.startswith("s32"):
            a /= 2147483648.0
        pts = fr.pts
        if t0 is None:
            t0 = fractions.Fraction(pts) * fr.time_base
            nxt = pts
        elif pts != nxt:
            gaps += 1
        nxt = pts + int(fractions.Fraction(fr.samples) / fr.sample_rate / fr.time_base)
        chunks.append(a)
    return np.concatenate(chunks, axis=1), t0, astream.rate, gaps


def _resample(a, sr_in, sr_out, method):
    if sr_in == sr_out:
        return a
    if method == "poly":
        g = math.gcd(sr_in, sr_out)
        return signal.resample_poly(a, sr_out // g, sr_in // g, axis=1).astype(np.float32)
    # swr through PyAV, streaming, as a production writer would do it
    layout = "stereo" if a.shape[0] == 2 else "mono"
    rs = av.AudioResampler(format="fltp", layout=layout, rate=sr_out)
    out = []
    step = 1024
    for i in range(0, a.shape[1], step):
        fr = av.AudioFrame.from_ndarray(np.ascontiguousarray(a[:, i:i + step]), format="fltp", layout=layout)
        fr.sample_rate = sr_in; fr.pts = i; fr.time_base = fractions.Fraction(1, sr_in)
        out += [o.to_ndarray() for o in rs.resample(fr)]
    out += [o.to_ndarray() for o in rs.resample(None)]
    return np.concatenate(out, axis=1).astype(np.float32)


def write_synced(src, dst, start_frame, frame_count, out_fps=None, acodec="opus", channels="source",
                 out_rate=None, bitrate=None, flac_s32=False, resampler="poly", embed=False, jpeg_q=90,
                 opus_application=None, opus_end_align=False):
    """opus_end_align: drop the last pre-skip (312) samples so the Opus track ends where the video ends.
    FFmpeg counts the pre-skip in the track duration, and OpenCV derives CAP_PROP_FRAME_COUNT from the container
    duration; without this, counts at >= ~63 fps come out one high (duration_test.py). Recommended for production."""
    t_start = time.perf_counter()
    c = av.open(src)
    vs, ast = c.streams.video[0], (c.streams.audio[0] if c.streams.audio else None)
    src_fps = fractions.Fraction(vs.average_rate)
    out_fps = fractions.Fraction(out_fps) if out_fps else src_fps
    v0 = fractions.Fraction(vs.start_time or 0) * vs.time_base
    t0 = v0 + fractions.Fraction(start_frame) / src_fps  # source time of output frame 0

    meta = dict(src=os.path.basename(src), start_frame=start_frame, frame_count=frame_count,
                src_fps=str(src_fps), out_fps=str(out_fps), acodec=acodec)
    # ---- audio: decode, choose channels, resample, cut the sample-exact window ----
    audio = None
    if acodec != "none" and ast is not None:
        a, a0, sr_in, gaps = _decode_audio(c, ast)
        c.seek(0)
        if channels == "mono":
            a = a.mean(axis=0, keepdims=True)
        sr = out_rate or (48000 if acodec == "opus" else sr_in)
        if acodec == "opus" and sr not in (48000, 24000, 16000, 12000, 8000):
            raise ValueError("Opus needs 48/24/16/12/8 kHz")
        a = _resample(a, sr_in, sr, resampler)
        s0 = (t0 - a0) * sr  # exact Fraction
        n_total = fractions.Fraction(frame_count) * sr / out_fps
        s0i, ni = round(s0), round(n_total)
        if acodec == "opus" and opus_end_align:
            ni -= 312  # libopus pre-skip at 48 kHz (checked against initial_padding after encoding)
        win = np.zeros((a.shape[0], ni), np.float32)
        lo, hi = max(0, s0i), min(a.shape[1], s0i + ni)
        if hi > lo:
            win[:, lo - s0i:hi - s0i] = a[:, lo:hi]
        meta.update(audio_src_rate=sr_in, audio_out_rate=sr, audio_channels=a.shape[0], audio_decode_gaps=gaps,
                    audio_window_first_src_sample=s0i, audio_window_rounding_samples=float(s0 - s0i),
                    audio_samples=ni, audio_pad_front=max(0, -s0i), audio_pad_back=max(0, s0i + ni - a.shape[1]),
                    audio_src_first_time_s=float(a0), video_src_start_time_s=float(v0))
        audio = (win, sr)

    # ---- output container ----
    if os.path.exists(dst):
        os.remove(dst)
    out = av.open(dst, "w", format="matroska")
    vso = out.add_stream("mjpeg", rate=out_fps)
    vso.width, vso.height = vs.codec_context.width, vs.codec_context.height
    vso.codec_context.pix_fmt = "yuvj420p"
    TB = fractions.Fraction(1) / out_fps
    vso.time_base = TB
    aso = None
    if audio is not None:
        win, sr = audio
        layout = "stereo" if win.shape[0] == 2 else "mono"
        if acodec == "opus":
            aso = out.add_stream("libopus", rate=sr)
            aso.bit_rate = bitrate or (64000 if layout == "mono" else 128000)
            if opus_application:
                aso.codec_context.options = {"application": opus_application}
        elif acodec == "flac":
            aso = out.add_stream("flac", rate=sr)
            aso.format = "s32" if flac_s32 else "s16"
            if flac_s32:
                aso.codec_context.bits_per_raw_sample = 24
        elif acodec == "vorbis":
            aso = out.add_stream("vorbis", rate=sr)
            aso.codec_context.options = {"strict": "experimental"}
            aso.bit_rate = bitrate or 128000
        elif acodec == "pcm_s24le":
            aso = out.add_stream("pcm_s24le", rate=sr)
        aso.layout = layout

    # ---- one pass: decode video, pick frames, JPEG, interleave audio ----
    jpeg_crcs, apkt_crcs = [], []
    a_pos = 0
    want = {}  # output slot -> source frame index (PREV policy)
    for k in range(frame_count):
        want[k] = start_frame + math.floor(fractions.Fraction(k) * src_fps / out_fps)
    by_src = {}
    for k, s in want.items():
        by_src.setdefault(s, []).append(k)
    k_next = 0
    for fr in c.decode(vs):
        idx = round((fractions.Fraction(fr.pts) * fr.time_base - v0) * src_fps)
        if idx not in by_src:
            if idx > want[frame_count - 1]:
                break
            continue
        bgr = fr.to_ndarray(format="bgr24")
        ok, jpg = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, jpeg_q])
        jb = jpg.tobytes()
        for k in by_src[idx]:
            assert k == k_next, (k, k_next)
            if aso is not None:
                end = round(fractions.Fraction(k + 1) * audio[1] / out_fps)
                chunk = audio[0][:, a_pos:end]
                af = av.AudioFrame.from_ndarray(np.ascontiguousarray(chunk), format="fltp", layout=aso.layout.name)
                af.sample_rate = audio[1]; af.pts = a_pos; af.time_base = fractions.Fraction(1, audio[1])
                for p in aso.encode(af):
                    apkt_crcs.append(C.crc32(bytes(p))); out.mux(p)
                a_pos = end
            p = av.Packet(jb); p.stream = vso; p.time_base = TB; p.pts = p.dts = k; p.is_keyframe = True
            out.mux(p)
            jpeg_crcs.append(C.crc32(jb))
            k_next += 1
    if aso is not None:
        for p in aso.encode(None):
            apkt_crcs.append(C.crc32(bytes(p))); out.mux(p)
        meta["encoder_initial_padding"] = aso.codec_context.initial_padding
    out.close(); c.close()
    meta["write_s"] = round(time.perf_counter() - t_start, 3)

    # ---- rebuild offsets from the final bytes ----
    t = time.perf_counter()
    scan = C.scan_mkv(dst)
    meta["scan_ms"] = round((time.perf_counter() - t) * 1000, 2)
    vnum = next(n for n, tr in scan["tracks"].items() if tr["codec_id"] == "V_MJPEG")
    anum = next((n for n, tr in scan["tracks"].items() if tr["codec_id"].startswith("A_")), None)
    ts_scale = scan["timestamp_scale"]
    blob = open(dst, "rb").read()
    vb = [b for b in scan["blocks"] if b[0] == vnum]
    ab = [b for b in scan["blocks"] if b[0] == anum]
    meta["video_blocks"] = len(vb)
    meta["video_crc_match"] = sum(1 for b, cr in zip(vb, jpeg_crcs) if C.crc32(blob[b[1]:b[1] + b[2]]) == cr)
    meta["audio_blocks"] = len(ab)
    meta["audio_crc_match"] = sum(1 for b, cr in zip(ab, apkt_crcs) if C.crc32(blob[b[1]:b[1] + b[2]]) == cr)
    meta["audio_laced_blocks"] = sum(1 for b in ab if b[5])
    meta["segment_uid"] = scan["segment_uid"]
    meta["bytes"] = len(blob)
    meta["video_bytes"] = sum(b[2] for b in vb)
    meta["audio_bytes"] = sum(b[2] for b in ab)
    index = dict(segment_uid=scan["segment_uid"], timestamp_scale_ns=ts_scale,
                 video=dict(track=vnum, rate=str(out_fps),
                            records=[[b[1], b[2], C.crc32(blob[b[1]:b[1] + b[2]]), b[3]] for b in vb]))
    if anum is not None:
        tr = scan["tracks"][anum]
        index["audio"] = dict(track=anum, codec_id=tr["codec_id"], codec_private=tr.get("codec_private", ""),
                              codec_delay_ns=tr.get("codec_delay_ns", 0), seek_preroll_ns=tr.get("seek_preroll_ns", 0),
                              sample_rate=audio[1], channels=audio[0].shape[0],
                              packets=[[b[1], b[2], b[3] * ts_scale] for b in ab])
        meta["audio_track"] = {k: v for k, v in tr.items() if k != "codec_private"}
        meta["audio_codec_private_len"] = len(tr.get("codec_private", "")) // 2
        meta["audio_first_block_ts_ns"] = ab[0][3] * ts_scale if ab else None
        meta["video_first_block_ts_ns"] = vb[0][3] * ts_scale if vb else None
    idx_path = os.path.splitext(dst)[0] + ".index.json"
    json.dump(index, open(idx_path, "w"))
    if embed:
        sys.path.insert(0, SE)
        import append_attachment as aa
        payload = json.dumps(index).encode()
        t = time.perf_counter(); aa.append(dst, payload, name="skellysync_index.json", mime="application/json")
        meta["embed_ms"] = round((time.perf_counter() - t) * 1000, 2)
        scan2 = C.scan_mkv(dst)
        meta["after_embed_blocks_unchanged"] = sum(1 for x, y in zip(scan["blocks"], scan2["blocks"]) if x == y)
        meta["after_embed_uid_same"] = scan2["segment_uid"] == scan["segment_uid"]
    return meta


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--start", type=int, default=0); ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--fps"); ap.add_argument("--acodec", default="opus")
    ap.add_argument("--channels", default="source"); ap.add_argument("--embed", action="store_true")
    a = ap.parse_args()
    print(json.dumps(write_synced(a.src, a.dst, a.start, a.count, a.fps, a.acodec, a.channels, embed=a.embed), indent=1))
