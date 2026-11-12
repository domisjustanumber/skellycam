"""FLAC packet offsets, crash index, and .skau embedding. PyAV 19.0.2 (run with the skellycam-phase1 venv).
Usage: python -I flac_skau.py <outdir>

F1  Native FLAC (frame_size=1024, flush_packets=1), written block by block like the recorder:
    is packet i at header_len + sum(sizes[:i])? Does the file end exactly at packet i after mux(i)?
    Is the header length the same live and after close? Mono and stereo.
F2  Live packet index under hard kills: the child appends (offset, size, crc) to an index file after each mux,
    then os._exit(1) at several points, some between the mux and the index write. Check every index record
    against the killed file's bytes, and count frames on disk that the index lacks.
F3  Finalise: stream-copy .flac -> .mka (PyAV), scan the MKA, check every FLAC frame is byte-identical,
    append a .skau-sized attachment (timing records + packet table) with sidecar_embedding/append_attachment.py,
    check blocks unchanged, decoded PCM identical to the source, attachment identical, SeekHead room.
    Also a 1-hour-sized .skau payload on a copy.
Writes electron_cfg.json for electron/main.cjs (decode by offsets in E35/E45, locator, <audio>).
"""
import fractions, hashlib, json, multiprocessing as mp, os, shutil, struct, subprocess, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "sidecar_embedding"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "audio_skellysync"))
import append_attachment as aa  # noqa: E402
from common import scan_mkv  # noqa: E402  (audio_skellysync element-header scanner)
import av  # noqa: E402
import numpy as np  # noqa: E402

RATE, BLOCK = 48000, 1024


def signal(seconds, channels, seed=3):
    rng = np.random.default_rng(seed)
    n = seconds * RATE
    x = rng.normal(0, 0.003, (n, channels))
    t = 0
    while t < n - 2000:                     # irregular clicks, distinct per channel
        for c in range(channels):
            x[t + 7 * c:t + 7 * c + 200, c] += 0.5 * np.sin(np.arange(200) * (0.3 + 0.1 * c))
        t += int(rng.integers(9000, 24000))
    return np.clip(x * 32767, -32768, 32767).astype(np.int16)


def flac_header_len(b):
    assert b[:4] == b"fLaC"
    p, blocks = 4, []
    while True:
        h = b[p]; ln = int.from_bytes(b[p + 1:p + 4], "big")
        blocks.append((h & 0x7F, ln)); p += 4 + ln
        if h & 0x80:
            return p, blocks


def write_flac(path, pcm, kill_at=None, idx_path=None, idx_before_write=False):
    ch = pcm.shape[1]
    out = av.open(path, "w", format="flac", options={"flush_packets": "1"})
    st = out.add_stream("flac", rate=RATE, layout="mono" if ch == 1 else "stereo")
    st.codec_context.options = {"frame_size": str(BLOCK)}
    st.time_base = fractions.Fraction(1, RATE)
    idx = open(idx_path, "wb") if idx_path else None
    pk, sizes_after, header_live, n_in, offset = [], [], None, 0, None
    for b0 in range(0, len(pcm), BLOCK):
        blk = pcm[b0:b0 + BLOCK]
        fr = av.AudioFrame.from_ndarray(blk.reshape(1, -1), format="s16", layout="mono" if ch == 1 else "stereo")
        fr.sample_rate = RATE; fr.pts = n_in; n_in += len(blk)
        for p in st.encode(fr):
            data = bytes(p)
            out.mux(p)
            if header_live is None:
                header_live = flac_header_len(open(path, "rb").read(65536))[0]
                offset = header_live
            sizes_after.append(os.stat(path).st_size)
            pk.append((offset, len(data), zlib.crc32(data), data))
            if idx:
                if kill_at is not None and len(pk) == kill_at and idx_before_write:
                    os._exit(1)            # mux done, index record not yet written
                idx.write(struct.pack("<QII", offset, len(data), zlib.crc32(data))); idx.flush()
            offset += len(data)
            if kill_at is not None and len(pk) == kill_at:
                os._exit(1)
    for p in st.encode(None):
        data = bytes(p); out.mux(p)
        sizes_after.append(os.stat(path).st_size)
        pk.append((offset, len(data), zlib.crc32(data), data)); offset += len(data)
    out.close()
    return pk, sizes_after, header_live


def decode_pcm(path):
    with av.open(path) as c:
        s = c.streams.audio[0]
        return np.concatenate([f.to_ndarray().reshape(-1, s.channels) if f.format.is_packed else f.to_ndarray().T
                               for f in c.decode(s)])


def f1(outdir, ch):
    pcm = signal(30, ch)
    path = os.path.join(outdir, f"f1_{ch}ch.flac")
    if os.path.exists(path): os.remove(path)
    pk, sizes_after, header_live = write_flac(path, pcm)
    blob = open(path, "rb").read()
    header_final, blocks = flac_header_len(blob)
    verbatim = sum(1 for o, s, c, d in pk if blob[o:o + s] == d)
    ends_at_this = sum(1 for (o, s, c, d), sz in zip(pk, sizes_after) if sz == o + s)
    dec = decode_pcm(path)
    return dict(channels=ch, packets=len(pk), header_len_live=header_live, header_len_final=header_final,
                metadata_blocks=[dict(type=t, len=l) for t, l in blocks],
                packet_at_predicted_offset=f"{verbatim}/{len(pk)}",
                file_ends_at_packet_just_muxed=f"{ends_at_this}/{len(pk)}",
                last_packet_ends_at_eof=pk[-1][0] + pk[-1][1] == len(blob),
                decoded_equals_source=bool(dec.shape == pcm.shape and np.array_equal(dec, pcm))), pcm, pk, path


def _child(path, pcm, kill_at, idx_path, before):
    write_flac(path, pcm, kill_at=kill_at, idx_path=idx_path, idx_before_write=before)


def f2(outdir):
    pcm = signal(20, 1, seed=5)
    rows = []
    for kill_at, before in ((40, False), (137, False), (300, False), (41, True), (138, True), (301, True)):
        path = os.path.join(outdir, f"f2_kill{kill_at}.flac"); idx = path + ".idx"
        for q in (path, idx):
            if os.path.exists(q): os.remove(q)
        pr = mp.Process(target=_child, args=(path, pcm, kill_at, idx, before)); pr.start(); pr.join()
        blob = open(path, "rb").read(); ib = open(idx, "rb").read()
        recs = [struct.unpack_from("<QII", ib, i) for i in range(0, len(ib) - len(ib) % 16, 16)]
        ok = sum(1 for o, s, c in recs if zlib.crc32(blob[o:o + s]) == c)
        on_disk = sum(1 for p in av.open(path).demux() if p.size)
        tail = len(blob) - (recs[-1][0] + recs[-1][1]) if recs else None
        rows.append(dict(kill_after_packet=kill_at, killed_between_mux_and_index=before, exit=pr.exitcode,
                         index_records=len(recs), index_records_crc_ok=ok, packets_on_disk=on_disk,
                         frames_on_disk_not_indexed=on_disk - len(recs), bytes_after_last_indexed=tail))
    return rows


def remux_mka(src, dst):
    with av.open(src) as inp:
        out = av.open(dst, "w", format="matroska")
        ost = out.add_stream_from_template(inp.streams.audio[0])
        for p in inp.demux(inp.streams.audio[0]):
            if p.size:
                p.stream = ost; out.mux(p)
        out.close()


def seekhead_slack(path):
    b = open(path, "rb").read(65536)
    eid, d, size, _ = aa.read_elem(b, 0)
    eid, seg_data, _, _ = aa.read_elem(b, d + size)
    eid, sh_data, sh_size, _ = aa.read_elem(b, seg_data)
    end = sh_data + sh_size
    e2, vd, vsz, _ = aa.read_elem(b, end)
    return (vd + vsz - end) if e2 == aa.ID_VOID else 0


def skau_payload(n_blocks, packets):
    hdr = b"SKAU" + struct.pack("<HHII", 1, 64, 48, 0) + os.urandom(64 - 16)
    recs = os.urandom(48 * n_blocks)
    table = b"".join(struct.pack("<QIIqII", o, s, BLOCK, i * BLOCK, c, 0) for i, (o, s, c) in enumerate(packets))
    return hdr + recs + table


def f3(outdir, ch, pcm, pk, flac_path):
    mka = flac_path.replace(".flac", ".mka")
    if os.path.exists(mka): os.remove(mka)
    remux_mka(flac_path, mka)
    sc = scan_mkv(mka)
    blocks = [b for b in sc["blocks"] if b[0] == 1]
    blob = open(mka, "rb").read()
    same = sum(1 for (tn, off, size, ts, kf, laced), (o, s, c, d) in zip(blocks, pk) if blob[off:off + size] == d)
    table = [(off, size, zlib.crc32(blob[off:off + size])) for tn, off, size, ts, kf, laced in blocks]
    payload = skau_payload(len(pk), table)
    slack_before = seekhead_slack(mka)
    app = mka.replace(".mka", "_skau.mka"); shutil.copyfile(mka, app)
    r = aa.append(app, payload, name="skellycam_audio.skau", mime="application/x-skellycam-audio-timing")
    sc2 = scan_mkv(app)
    blocks2 = [b for b in sc2["blocks"] if b[0] == 1]
    dump = app + ".dump"
    if os.path.exists(dump): os.remove(dump)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-dump_attachment:t:0", dump, "-i", app], capture_output=True)
    dec_mka = decode_pcm(mka); dec_app = decode_pcm(app)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", app],
                         capture_output=True, text=True).stdout.strip()
    ff = subprocess.run(["ffmpeg", "-v", "error", "-i", app, "-f", "s16le", "-"], capture_output=True)
    ff_pcm = np.frombuffer(ff.stdout, np.int16).reshape(-1, ch)
    # 1-hour-sized payload on another copy
    n1h = RATE * 3600 // BLOCK
    big = os.urandom(64 + 48 * n1h + 32 * n1h)
    app1h = mka.replace(".mka", "_skau1h.mka"); shutil.copyfile(mka, app1h)
    r1h = aa.append(app1h, big, name="skellycam_audio.skau", mime="application/x-skellycam-audio-timing")
    dec_1h = decode_pcm(app1h)
    return dict(channels=ch, mka_tracks={k: dict(codec_id=v["codec_id"], codec_private_len=len(v.get("codec_private", "")) // 2)
                                          for k, v in sc["tracks"].items()},
                mka_blocks=len(blocks), laced=sum(1 for b in blocks if b[5]),
                flac_frames_byte_identical_in_mka=f"{same}/{len(pk)}",
                seekhead_spare_before=slack_before, append=dict(void_pad=r["void_pad"], payload_len=len(payload)),
                blocks_unchanged_after_append=blocks == blocks2, segment_uid_same=sc["segment_uid"] == sc2["segment_uid"],
                attachment_identical=os.path.exists(dump) and open(dump, "rb").read() == payload,
                decoded_mka_equals_source=bool(np.array_equal(dec_mka, pcm)),
                decoded_after_append_equals_source=bool(np.array_equal(dec_app, pcm)),
                ffmpeg_cli_pcm_equals_source=bool(ff_pcm.shape == pcm.shape and np.array_equal(ff_pcm, pcm)),
                ffprobe_duration_s=dur,
                one_hour_payload=dict(bytes=len(big), void_pad=r1h["void_pad"],
                                      decoded_equals_source=bool(np.array_equal(dec_1h, pcm)))), mka, app, table, payload, sc


def main():
    outdir = sys.argv[1]; os.makedirs(outdir, exist_ok=True)
    res = dict(av=av.__version__, libavformat=list(av.library_versions["libavformat"]), F1=[], F2=None, F3=[])
    cfg = dict(tests=[])
    for ch in (1, 2):
        r1, pcm, pk, flac_path = f1(outdir, ch); res["F1"].append(r1)
        r3, mka, app, table, payload, sc = f3(outdir, ch, pcm, pk, flac_path); res["F3"].append(r3)
        ref = os.path.join(outdir, f"ref_{ch}ch.f32"); (pcm.astype(np.float32) / 32768.0).tofile(ref)
        fb = open(flac_path, "rb").read()
        desc = b"fLaC" + bytes([0x80]) + fb[5:8] + fb[8:8 + 34]           # STREAMINFO only, marked last
        url = lambda p: "file:///" + os.path.abspath(p).replace("\\", "/")
        cfg["tests"].append(dict(name=f"native_flac_{ch}ch", url=url(flac_path), ref=url(ref), channels=ch, rate=RATE,
                                 description=desc.hex(), packets=[[o, s] for o, s, c, d in pk]))
        cfg["tests"].append(dict(name=f"mka_skau_{ch}ch", url=url(app), ref=url(ref), channels=ch, rate=RATE,
                                 description=sc["tracks"][1]["codec_private"], packets=[[o, s] for o, s, c in table],
                                 skau_sha256=hashlib.sha256(payload).hexdigest()))
    res["F2"] = f2(outdir)
    json.dump(cfg, open(os.path.join(outdir, "electron_cfg.json"), "w"))
    json.dump(res, open(os.path.join(outdir, "flac_skau.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
