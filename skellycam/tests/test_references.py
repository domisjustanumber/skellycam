"""Check the required provenance fields of each source key that the code cites (CITATIONS.md)."""
from pathlib import Path
import re


def test_cited_references_have_required_metadata():
    root = Path(__file__).resolve().parents[2]
    text = (root / "references.bib").read_text(encoding="utf-8")
    entries = dict(re.findall(r"@\w+\{(\w+),\s*(.*?)(?=\n\}|\Z)", text, re.S))
    sources = ["skellycam/core/device_detection/usb_connection.py"]
    keys = [key for source in sources
            for key in re.findall(r"\[@(\w+)\]", (root / source).read_text(encoding="utf-8"))]
    assert keys
    for key in keys:
        assert key in entries
        for field in ("title", "url", "urldate", "review", "claim"):
            assert re.search(rf"\b{field}\s*=\s*\{{[^}}]+\}}", entries[key])
