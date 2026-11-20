"""Header, rows, footer and CRC of the timing sidecar, and its strict read (specs/recorder.md, 6.5, 8.1)."""
import re
import zlib
from typing import NamedTuple

INTEGER = re.compile(rb"-?(0|[1-9][0-9]*)")  # SFF-701
COLUMN_LINE = b"frame,source_frame_number,arrival_ns,sample_ns,flags,byte_offset,byte_size,crc32\n"
GAP, FILLED, ENCODE_SKIP, REPEAT, MISSING = 1, 2, 4, 8, 16


class Row(NamedTuple):
    frame: int
    source_frame_number: int | None
    arrival_ns: int | None
    sample_ns: int | None
    flags: int
    byte_offset: int | None
    byte_size: int | None


class Sidecar(NamedTuple):
    rows: list  # the usable rows: up to the first row that is not complete or has a wrong CRC
    ends: list  # the byte offset after each usable row
    header_end: int  # the byte offset after the column line
    has_end: bool  # the last line is an `# end` line
    data: bytes


def header_line(key, value) -> bytes:
    return f"# {key}={value}\n".encode()


def row_line(row: Row) -> bytes:
    """One row with its CRC (SFF-744): the CRC-32 of the bytes before the comma of the crc32 field."""
    body = ",".join("" if v is None else str(v) for v in row).encode() + b","
    return body + f"{zlib.crc32(body[:-1]):08x}\n".encode()


def row_flags(previous_sfn, sfn, missing) -> int:
    """`gap` and `repeat` of 7.1, and `missing` of 7.2."""
    flags = MISSING if missing else 0
    if previous_sfn is not None and sfn is not None:
        if sfn == previous_sfn:
            flags |= REPEAT
        elif sfn != previous_sfn + 1:
            flags |= GAP
    return flags


def end_line(rows: int, gaps: int, missing: int) -> bytes:
    """The `# end` line of SFF-745 with `missing` before the last key (F-1). 5a never fills or skips."""
    return f"# end rows={rows} gaps={gaps} filled=0 missing={missing} encode_skips=0\n".encode()


def counts(rows) -> tuple[int, int]:
    """The `gaps` and `missing` counts of rows."""
    return sum(1 for r in rows if r.flags & GAP), sum(1 for r in rows if r.flags & MISSING)


def _int(field: bytes):
    if field == b"":
        return None
    if not INTEGER.fullmatch(field):
        raise ValueError(f"integer not in the form of SFF-701: {field!r}")
    return int(field)


def read_strict(path) -> Sidecar:
    """Read a sidecar strictly (SFF-746). Raises ValueError when it has no complete column line."""
    with open(path, "rb") as handle:
        data = handle.read()
    lines = data.split(b"\n")
    torn = lines.pop()  # the bytes after the last LF: empty, or a torn last line
    pos, index = 0, 0
    while index < len(lines) and lines[index].startswith(b"# "):
        pos += len(lines[index]) + 1
        index += 1
    if index >= len(lines) or lines[index] + b"\n" != COLUMN_LINE:
        raise ValueError(f"{path}: no complete column line")
    header_end = pos = pos + len(COLUMN_LINE)
    rows, ends = [], []
    for line in lines[index + 1:]:
        if line.startswith(b"#"):
            break
        fields = line.split(b",")
        if len(fields) != 8 or fields[7] != f"{zlib.crc32(line[:line.rindex(b',')]):08x}".encode():
            break
        try:
            row = Row(*(_int(f) for f in fields[:7]))
        except ValueError:
            break
        if row.frame is None or row.flags is None:
            break
        rows.append(row)
        pos += len(line) + 1
        ends.append(pos)
    has_end = not torn and bool(lines) and lines[-1].startswith(b"# end")
    return Sidecar(rows, ends, header_end, has_end, data)
