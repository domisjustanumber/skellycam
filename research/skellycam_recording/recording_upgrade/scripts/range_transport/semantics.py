"""T-S5 part 1: HTTP Range semantics of skellycam's playback route (as is) and of the minimal fix.
Usage: python -I semantics.py <media_dir> <out.json>   (servers from server.py on 127.0.0.1:53190 real, :53191 bare)
Raw http.client, so nothing is hidden by a browser. Every body is checked against the file on disk.
"""
import hashlib, http.client, json, os, sys, time, urllib.parse

media, out_path = sys.argv[1], sys.argv[2]
REAL, BARE = 53190, 53191
REC_PARENT = os.path.join(media, "rec")
Q = "?recording_parent_directory=" + urllib.parse.quote(REC_PARENT)
KEEP = ("content-range", "content-length", "accept-ranges", "content-type", "etag", "last-modified",
        "access-control-allow-origin", "access-control-expose-headers", "access-control-allow-credentials",
        "access-control-allow-headers", "access-control-allow-methods", "cache-control", "vary")


def req(port, method, path, headers=None, read_cap=8 << 20):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=600)
    t = time.perf_counter()
    c.request(method, path, headers=headers or {})
    r = c.getresponse()
    body = r.read(read_cap) if method != "HEAD" else b""
    ms = (time.perf_counter() - t) * 1000
    h = {k.lower(): v for k, v in r.getheaders()}
    c.close()
    return r.status, h, body, ms


def file_bytes(path, start, end_incl):
    with open(path, "rb") as f:
        f.seek(start)
        return f.read(end_incl - start + 1)


def case(port, path, local, rng=None, method="GET", extra=None, expect=None):
    hd = dict(extra or {})
    if rng is not None:
        hd["Range"] = rng
    st, h, body, ms = req(port, method, path, hd)
    rec = {"method": method, "range": rng, "status": st, "ms": round(ms, 1), "body_len": len(body),
           "headers": {k: h[k] for k in KEEP if k in h}}
    if extra:
        rec["req_headers"] = extra
    if expect is not None and local and os.path.exists(local):
        s, e = expect
        rec["bytes_match_file"] = body == file_bytes(local, s, e)
    if st == 206 and h.get("content-type", "").startswith("multipart/byteranges"):
        rec["multipart_parts"] = body.count(b"Content-Range:")
    return rec


def suite(port, path, local, size, label):
    out = {"label": label, "path": path, "file_size_on_disk": size, "cases": []}
    add = lambda **k: out["cases"].append(case(port, path, local, **k))
    add(rng="bytes=0-15", expect=(0, 15))
    add(rng=f"bytes={size // 2}-{size // 2 + 153599}", expect=(size // 2, size // 2 + 153599))
    add(rng="bytes=-16", expect=(size - 16, size - 1))
    add(rng=f"bytes={size - 100}-", expect=(size - 100, size - 1))
    add(rng=f"bytes=0-{size + 1000}")                  # end past EOF: clamp, read capped at 8 MiB here
    add(method="HEAD")
    add(method="HEAD", rng="bytes=0-15")
    add(rng="bytes=0-15,32-47")
    add(rng=f"bytes={size}-")
    add(rng=f"bytes={size + 10}-{size + 20}")
    add(rng="bytes=-0")
    add(rng="bytes=10-5")
    add(rng="items=0-15")
    add(rng="bytes=0-15", extra={"Origin": "null"}, expect=(0, 15))
    add(rng="bytes=-16", extra={"Origin": "http://localhost:5173"}, expect=(size - 16, size - 1))
    # CORS preflight a renderer sends for a non-safelisted Range (e.g. a suffix range)
    st, h, _, ms = req(port, "OPTIONS", path, {"Origin": "null", "Access-Control-Request-Method": "GET",
                                               "Access-Control-Request-Headers": "range"})
    out["cases"].append({"method": "OPTIONS (preflight, Origin null, range)", "status": st,
                         "headers": {k: h[k] for k in KEEP if k in h}})
    return out


def main():
    m = json.load(open(os.path.join(media, "media.json")))
    res = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "suites": []}
    cam0, h264, pat, big = m["cam0"], m["h264"], m["pattern"], m["big"]
    web = os.path.join(REC_PARENT, "rangetest", "cam0.web.mp4")
    if os.path.exists(web):
        os.remove(web)
    # 1. route as it is today, MJPEG MKV: first request triggers the libx264 transcode
    p = "/skellycam/playback/rangetest/videos/cam0" + Q
    st, h, body, ms = req(REAL, "GET", p, {"Range": "bytes=0-15"})
    first = {"status": st, "ms_first_request": round(ms), "content_range": h.get("content-range"),
             "first16_hex": body[:16].hex(), "cam0_first16_hex": file_bytes(cam0["path"], 0, 15).hex(),
             "web_mp4_created": os.path.exists(web), "web_mp4_size": os.path.getsize(web) if os.path.exists(web) else None,
             "cam0_mkv_size": cam0["size"]}
    st, h, body, ms = req(REAL, "GET", p, {"Range": "bytes=0-15"})
    first["ms_second_request"] = round(ms, 1)
    first["second_matches_mkv"] = body == file_bytes(cam0["path"], 0, 15)
    first["second_matches_web_mp4"] = os.path.exists(web) and body == file_bytes(web, 0, 15)
    res["route_asis_mjpeg_mkv"] = first
    # 2. route as it is today, H.264 MP4 (served as is): Range semantics of the route
    res["suites"].append(suite(REAL, "/skellycam/playback/rangetest/videos/h264" + Q, h264["path"], h264["size"],
                               "route_asis_h264_mp4"))
    # 3. the .mka audio file and its listing
    st, h, body, _ = req(REAL, "GET", "/skellycam/playback/rangetest/videos" + Q)
    res["route_asis_listing"] = {"status": st, "body": json.loads(body)}
    res["route_asis_mka"] = {"note": ".mka is not in VIDEO_EXTENSIONS; requesting the stem",
                             "status": req(REAL, "GET", "/skellycam/playback/rangetest/videos/f1_1ch_skau" + Q)[0]}
    # 4. the fix (FileResponse on the original file), behind skellycam's middleware, then bare
    for port, lab in ((REAL, "fixed_in_real_app"), (BARE, "fixed_bare")):
        res["suites"].append(suite(port, "/fixed/pattern.bin", pat["path"], pat["size"], lab + "_pattern"))
    s = suite(BARE, "/fixed/big.mkv", big["path"], big["size"], "fixed_bare_big_4p7GB")
    for chk in big["range_sha256"]:
        st, h, body, ms = req(BARE, "GET", "/fixed/big.mkv", {"Range": f"bytes={chk['off']}-{chk['off'] + chk['len'] - 1}"})
        s["cases"].append({"range": f"bytes={chk['off']}-{chk['off'] + chk['len'] - 1}", "status": st,
                           "content_range": h.get("content-range"), "sha_ok": hashlib.sha256(body).hexdigest() == chk["sha256"],
                           "ms": round(ms, 1)})
    res["suites"].append(s)
    json.dump(res, open(out_path, "w"), indent=1)
    print(json.dumps(res, indent=1)[:200000])


if __name__ == "__main__":
    main()
