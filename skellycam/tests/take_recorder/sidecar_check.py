"""A strict reader of a video timing sidecar for the recorder tests (specs/recorder.md, section 6.5).

Written from the text of the spec (6.5, 7.1 to 7.4) and of the format (SFF-700, SFF-701, SFF-704,
SFF-741 to SFF-747, SFF-754 to SFF-758, F-1, F-2). It imports no code of
`skellycam.core.take_recorder`, so it is an independent check of the product.
"""

import re
import zlib
from dataclasses import dataclass, field

HEADER_KEYS = (
    "skellyfileformat", "format_version", "format_prerelease", "writer", "take_uuid", "take_start_host_ns",
    "take_start_utc_ns", "utc_offset_min", "clock", "clock_hz", "group_size", "audio_count", "group_position",
    "camera_key", "camera_label", "nominal_rate", "display_rotation",
)
TAKE_KEYS = HEADER_KEYS[4:12]  # take_uuid to audio_count (SFF-749)
COLUMNS = ("frame", "source_frame_number", "arrival_ns", "sample_ns", "flags", "byte_offset", "byte_size", "crc32")
END_KEYS = ("rows", "gaps", "filled", "missing", "encode_skips")

GAP, FILLED, ENCODE_SKIP, REPEAT, MISSING = 1, 2, 4, 8, 16

INTEGER = re.compile(rb"-?(0|[1-9][0-9]*)")
CRC = re.compile(rb"[0-9a-f]{8}")


@dataclass
class Row:
    frame: int
    source_frame_number: int | None
    arrival_ns: int | None
    sample_ns: int | None
    flags: int
    byte_offset: int | None
    byte_size: int | None
    crc32: str
    raw: bytes  # the line without its LF
    offset: int  # offset of the line in the file

    @property
    def missing(self):
        return bool(self.flags & MISSING)


@dataclass
class Sidecar:
    header: dict  # key -> value text, in file order
    header_order: list
    columns: list
    rows: list  # the usable rows (strict read)
    footer: list  # (word, {key: value}, raw line)
    torn_bytes: int
    bad_row: str | None  # why the strict read stopped at a complete line, or None
    rows_end: int  # offset after the last usable row
    data: bytes = field(repr=False, default=b"")

    @property
    def end(self):
        """The `# end` counts as ints, or None when the last line is not an `# end` line."""
        if not self.footer or self.footer[-1][0] != "end":
            return None
        return {k: int(v) for k, v in self.footer[-1][1].items()}

    def footer_words(self):
        return [word for word, _, _ in self.footer]


def row_crc(raw_line):
    """The CRC text of a row: CRC-32 of the bytes before the comma that comes before the crc32 field."""
    return f"{zlib.crc32(raw_line[: raw_line.rindex(b',')]) & 0xFFFFFFFF:08x}"


def make_row(frame, source_frame_number, arrival_ns, sample_ns, flags, byte_offset, byte_size):
    """One row line with its LF, as 6.5 gives it. None gives an empty field."""
    fields = [frame, source_frame_number, arrival_ns, sample_ns, flags, byte_offset, byte_size]
    body = ",".join("" if v is None else str(v) for v in fields).encode()
    return body + b"," + row_crc(body + b",x").encode() + b"\n"


def _int(text, allow_empty):
    if text == b"":
        if allow_empty:
            return None
        raise ValueError("empty field")
    if not INTEGER.fullmatch(text):
        raise ValueError(f"integer not in the form of SFF-701: {text!r}")
    return int(text)


def _footer(line):
    text = line.decode("utf-8")
    if not text.startswith("# "):
        raise ValueError(f"bad footer line {text!r}")
    parts = text[2:].split(" ")
    word, values = parts[0], {}
    rest = parts[1:]
    for i, part in enumerate(rest):
        key, sep, value = part.partition("=")
        if not sep:
            raise ValueError(f"bad footer key {part!r}")
        if word == "repair" and key == "repair_writer":  # the value of the last key can hold a space
            values[key] = " ".join([value, *rest[i + 1:]])
            break
        values[key] = value
    return word, values, line


def parse(data):
    """Read a sidecar strictly (SFF-746). Raises ValueError on a header or column-line defect."""
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("byte order mark")
    if b"\r" in data:
        raise ValueError("CR in the file")
    data.decode("utf-8")
    lines, pos = [], 0
    while pos < len(data):
        end = data.find(b"\n", pos)
        if end < 0:
            lines.append((pos, data[pos:], False))
            break
        lines.append((pos, data[pos:end], True))
        pos = end + 1
    header, order, index = {}, [], 0
    while index < len(lines) and lines[index][1].startswith(b"# ") and b"=" in lines[index][1] and lines[index][2]:
        key, _, value = lines[index][1][2:].decode("utf-8").partition("=")
        header[key] = value
        order.append(key)
        index += 1
    if index >= len(lines) or not lines[index][2]:
        raise ValueError("no complete column line")
    columns = lines[index][1].decode("utf-8").split(",")
    index += 1
    rows, footer, torn, bad, rows_end = [], [], 0, None, lines[index - 1][0] + len(lines[index - 1][1]) + 1
    for offset, line, complete in lines[index:]:
        if not complete:
            torn += len(line)
            break
        if line.startswith(b"#"):
            footer.append(_footer(line))
            continue
        if footer:
            bad = "data row after a footer line"
            break
        fields = line.split(b",")
        if len(fields) != len(COLUMNS):
            bad = f"row with {len(fields)} fields"
            break
        if not CRC.fullmatch(fields[7]) or row_crc(line) != fields[7].decode():
            bad = "crc_mismatch"
            break
        try:
            values = [_int(fields[0], False), _int(fields[1], True), _int(fields[2], True), _int(fields[3], True),
                      _int(fields[4], False), _int(fields[5], True), _int(fields[6], True)]
        except ValueError as error:
            bad = str(error)
            break
        rows.append(Row(*values, fields[7].decode(), line, offset))
        rows_end = offset + len(line) + 1
    return Sidecar(header, order, columns, rows, footer, torn, bad, rows_end, data)


def read(path):
    with open(path, "rb") as handle:
        return parse(handle.read())


def expected_flags(previous_sfn, sfn, missing):
    """The flags of a row from 7.1 and 7.2: gap, repeat and missing."""
    flags = MISSING if missing else 0
    if previous_sfn is not None and sfn is not None:
        if sfn == previous_sfn:
            flags |= REPEAT
        elif sfn != previous_sfn + 1:
            flags |= GAP
    return flags
