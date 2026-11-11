"""JPEG checks for native-MJPEG frames (stdlib; optional strict/lenient decoders).

    from common import jpegcheck
    r = jpegcheck.check_jpeg(frame_bytes)
    r -> {soi, eoi, sof0_w, sof0_h, sof_type, header_sha1, header_bytes, bytes_before_soi, trailing_after_eoi,
          marker_ok, marker_issues, lenient_ok, lenient_method, strict_ok, strict_method, strict_error,
          extra_bytes_before_eoi}

Field meanings:
- ``soi``: the buffer starts with FFD8 (``bytes_before_soi`` counts junk before the first FFD8 if it does not).
- ``eoi``: an FFD9 end marker terminates the entropy-coded data (``trailing_after_eoi`` = bytes after it; some
  cameras pad the payload).
- ``sof0_w`` / ``sof0_h``: frame size from the first SOF0/SOF1/SOF2 segment (``sof_type`` says which).
- ``header_sha1``: full SHA-1 hex of the bytes from SOI to the end of the SOS segment inclusive (quantisation and
  Huffman tables, SOF, SOS; no image data). Equal across APIs for one camera+mode => the bytes came from the same
  encoder (camera), not a host re-encode. (mjpeg/mjpeg_common.py ``jpeg_header`` hashes the same span; it keeps
  only the first 12 hex digits, ``header_sha1[:12]`` matches it.)
- ``marker_ok``: marker walk of bitstream/verify/strict_jpeg_check.py (SOF present, SOS present, RSTn order and
  count, no stray markers inside the scan, EOI present).
- ``lenient_ok``: marker walk passes AND a lenient decode succeeds when a decoder is importable (simplejpeg with
  strict=False, else Pillow). With no decoder installed it is the marker walk alone (``lenient_method`` says so).
- ``strict_ok``: libjpeg-turbo strict decode (any libjpeg warning fails), via simplejpeg (bundles libjpeg-turbo)
  or PyTurboJPEG (needs a system libturbojpeg) if importable, else None.
- ``extra_bytes_before_eoi``: the N in libjpeg's warning "Corrupt JPEG data: N extraneous bytes before marker
  0xd9" (the generic 4C4A:4A55 camera's 1080p frames carry 387-1195 such bytes; REPORT finding 6). 0 when the
  strict decode passed, None when no strict decoder is available or a different error occurred.

Logic reused from mjpeg/mjpeg_common.py (``jpeg_header``, ``validate_jpeg``) and
bandwidth/verify/strict_jpeg_check.py (``marker_walk``, strict decode); both were validated on Gerald's frames.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Any

_EXTRANEOUS_RE = re.compile(r"(\d+)\s+extraneous bytes before marker 0x([0-9a-fA-F]{2})")


def parse_sof0(b: bytes) -> dict[str, Any] | None:
    """Walk marker segments from SOI up to SOS and return the first SOF0/1/2 as
    {"type": "SOF0", "w", "h", "precision", "components": [{"id","h","v","tq"}], "offset"}; None if absent."""
    i = b.find(b"\xff\xd8")
    if i < 0:
        return None
    pos = i + 2
    n = len(b)
    while pos + 4 <= n:
        if b[pos] != 0xFF:
            return None
        m = b[pos + 1]
        if m == 0xFF:  # fill byte
            pos += 1
            continue
        if m in (0x01,) or 0xD0 <= m <= 0xD7:  # standalone markers
            pos += 2
            continue
        ln = (b[pos + 2] << 8) | b[pos + 3]
        if m in (0xC0, 0xC1, 0xC2):
            seg = b[pos + 4:pos + 2 + ln]
            if len(seg) < 6:
                return None
            nc = seg[5]
            comps = []
            for k in range(nc):
                j = 6 + 3 * k
                if j + 2 < len(seg):
                    comps.append({"id": seg[j], "h": seg[j + 1] >> 4, "v": seg[j + 1] & 15, "tq": seg[j + 2]})
            return {"type": {0xC0: "SOF0", 0xC1: "SOF1", 0xC2: "SOF2"}[m], "precision": seg[0],
                    "h": (seg[1] << 8) | seg[2], "w": (seg[3] << 8) | seg[4], "components": comps, "offset": pos}
        if m == 0xDA:  # SOS reached without a SOF
            return None
        pos += 2 + ln
    return None


def header_span(b: bytes) -> tuple[int, int] | None:
    """(start, end) of SOI..end of SOS segment inclusive, or None if no SOS is found."""
    i = b.find(b"\xff\xd8")
    if i < 0:
        return None
    pos = i + 2
    n = len(b)
    while pos + 4 <= n:
        if b[pos] != 0xFF:
            return None
        m = b[pos + 1]
        if m == 0xFF:
            pos += 1
            continue
        if 0xD0 <= m <= 0xD7 or m == 0x01:
            pos += 2
            continue
        ln = (b[pos + 2] << 8) | b[pos + 3]
        if m == 0xDA:
            end = pos + 2 + ln
            return (i, end) if end <= n else None
        pos += 2 + ln
    return None


def marker_walk(b: bytes) -> dict[str, Any]:
    """Structural walk (from strict_jpeg_check.py): SOF dims, DRI, RSTn order/count in the scan, stray markers,
    EOI position and trailing bytes. ``ok`` is True when the structure is complete and consistent."""
    start = b.find(b"\xff\xd8")
    r: dict[str, Any] = {"soi_at": start if start >= 0 else None, "w": None, "h": None, "dri": 0, "rst": 0,
                         "rst_order_ok": True, "other_markers_in_scan": 0, "eoi_at": None,
                         "trailing_after_eoi": None, "mcus": None, "expected_rst": None, "has_sos": False,
                         "issues": [], "ok": False}
    if start < 0:
        r["issues"].append("no SOI")
        return r
    i, n = start + 2, len(b)
    samp: list[tuple[int, int]] = []
    while i + 4 <= n:
        if b[i] != 0xFF:
            r["issues"].append(f"no marker at offset {i}")
            break
        m = b[i + 1]
        if m == 0xFF:
            i += 1
            continue
        if 0xD0 <= m <= 0xD7 or m == 0x01:
            i += 2
            continue
        if m == 0xD9:
            r["issues"].append("EOI before SOS")
            r["eoi_at"] = i
            break
        L = (b[i + 2] << 8) | b[i + 3]
        if m in (0xC0, 0xC1, 0xC2) and i + 9 < n:
            r["h"] = (b[i + 5] << 8) | b[i + 6]
            r["w"] = (b[i + 7] << 8) | b[i + 8]
            nc = b[i + 9]
            samp = [(b[i + 11 + 3 * k] >> 4, b[i + 11 + 3 * k] & 15) for k in range(nc) if i + 11 + 3 * k < n]
        elif m == 0xDD and i + 5 < n:
            r["dri"] = (b[i + 4] << 8) | b[i + 5]
        elif m == 0xDA:
            r["has_sos"] = True
            j = i + 2 + L
            exp = 0
            while j + 1 < n:
                if b[j] == 0xFF and b[j + 1] != 0x00:
                    mm = b[j + 1]
                    if 0xD0 <= mm <= 0xD7:
                        if (mm - 0xD0) != (exp % 8):
                            r["rst_order_ok"] = False
                        exp += 1
                        r["rst"] += 1
                        j += 2
                        continue
                    if mm == 0xD9:
                        r["eoi_at"] = j
                        r["trailing_after_eoi"] = n - (j + 2)
                        break
                    if mm == 0xFF:
                        j += 1
                        continue
                    r["other_markers_in_scan"] += 1
                    j += 2
                    continue
                j += 1
            break
        i += 2 + L
    if samp and r["w"] and r["h"]:
        hmax = max(s[0] for s in samp) or 1
        vmax = max(s[1] for s in samp) or 1
        r["mcus"] = math.ceil(r["w"] / (8 * hmax)) * math.ceil(r["h"] / (8 * vmax))
        if r["dri"]:
            r["expected_rst"] = math.ceil(r["mcus"] / r["dri"]) - 1
    if r["w"] is None:
        r["issues"].append("no SOF0/1/2")
    if not r["has_sos"]:
        r["issues"].append("no SOS")
    if r["has_sos"] and r["eoi_at"] is None:
        r["issues"].append("no EOI after scan")
    if not r["rst_order_ok"]:
        r["issues"].append("RST markers out of order")
    if r["other_markers_in_scan"]:
        r["issues"].append(f"{r['other_markers_in_scan']} stray markers in scan")
    if r["expected_rst"] is not None and r["rst"] != r["expected_rst"]:
        r["issues"].append(f"RST count {r['rst']} != expected {r['expected_rst']}")
    r["ok"] = bool(start >= 0 and r["w"] and r["has_sos"] and r["eoi_at"] is not None and r["rst_order_ok"]
                   and r["other_markers_in_scan"] == 0
                   and (r["expected_rst"] is None or r["rst"] == r["expected_rst"]))
    return r


# --------------------------------------------------------------------------------------------- optional decoders
def _strict_decode(b: bytes) -> tuple[bool | None, str | None, str | None]:
    """(ok, method, error). ok None when no strict decoder is importable."""
    try:
        import simplejpeg  # bundles libjpeg-turbo; strict=True turns libjpeg warnings into errors
        try:
            simplejpeg.decode_jpeg(b, strict=True)
            return True, "simplejpeg(strict=True)", None
        except Exception as e:
            return False, "simplejpeg(strict=True)", f"{type(e).__name__}: {str(e)[:200]}"
    except ImportError:
        pass
    try:
        from turbojpeg import TurboJPEG, TJFLAG_STOPONWARNING  # PyTurboJPEG; needs libturbojpeg installed
        try:
            tj = TurboJPEG()
        except Exception:
            return None, None, None
        try:
            tj.decode(b, flags=TJFLAG_STOPONWARNING)
            return True, "PyTurboJPEG(TJFLAG_STOPONWARNING)", None
        except Exception as e:
            return False, "PyTurboJPEG(TJFLAG_STOPONWARNING)", f"{type(e).__name__}: {str(e)[:200]}"
    except ImportError:
        pass
    return None, None, None


def _lenient_decode(b: bytes) -> tuple[bool | None, str | None]:
    """(ok, method). ok None when no decoder is importable."""
    try:
        import simplejpeg
        try:
            simplejpeg.decode_jpeg(b, strict=False)
            return True, "simplejpeg(strict=False)"
        except Exception:
            return False, "simplejpeg(strict=False)"
    except ImportError:
        pass
    try:
        import io
        from PIL import Image
        try:
            im = Image.open(io.BytesIO(b))
            im.load()
            return True, "Pillow"
        except Exception:
            return False, "Pillow"
    except ImportError:
        pass
    return None, None


def decoders_available() -> dict[str, bool]:
    """Which optional decoders are importable (for the result's environment section)."""
    out = {}
    for mod in ("simplejpeg", "turbojpeg", "PIL"):
        try:
            __import__(mod)
            out[mod] = True
        except Exception:
            out[mod] = False
    return out


def check_jpeg(b: bytes, decode: bool = True) -> dict[str, Any]:
    """Check one frame. ``decode=False`` skips the (slow) decoders: lenient_ok = marker walk, strict_ok = None."""
    b = bytes(b)
    soi_at = b.find(b"\xff\xd8")
    walk = marker_walk(b)
    sof = parse_sof0(b)
    span = header_span(b)
    hdr_sha1 = hashlib.sha1(b[span[0]:span[1]]).hexdigest() if span else None
    res: dict[str, Any] = {
        "bytes": len(b),
        "soi": len(b) >= 2 and b[:2] == b"\xff\xd8",
        "bytes_before_soi": soi_at if soi_at > 0 else (0 if soi_at == 0 else None),
        "eoi": walk["eoi_at"] is not None,
        "trailing_after_eoi": walk["trailing_after_eoi"],
        "sof0_w": sof["w"] if sof else None,
        "sof0_h": sof["h"] if sof else None,
        "sof_type": sof["type"] if sof else None,
        "header_sha1": hdr_sha1,
        "header_bytes": (span[1] - span[0]) if span else None,
        "marker_ok": walk["ok"],
        "marker_issues": walk["issues"],
        "lenient_ok": walk["ok"],
        "lenient_method": "marker_walk",
        "strict_ok": None,
        "strict_method": None,
        "strict_error": None,
        "extra_bytes_before_eoi": None,
    }
    if not decode or len(b) < 4:
        return res
    sok, smeth, serr = _strict_decode(b)
    res["strict_ok"], res["strict_method"], res["strict_error"] = sok, smeth, serr
    if sok is True:
        res["extra_bytes_before_eoi"] = 0
    elif serr:
        m = _EXTRANEOUS_RE.search(serr)
        if m and m.group(2).lower() == "d9":
            res["extra_bytes_before_eoi"] = int(m.group(1))
    if sok is True:
        res["lenient_ok"], res["lenient_method"] = bool(walk["ok"]), "marker_walk+strict_decode"
    else:
        lok, lmeth = _lenient_decode(b)
        if lok is not None:
            res["lenient_ok"] = bool(walk["ok"] and lok)
            res["lenient_method"] = f"marker_walk+{lmeth}"
    return res


def summarize_checks(checks: list[dict[str, Any]], want_w: int | None = None,
                     want_h: int | None = None) -> dict[str, Any]:
    """Aggregate check_jpeg results of one run: counts, fractions, SOF size match, distinct header hashes."""
    n = len(checks)
    if n == 0:
        return {"n": 0}

    def frac(k: str) -> float | None:
        vals = [c[k] for c in checks if c.get(k) is not None]
        return (sum(1 for v in vals if v) / len(vals)) if vals else None

    sizes: dict[str, int] = {}
    hdrs: dict[str, int] = {}
    extra = [c["extra_bytes_before_eoi"] for c in checks if c.get("extra_bytes_before_eoi")]
    for c in checks:
        s = f"{c.get('sof0_w')}x{c.get('sof0_h')}"
        sizes[s] = sizes.get(s, 0) + 1
        if c.get("header_sha1"):
            hdrs[c["header_sha1"]] = hdrs.get(c["header_sha1"], 0) + 1
    size_ok = None
    if want_w and want_h:
        size_ok = sum(1 for c in checks if c.get("sof0_w") == want_w and c.get("sof0_h") == want_h) / n
    return {"n": n, "soi_fraction": frac("soi"), "eoi_fraction": frac("eoi"), "marker_ok_fraction": frac("marker_ok"),
            "lenient_ok_fraction": frac("lenient_ok"), "strict_ok_fraction": frac("strict_ok"),
            "sof_sizes": sizes, "sof_matches_request_fraction": size_ok, "header_sha1_counts": hdrs,
            "extra_bytes_before_eoi": ({"n": len(extra), "min": min(extra), "max": max(extra)} if extra else None)}
