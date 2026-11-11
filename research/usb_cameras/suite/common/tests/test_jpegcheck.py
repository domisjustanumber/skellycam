"""JPEG checks: marker walk, SOF0, header SHA-1 span, strict/lenient decode, extraneous bytes before EOI."""
import base64
import hashlib

import pytest

from common import jpegcheck as jc

# 32x16 baseline JPEG made with Pillow (quality 85); embedded so the test needs no decoder to run.
JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAUDBAQEAwUEBAQFBQUGBwwIBwcHBw8LCwkMEQ8SEhEPERETFhwXExQaFRERGCEYGh0d"
    "Hx8fExciJCIeJBweHx7/2wBDAQUFBQcGBw4ICA4eFBEUHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4e"
    "Hh4eHh4eHh7/wAARCAAQACADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUF"
    "BAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVW"
    "V1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi"
    "4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAEC"
    "AxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVm"
    "Z2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq"
    "8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDwOw8KfZsfu9+72xW9Y+FPs2P3e/d7Y6V61Y+FPs2P3e/d7Y6Vv2HhT7Nj93v3e2MYrz8V"
    "xP7Lrycnz9nf/wBL5/8AyU+UyLjG9ve/4J5LYeFPs2P3e/d7Yxit+w8KfZsfut+72x0r1mw8KfZsfut+72x0rfsPCn2bH7rdu9sd"
    "K+dxXE/suvJyfP2d/wD0vn/8lP2fIuMb297/AIJ//9k=")


def _has(mod):
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def test_parse_sof0_and_header():
    sof = jc.parse_sof0(JPEG)
    assert sof["type"] == "SOF0" and (sof["w"], sof["h"]) == (32, 16)
    assert len(sof["components"]) == 3
    r = jc.check_jpeg(JPEG, decode=False)
    assert r["soi"] and r["eoi"] and r["marker_ok"] and r["lenient_ok"]
    assert (r["sof0_w"], r["sof0_h"]) == (32, 16)
    assert r["trailing_after_eoi"] == 0
    s, e = jc.header_span(JPEG)
    assert s == 0 and r["header_bytes"] == e
    assert r["header_sha1"] == hashlib.sha1(JPEG[:e]).hexdigest()
    # header ends with the SOS segment: the byte after it is entropy data, the 2 bytes at its start are FFDA
    sos_at = JPEG.rfind(b"\xff\xda", 0, e)
    assert sos_at > 0 and sos_at + 2 + ((JPEG[sos_at + 2] << 8) | JPEG[sos_at + 3]) == e


def test_header_sha1_matches_mjpeg_common_prefix():
    # mjpeg/mjpeg_common.jpeg_header hashes b[i:pos+2+ln] (SOI..SOS) and keeps 12 hex digits
    r = jc.check_jpeg(JPEG, decode=False)
    s, e = jc.header_span(JPEG)
    assert r["header_sha1"][:12] == hashlib.sha1(JPEG[s:e]).hexdigest()[:12]


def test_truncated_and_garbage():
    trunc = JPEG[: len(JPEG) // 2]
    r = jc.check_jpeg(trunc, decode=False)
    assert r["soi"] and not r["eoi"] and not r["marker_ok"] and not r["lenient_ok"]
    g = jc.check_jpeg(b"\x00" * 100)
    assert not g["soi"] and g["sof0_w"] is None and g["header_sha1"] is None
    assert jc.check_jpeg(b"")["soi"] is False


def test_padding_after_eoi_and_leading_bytes():
    r = jc.check_jpeg(JPEG + b"\x00" * 7, decode=False)
    assert r["eoi"] and r["trailing_after_eoi"] == 7
    r2 = jc.check_jpeg(b"\x00\x00" + JPEG, decode=False)
    assert not r2["soi"] and r2["bytes_before_soi"] == 2 and r2["sof0_w"] == 32


@pytest.mark.skipif(not _has("simplejpeg"), reason="simplejpeg not installed")
def test_strict_decode_and_extraneous_bytes():
    ok = jc.check_jpeg(JPEG)
    assert ok["strict_ok"] is True and ok["extra_bytes_before_eoi"] == 0 and ok["lenient_ok"]
    # Junk before EOI, like the generic camera's 1080p frames. libjpeg's Huffman bit buffer reads a few bytes
    # ahead, so its count is up to ~5 lower than the bytes inserted (a handful of zero bytes can go unnoticed).
    bad = JPEG[:-2] + b"\xab" * 100 + JPEG[-2:]
    r = jc.check_jpeg(bad)
    assert r["strict_ok"] is False
    assert 90 <= r["extra_bytes_before_eoi"] <= 100
    assert r["lenient_ok"] is True                  # lenient decoders accept it (REPORT finding 6)


def test_no_decoder_gives_none(monkeypatch):
    monkeypatch.setattr(jc, "_strict_decode", lambda b: (None, None, None))
    monkeypatch.setattr(jc, "_lenient_decode", lambda b: (None, None))
    r = jc.check_jpeg(JPEG)
    assert r["strict_ok"] is None and r["extra_bytes_before_eoi"] is None and r["lenient_ok"] is True


def test_summarize():
    s = jc.summarize_checks([jc.check_jpeg(JPEG, decode=False)] * 3 + [jc.check_jpeg(JPEG[:100], decode=False)],
                            32, 16)
    assert s["n"] == 4 and s["marker_ok_fraction"] == 0.75 and s["sof_matches_request_fraction"] == 0.75
