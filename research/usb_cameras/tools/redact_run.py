# /// script
# requires-python = "==3.12.13"
# dependencies = []
# ///
"""Redact private identifiers from a suite results folder before it is committed (privacy rule, 2026-11-11).

    uv run --python 3.12 --script research/usb_cameras/tools/redact_run.py RUN_DIR [RUN_DIR ...] [--apply]

Without --apply it only reports what it would change. The values are derived from the run's own files, so no private
value is ever written into git:

- USB iSerial strings (``USB\\VID_xxxx&PID_xxxx\\<serial>``; Windows-generated instance ids contain ``&`` and are
  kept). The C922's serial becomes ``C922SN01`` (the placeholder the repo already uses; same length); any other
  device's serial becomes ``SN_<VID><PID>`` padded or cut to the serial's length. Also replaced where the serial
  appears alone (file names, ``sn=`` keys, slugs), case-insensitively.
- USB ContainerIds whose last field is a MAC (v1 UUID node, not the ``...806E6F6E6963`` "no NIC" filler): the first
  10 hex digits of the node become zeros, the last byte is kept so distinct containers stay distinct.
- Private IPv4 host addresses (192.168.x.y, 10.x.y.z, 172.16-31.x.y, 169.254.x.y; not .0/.255, not 127.x) become
  ``a.b.c.x``.
- Telemetry ids (``user_id=<32 hex>``) become ``user_id=<redacted>``.
- Personal apps in process lists: ``"name": "<App>.exe"`` for chat/conferencing apps becomes
  ``"name": "conferencing_app.exe"``.
- Email addresses other than public project/vendor addresses become ``[email removed]``.

File names are renamed with the same serial mapping. Binary files (images, video) are never edited: the script lists
any image or video it finds, because those must not be committed at all (move them to skellycam-raw).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TEXT_EXT = {".json", ".jsonl", ".md", ".txt", ".log", ".csv", ".tsv", ".py", ".html", ".xml", ".yaml", ".yml", ""}
MEDIA_EXT = {".jpg", ".jpeg", ".png", ".mjpeg", ".mjpg", ".mp4", ".mkv", ".avi", ".mov", ".wav", ".bmp", ".raw",
             ".yuv", ".nv12", ".pgm"}
C922 = ("046D", "085C")
SERIAL_RX = re.compile(r"(?i)USB\\{1,2}VID_([0-9A-F]{4})&PID_([0-9A-F]{4})\\{1,2}([0-9A-Z]{6,})(?![0-9A-Z&])")
CONTAINER_RX = re.compile(r"(?i)\b([0-9a-f]{8}-[0-9a-f]{4}-1[0-9a-f]{3}-[0-9a-f]{4}-)([0-9a-f]{12})\b")
NO_NIC = "806e6f6e6963"
IP_RX = re.compile(r"(?<![\d.])(192\.168|10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])|169\.254)\.(\d{1,3})\.(\d{1,3})(?![\d.])")
TELEMETRY_RX = re.compile(r"(?i)(user_id\s*[=:]\s*\"?)[0-9a-f]{32}")
APPS_RX = re.compile(r'(?i)"name":\s*"(discord|signal|whatsapp|telegram|zoom|teams|ms-teams|slack|skype|webex)[^"]*\.exe"')
EMAIL_RX = re.compile(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
PUBLIC_EMAIL = re.compile(r"(?i)(noreply|no-reply|users\.noreply\.github\.com|freemocap\.org|x264\.com|btbn\.de|"
                          r"stemmer-imaging\.com|example\.(com|org|invalid)|anthropic\.com)$")


def find_serials(files: list[Path]) -> dict[str, str]:
    serials: dict[str, str] = {}
    for f in files:
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in SERIAL_RX.finditer(t):
            vid, pid, sn = m.group(1).upper(), m.group(2).upper(), m.group(3)
            if sn.upper() in serials or re.fullmatch(r"(?i)C922SN01|SN_[0-9A-F]+.*|PERIPHSN.*", sn):
                continue
            if (vid, pid) == C922:
                rep = "C922SN01"
            else:
                rep = f"SN_{vid}{pid}"
            rep = (rep + "0" * len(sn))[:len(sn)] if len(rep) < len(sn) else rep[:max(len(sn), 8)]
            serials[sn.upper()] = rep
    return serials


def redact_text(t: str, serials: dict[str, str]) -> tuple[str, dict]:
    counts: dict[str, int] = {}

    def bump(k, n):
        if n:
            counts[k] = counts.get(k, 0) + n

    for sn, rep in serials.items():
        t, n = re.subn(re.escape(sn), rep, t, flags=re.I)
        bump("serial", n)

    def cont(m):
        node = m.group(2)
        if node.lower() == NO_NIC:
            return m.group(0)
        return m.group(1) + "0000000000" + node[-2:]
    t, n = CONTAINER_RX.subn(cont, t)
    bump("container_mac", n)

    def ip(m):
        last = m.group(3)
        if last in ("0", "255"):
            return m.group(0)
        return f"{m.group(1)}.{m.group(2)}.x"
    t, n = IP_RX.subn(ip, t)
    bump("private_ip", n)
    t, n = TELEMETRY_RX.subn(lambda m: m.group(1) + "<redacted>", t)
    bump("telemetry_id", n)
    t, n = APPS_RX.subn('"name": "conferencing_app.exe"', t)
    bump("personal_app", n)

    def em(m):
        return m.group(0) if PUBLIC_EMAIL.search(m.group(0)) else "[email removed]"
    t2 = EMAIL_RX.sub(em, t)
    bump("email", sum(1 for a, b in zip(EMAIL_RX.findall(t), EMAIL_RX.findall(t2)) if a != b))
    return t2, counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dirs", nargs="+")
    ap.add_argument("--apply", action="store_true", help="write the changes (default: report only)")
    a = ap.parse_args(argv)
    files = [f for d in a.run_dirs for f in Path(d).rglob("*") if f.is_file()]
    media = [f for f in files if f.suffix.lower() in MEDIA_EXT]
    text = [f for f in files if f.suffix.lower() in TEXT_EXT]
    serials = find_serials(text)
    print(f"{len(files)} files, {len(text)} text, {len(media)} media; serials found: {len(serials)} "
          f"({', '.join(f'{s[:4]}… -> {r}' for s, r in serials.items())})")
    total: dict[str, int] = {}
    changed = 0
    for f in text:
        t = f.read_text(encoding="utf-8", errors="surrogateescape")
        t2, c = redact_text(t, serials)
        if t2 != t:
            changed += 1
            for k, v in c.items():
                total[k] = total.get(k, 0) + v
            if a.apply:
                f.write_text(t2, encoding="utf-8", errors="surrogateescape")
    renames = []
    for f in sorted(files, key=lambda p: len(p.parts), reverse=True):
        new = f.name
        for sn, rep in serials.items():
            new = re.sub(re.escape(sn), rep, new, flags=re.I)
        if new != f.name:
            renames.append((f, f.with_name(new)))
    dirs = sorted({d for f in files for d in f.parents}, key=lambda p: len(p.parts), reverse=True)
    for d in dirs:
        new = d.name
        for sn, rep in serials.items():
            new = re.sub(re.escape(sn), rep, new, flags=re.I)
        if new != d.name:
            renames.append((d, d.with_name(new)))
    print(f"text files changed: {changed}; replacements: {total}; paths to rename: {len(renames)}")
    if media:
        print("MEDIA FILES (never commit; move to C:/Users/Dom/Documents/skellycam-raw with mirrored paths):")
        for m in media[:50]:
            print("  ", m)
    if a.apply:
        for src, dst in renames:                       # deepest first: files, then their folders
            if src.exists() and not dst.exists():
                src.rename(dst)
        print("applied")
    else:
        print("report only: re-run with --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
