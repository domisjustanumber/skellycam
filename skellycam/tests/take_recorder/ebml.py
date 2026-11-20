"""An independent EBML and Matroska walker for the recorder tests (specs/recorder.md, sections 6.3 and 7.4).

Written from RFC 8794 (EBML) and RFC 9559 (Matroska). It imports no code of
`skellycam.core.take_recorder` and no PyAV, so it is an independent check of the camera files.
It reads a finished file, a live file and a killed file: a Segment or a Cluster of unknown size, a
cut last element, and a CRC-32 element as the first child of a Cluster.
"""

import struct
import zlib
from dataclasses import dataclass, field

EBML = 0x1A45DFA3
DOC_TYPE = 0x4282
SEGMENT = 0x18538067
SEEK_HEAD = 0x114D9B74
INFO = 0x1549A966
TIMESTAMP_SCALE = 0x2AD7B1
TRACKS = 0x1654AE6B
TRACK_ENTRY = 0xAE
TRACK_NUMBER = 0xD7
TRACK_TYPE = 0x83
CODEC_ID = 0x86
DEFAULT_DURATION = 0x23E383
VIDEO = 0xE0
PIXEL_WIDTH = 0xB0
PIXEL_HEIGHT = 0xBA
PROJECTION = 0x7670
PROJECTION_POSE_ROLL = 0x7675
CLUSTER = 0x1F43B675
CLUSTER_TIMESTAMP = 0xE7
SIMPLE_BLOCK = 0xA3
BLOCK_GROUP = 0xA0
CRC32 = 0xBF
CUES = 0x1C53BB6B
TAGS = 0x1254C367
VOID = 0xEC

# Elements that hold children and that the walker enters.
MASTERS = {EBML, SEGMENT, SEEK_HEAD, INFO, TRACKS, TRACK_ENTRY, VIDEO, PROJECTION, CLUSTER, BLOCK_GROUP, CUES, TAGS}
# Children of a Segment: an element of unknown size ends where one of these starts (RFC 8794 6.2).
SEGMENT_CHILDREN = {SEEK_HEAD, INFO, TRACKS, CLUSTER, CUES, TAGS, 0x1043A770, 0x1941A469}


def read_id(data, pos):
    """An element ID with its marker bits, and its length. ValueError on a bad first byte."""
    first = data[pos]
    for length in range(1, 5):
        if first & (0x80 >> (length - 1)):
            if pos + length > len(data):
                raise EOFError
            return int.from_bytes(data[pos:pos + length], "big"), length
    raise ValueError(f"bad element ID at {pos}")


def read_size(data, pos):
    """A data size (None for the unknown size) and its length. EOFError when it is cut."""
    first = data[pos]
    for length in range(1, 9):
        mask = 0x80 >> (length - 1)
        if first & mask:
            if pos + length > len(data):
                raise EOFError
            value = int.from_bytes(data[pos:pos + length], "big") & ((1 << (7 * length)) - 1)
            return (None if value == (1 << (7 * length)) - 1 else value), length
    raise ValueError(f"bad size at {pos}")


@dataclass
class Element:
    id: int
    start: int  # offset of the ID
    data_start: int
    size: int | None  # None: unknown size
    end: int  # offset after the element (for an unknown size: where the walker found its end)
    complete: bool
    children: list = field(default_factory=list)
    parent: "Element | None" = None


@dataclass
class Block:
    """One SimpleBlock (or Block of a BlockGroup) with its payload position (SFF-739)."""

    element_start: int
    end: int
    payload_offset: int
    payload_size: int
    track: int
    time_ms: int  # cluster timestamp + relative timestamp, in TimestampScale units
    keyframe: bool
    lacing: int
    simple: bool
    cluster_index: int


@dataclass
class Track:
    number: int
    codec_id: str
    track_type: int | None
    default_duration: int | None
    width: int | None
    height: int | None


@dataclass
class Cluster:
    start: int
    end: int
    size: int | None
    complete: bool
    first_child: int | None
    crc_present: bool
    crc_ok: bool | None
    block_count: int


@dataclass
class MkvFile:
    length: int
    doc_type: str | None
    segment_unknown_size: bool
    segment_data_start: int | None
    timestamp_scale: int | None
    tracks: list
    blocks: list  # complete blocks only, in file order
    clusters: list
    ids: set  # each element ID seen
    has_cues: bool
    cut_at: int | None  # offset of the first element that the file cuts, or None
    top: list


def walk(data):
    """Walk `data` (bytes) and return an MkvFile. A cut element ends the walk."""
    ids, top, state = set(), [], {"cut": None}

    def parse_children(parent, start, limit, unknown):
        pos = start
        while pos < limit:
            try:
                eid, idlen = read_id(data, pos)
                size, sizelen = read_size(data, pos + idlen)
            except (EOFError, IndexError):
                state["cut"] = pos if state["cut"] is None else state["cut"]
                return pos
            if unknown and parent is not None and parent.id == CLUSTER and eid in SEGMENT_CHILDREN:
                return pos  # a cluster of unknown size ends at the next segment child
            data_start = pos + idlen + sizelen
            ids.add(eid)
            if size is None:
                element = Element(eid, pos, data_start, None, limit, True, parent=parent)
                if eid in MASTERS:
                    element.end = parse_children(element, data_start, limit, True)
                else:
                    state["cut"] = pos if state["cut"] is None else state["cut"]
                    return pos
            else:
                end = data_start + size
                complete = end <= len(data)
                element = Element(eid, pos, data_start, size, min(end, len(data)), complete, parent=parent)
                if not complete:
                    state["cut"] = pos if state["cut"] is None else state["cut"]
                if eid in MASTERS:
                    parse_children(element, data_start, min(end, len(data)), False)
            (parent.children if parent is not None else top).append(element)
            if not element.complete or element.size is None and element.end >= limit:
                return element.end
            pos = element.end
        return pos

    parse_children(None, 0, len(data), False)

    def find(elements, eid):
        return [e for e in elements if e.id == eid]

    def uint(element):
        return int.from_bytes(data[element.data_start:element.end], "big")

    header = find(top, EBML)
    doc_type = None
    if header:
        found = find(header[0].children, DOC_TYPE)
        doc_type = data[found[0].data_start:found[0].end].rstrip(b"\x00").decode("ascii") if found else None
    segments = find(top, SEGMENT)
    segment = segments[0] if segments else None
    children = segment.children if segment else []
    scale = None
    for info in find(children, INFO):
        for element in find(info.children, TIMESTAMP_SCALE):
            scale = uint(element)
    tracks = []
    for tracks_element in find(children, TRACKS):
        for entry in find(tracks_element.children, TRACK_ENTRY):
            values = {e.id: e for e in entry.children}
            video = values.get(VIDEO)
            vids = {e.id: e for e in video.children} if video else {}
            tracks.append(Track(
                number=uint(values[TRACK_NUMBER]) if TRACK_NUMBER in values else None,
                codec_id=data[values[CODEC_ID].data_start:values[CODEC_ID].end].rstrip(b"\x00").decode("ascii") if CODEC_ID in values else None,
                track_type=uint(values[TRACK_TYPE]) if TRACK_TYPE in values else None,
                default_duration=uint(values[DEFAULT_DURATION]) if DEFAULT_DURATION in values else None,
                width=uint(vids[PIXEL_WIDTH]) if PIXEL_WIDTH in vids else None,
                height=uint(vids[PIXEL_HEIGHT]) if PIXEL_HEIGHT in vids else None,
            ))
    blocks, clusters = [], []
    for index, cluster in enumerate(find(children, CLUSTER)):
        timestamp = 0
        crc_present, crc_ok = False, None
        first = cluster.children[0].id if cluster.children else None
        count = 0
        for child in cluster.children:
            if child.id == CRC32:
                crc_present = True
                if child.complete and cluster.complete and child.end - child.data_start == 4:
                    stored = struct.unpack("<I", data[child.data_start:child.end])[0]
                    crc_ok = stored == zlib.crc32(data[child.end:cluster.end])
            elif child.id == CLUSTER_TIMESTAMP and child.complete:
                timestamp = uint(child)
            elif child.id in (SIMPLE_BLOCK, BLOCK_GROUP) and child.complete:
                block_element = child if child.id == SIMPLE_BLOCK else next((c for c in child.children if c.id == 0xA1), None)
                if block_element is None:
                    continue
                pos = block_element.data_start
                track, tracklen = read_size(data, pos)
                relative = struct.unpack(">h", data[pos + tracklen:pos + tracklen + 2])[0]
                flags = data[pos + tracklen + 2]
                payload = pos + tracklen + 3
                blocks.append(Block(child.start, child.end, payload, block_element.end - payload, track,
                                    timestamp + relative, bool(flags & 0x80) if child.id == SIMPLE_BLOCK else False,
                                    (flags >> 1) & 0x03, child.id == SIMPLE_BLOCK, index))
                count += 1
        clusters.append(Cluster(cluster.start, cluster.end, cluster.size, cluster.complete, first, crc_present, crc_ok, count))
    return MkvFile(
        length=len(data), doc_type=doc_type,
        segment_unknown_size=bool(segment and segment.size is None),
        segment_data_start=segment.data_start if segment else None,
        timestamp_scale=scale, tracks=tracks, blocks=blocks, clusters=clusters, ids=ids,
        has_cues=bool(find(children, CUES)), cut_at=state["cut"], top=top,
    )


def walk_file(path):
    with open(path, "rb") as handle:
        return walk(handle.read())


def payloads(path):
    """The payload bytes of each complete block of a camera file, in file order."""
    with open(path, "rb") as handle:
        data = handle.read()
    return [data[b.payload_offset:b.payload_offset + b.payload_size] for b in walk(data).blocks]


# ---------------------------------------------------------------------------
# A minimal Matroska writer, for the self-tests of the walker only (no product code)
# ---------------------------------------------------------------------------

def encode_id(eid):
    return eid.to_bytes((eid.bit_length() + 7) // 8, "big")


def encode_size(size, length=None):
    if size is None:
        return b"\x01\xff\xff\xff\xff\xff\xff\xff"
    length = length or next(n for n in range(1, 9) if size < (1 << (7 * n)) - 1)
    return ((1 << (7 * length)) | size).to_bytes(length, "big")


def element(eid, payload):
    return encode_id(eid) + encode_size(len(payload)) + payload


def uint_element(eid, value):
    return element(eid, value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big"))


def build_mkv(frames, *, period_ms=33, unknown_segment=True, crc=True, track=1, default_duration=33333333):
    """A small Matroska file with one block per cluster, as the pinned FFmpeg writes a live file."""
    header = element(EBML, element(DOC_TYPE, b"matroska"))
    info = element(INFO, uint_element(TIMESTAMP_SCALE, 1_000_000))
    tracks = element(TRACKS, element(TRACK_ENTRY, uint_element(TRACK_NUMBER, track) + uint_element(TRACK_TYPE, 1)
                                     + element(CODEC_ID, b"V_MJPEG") + uint_element(DEFAULT_DURATION, default_duration)
                                     + element(VIDEO, uint_element(PIXEL_WIDTH, 64) + uint_element(PIXEL_HEIGHT, 48))))
    body = info + tracks
    for k, frame in enumerate(frames):
        block = encode_size(track, 1) + struct.pack(">h", 0) + b"\x80" + frame
        inner = uint_element(CLUSTER_TIMESTAMP, k * period_ms) + element(SIMPLE_BLOCK, block)
        if crc:
            inner = element(CRC32, struct.pack("<I", zlib.crc32(inner))) + inner
        body += element(CLUSTER, inner)
    segment = encode_id(SEGMENT) + (encode_size(None) if unknown_segment else encode_size(len(body), 8)) + body
    return header + segment
