"""The completion of a short camera pair by the take level (specs/recorder.md, section 7.4).

It runs only after the camera's process was joined, or after its result says `files_closed`.
"""
import mmap
import os
import zlib

from skellycam.core.take_recorder import sidecar

SEGMENT, CLUSTER, SIMPLE_BLOCK, CRC32 = 0x18538067, 0x1F43B675, 0xA3, 0xBF


def _element(data, pos):
    """The ID, the data start and the data size (None for the unknown size) of the element at `pos`.
    IndexError when the element header is cut."""
    first = data[pos]
    id_length = next(n for n in range(1, 5) if first & (0x80 >> (n - 1)))
    eid = int.from_bytes(data[pos:pos + id_length], "big")
    pos += id_length
    first = data[pos]
    size_length = next(n for n in range(1, 9) if first & (0x80 >> (n - 1)))
    if pos + size_length > len(data):
        raise IndexError
    size = int.from_bytes(data[pos:pos + size_length], "big") & ((1 << (7 * size_length)) - 1)
    return eid, pos + size_length, None if size == (1 << (7 * size_length)) - 1 else size


def complete_blocks(data: bytes | mmap.mmap) -> tuple[list, int]:
    """Walk the Segment (SFF-740). Returns the end offset of each complete SimpleBlock, in file order,
    and the offset of the first Cluster (or of the end of the walk when the file has no Cluster)."""
    try:
        _, start, size = _element(data, 0)  # the EBML header
        eid, pos, size = _element(data, start + size)
    except (IndexError, StopIteration, TypeError):
        return [], len(data)  # the header is cut: the process ended in `start`; nothing to cut
    if eid != SEGMENT:
        raise ValueError("no Segment after the EBML header")
    end = len(data) if size is None else min(len(data), pos + size)
    blocks, first_cluster = [], None
    while pos < end:
        try:
            eid, data_start, size = _element(data, pos)
        except (IndexError, StopIteration):
            break
        # shortcut: an element of unknown size ends the walk; the pinned FFmpeg writes each Cluster
        # with its size (6.3). Step 5c walks such elements when it repairs files of other writers.
        if size is None or data_start + size > len(data):
            if eid == CLUSTER and first_cluster is None:
                first_cluster = pos
            break
        if eid == CLUSTER:
            first_cluster = pos if first_cluster is None else first_cluster
            found = _cluster_blocks(data, data_start, data_start + size)
            if found is None:
                break  # a damaged cluster: keep the blocks before it
            blocks += found
        pos = data_start + size
    return blocks, pos if first_cluster is None else first_cluster


def _cluster_blocks(data, start, end):
    """The end offsets of the SimpleBlocks of one complete Cluster, or None when its CRC-32 is wrong
    or a child does not parse."""
    found = []
    try:
        while start < end:
            eid, child_start, size = _element(data, start)
            child_end = child_start + size
            crc_wrong = eid == CRC32 and int.from_bytes(data[child_start:child_end], "little") != zlib.crc32(data[child_end:end])
            if child_end > end or crc_wrong:
                return None
            if eid == SIMPLE_BLOCK:
                found.append(child_end)
            start = child_end
    except (IndexError, StopIteration, TypeError):
        return None
    return found


def _walk_file(mkv_path):
    """complete_blocks of the file, read through a map so that memory does not grow with the file.
    Returns (block ends, first Cluster, file size); the size is 0 for a missing or empty file."""
    try:
        with open(mkv_path, "rb") as handle:
            size = os.fstat(handle.fileno()).st_size
            if not size:
                return [], 0, 0
            with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:  # closed before any cut
                blocks, first_cluster = complete_blocks(data)
    except FileNotFoundError:
        return [], 0, 0
    return blocks, first_cluster, size


def complete_pair(mkv_path, csv_path, frame_count: int, writer: str, header) -> int | None:
    """Complete a pair whose sidecar has no `# end` line. Returns n, the blocks kept, or None when the
    sidecar ended normally. A sidecar with no usable header (the process ended in `start`) is written
    again from `header`, the (key, value) pairs of 6.5, with `missing` rows only."""
    try:
        csv = sidecar.read_strict(csv_path)
    except (FileNotFoundError, ValueError):
        csv = None
    if csv is not None and csv.has_end:
        if b"\n# repair " not in csv.data:
            return None
        return sum(1 for r in csv.rows if r.byte_offset is not None)  # an earlier `finish` completed it
    blocks, first_cluster, media_size = _walk_file(mkv_path)
    kept = [] if csv is None else csv.rows
    n = min(len(kept), len(blocks))  # SFF-795: the first n rows and the first n blocks
    media_cut = blocks[n - 1] if n else first_cluster
    if media_cut < media_size:
        with open(mkv_path, "r+b") as handle:  # cut after block n - 1; no byte before it changes, nothing is appended
            handle.truncate(media_cut)
            os.fsync(handle.fileno())
    missing_rows = [sidecar.Row(k, None, None, None, sidecar.MISSING, None, None) for k in range(n, frame_count)]
    rows = kept[:n] + missing_rows
    gaps, missing = sidecar.counts(rows)
    if csv is None:
        old_size = csv_path.stat().st_size if csv_path.exists() else 0
        lines = [sidecar.header_line(key, value) for key, value in header] + [sidecar.COLUMN_LINE]
        csv_cut, mode = 0, "wb"
    else:
        old_size, lines, csv_cut, mode = len(csv.data), [], csv.ends[n - 1] if n else csv.header_end, "r+b"
    lines += [sidecar.row_line(row) for row in missing_rows]
    lines.append(f"# repair cut_bytes={old_size - csv_cut} media_cut_bytes={media_size - min(media_cut, media_size)} "
                 f"repair_writer={writer}\n".encode())
    lines.append(sidecar.end_line(len(rows), gaps, missing))
    with open(csv_path, mode) as handle:
        handle.truncate(csv_cut)
        handle.seek(csv_cut)
        for line in lines:
            handle.write(line)
        os.fsync(handle.fileno())
    return n
