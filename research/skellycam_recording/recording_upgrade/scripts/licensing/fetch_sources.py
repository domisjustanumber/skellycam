# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf==5.4.0"]
# ///
"""Download primary-source pages for the licensing notes and extract plain text.

For each source in sources.json ({"id", "url"}) this saves the raw bytes and a whitespace-normalised
text rendering under <cache>/ and records sha256, HTTP status and fetch time in <cache>/fetch_log.json.
PDFs are converted with pypdf 5.4.0. Nothing is executed from the downloaded content.

Then `verify` mode checks that every quote listed in quotes.json occurs verbatim (after whitespace
and typographic-quote normalisation) in the extracted text of its source, and writes a JSON report.

Usage:
  uv run --script fetch_sources.py fetch  --sources sources.json --cache <dir> [--only id1,id2]
  uv run --script fetch_sources.py verify --quotes quotes.json --cache <dir> --out <report.json>
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import html.parser
import io
import json
import pathlib
import re
import subprocess
import sys

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0 Safari/537.36"


class _Text(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.skip += 1
        elif tag in ("p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "td", "th", "section", "pre"):
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace(" ", " ").replace("–", "-").replace("—", "-").replace("­", "")
    return re.sub(r"\s+", " ", s).strip()


def to_text(raw: bytes, url: str, ctype: str) -> str:
    if raw[:5] == b"%PDF-" or url.lower().endswith(".pdf"):
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(raw))
        return "\n".join((p.extract_text() or "") for p in r.pages)
    txt = raw.decode("utf-8", "replace")
    if "<html" in txt[:5000].lower() or "<!doctype" in txt[:200].lower():
        p = _Text(); p.feed(txt); return "".join(p.out)
    return txt


def fetch(url: str) -> tuple[int, str, bytes]:
    # curl (Git for Windows build) follows redirects; -w prints final status and content type.
    r = subprocess.run(["curl", "-sL", "--max-time", "60", "-A", UA, "-o", "-", "-w", "\n%{http_code} %{content_type}", url],
                       capture_output=True)
    body, _, tail = r.stdout.rpartition(b"\n")
    parts = tail.decode(errors="replace").split(" ", 1)
    return int(parts[0] or 0), (parts[1] if len(parts) > 1 else ""), body


def cmd_fetch(a):
    cache = pathlib.Path(a.cache); cache.mkdir(parents=True, exist_ok=True)
    log_p = cache / "fetch_log.json"
    log = json.loads(log_p.read_text()) if log_p.exists() else {}
    only = set(a.only.split(",")) if a.only else None
    for s in json.loads(pathlib.Path(a.sources).read_text(encoding="utf-8")):
        if only and s["id"] not in only:
            continue
        code, ctype, raw = fetch(s["url"])
        (cache / f"{s['id']}.raw").write_bytes(raw)
        try:
            text = norm(to_text(raw, s["url"], ctype))
        except Exception as e:  # noqa: BLE001
            text = f"EXTRACT_ERROR {e!r}"
        (cache / f"{s['id']}.txt").write_text(text, encoding="utf-8")
        log[s["id"]] = {"url": s["url"], "http_status": code, "content_type": ctype, "bytes": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(), "text_chars": len(text),
                        "fetched_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        print(f"{s['id']:28s} {code} {len(raw):>9d} B  text {len(text):>8d} chars  {s['url']}")
    log_p.write_text(json.dumps(log, indent=1), encoding="utf-8")


def cmd_verify(a):
    cache = pathlib.Path(a.cache)
    log = json.loads((cache / "fetch_log.json").read_text())
    rep, bad = [], 0
    for q in json.loads(pathlib.Path(a.quotes).read_text(encoding="utf-8")):
        tp = cache / f"{q['source']}.txt"
        text = norm(tp.read_text(encoding="utf-8")) if tp.exists() else ""
        found = norm(q["quote"]) in text
        bad += not found
        rep.append({**q, "found_verbatim": found, "url": log.get(q["source"], {}).get("url"),
                    "sha256": log.get(q["source"], {}).get("sha256"),
                    "fetched_utc": log.get(q["source"], {}).get("fetched_utc")})
        if not found:
            print("NOT FOUND:", q["source"], "|", q["quote"][:100])
    pathlib.Path(a.out).write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(f"{len(rep) - bad}/{len(rep)} quotes found verbatim")


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch"); f.add_argument("--sources", required=True); f.add_argument("--cache", required=True); f.add_argument("--only")
    v = sub.add_parser("verify"); v.add_argument("--quotes", required=True); v.add_argument("--cache", required=True); v.add_argument("--out", required=True)
    a = ap.parse_args()
    {"fetch": cmd_fetch, "verify": cmd_verify}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
