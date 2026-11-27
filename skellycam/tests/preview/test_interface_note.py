"""T-PRV-31: the interface note for the FreeMoCap session (specs/preview-4b.md section 8).

doc. The note exists; it has a heading for each item of section 8; its camera message table equals table 3.2 of
`specs/preview.md`. The test does not check the prose.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "specs" / "preview-interface-note.md"
SPEC_4A = ROOT / "specs" / "preview.md"
HEADINGS = ("Camera message", "Ready message and safety net", "Deleted", "framerate_update", "Camera status", "Tile",
            "Compression")


def headings(text):
    return [re.sub(r"^#+\s*(\d+(\.\d+)*\.?\s*)?", "", line).strip() for line in text.splitlines()
            if line.startswith("#")]


def first_table_after(text, heading_rx):
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("#") and re.search(heading_rx, line))
    rows, seen = [], False
    for line in lines[start + 1:]:
        if line.startswith("#") and not seen:
            break
        if line.startswith("|"):
            seen = True
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-+:?", cell) for cell in cells):
                rows.append(cells)
        elif seen:
            break
    return rows


def test_t_prv_31_the_interface_note():
    assert NOTE.exists(), "specs/preview-interface-note.md does not exist"
    note = NOTE.read_text(encoding="utf-8")
    found = headings(note)
    missing = [h for h in HEADINGS if not any(f.lower().startswith(h.lower()) for f in found)]
    assert missing == [], f"no heading for {missing}; headings: {found}"
    table_4a = first_table_after(SPEC_4A.read_text(encoding="utf-8"), r"^### 3\.2 ")
    assert table_4a, "no table 3.2 in specs/preview.md"
    assert first_table_after(note, r"Camera message") == table_4a
