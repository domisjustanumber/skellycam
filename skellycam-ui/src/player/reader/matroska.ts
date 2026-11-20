// The camera file: the head, the tail and the block check of a frame read (specs/player.md sections
// 6.9 and 6.10; SFF-739, SFF-740, SFF-759). The walk enters the Segment and each Cluster, known or
// unknown size, and skips each other element of known size.
import type {TakeFiles} from '../files/take-files.ts';

export const EBML_MAGIC = [0x1a, 0x45, 0xdf, 0xa3];
const ID = {EBML: 0x1a45dfa3, DocType: 0x4282, Segment: 0x18538067, Cluster: 0x1f43b675, Tracks: 0x1654ae6b,
    TrackEntry: 0xae, TrackNumber: 0xd7, TrackType: 0x83, SimpleBlock: 0xa3, BlockGroup: 0xa0};
const CONTAINERS = new Set([ID.Segment, ID.Cluster]);
const HEAD_STEP = 64 * 1024;
const TAIL_STEP = 1024 * 1024;

export class BlockMismatch extends Error {}

interface Element {
    id: number;
    size: number | null;   // null: unknown size
    data: number;          // the offset of the data in the buffer
}

/** One element header at `at`, or null when the buffer ends inside it. */
function element(b: Uint8Array, at: number): Element | null {
    if (at >= b.length) return null;
    const idLen = Math.clz32(b[at]) - 23;
    if (idLen < 1 || idLen > 4) bad();
    if (at + idLen >= b.length) return null;
    let id = 0;
    for (let i = 0; i < idLen; i++) id = id * 256 + b[at + i];
    const s = at + idLen;
    const sizeLen = Math.clz32(b[s]) - 23;
    if (sizeLen < 1 || sizeLen > 8) return bad();
    if (s + sizeLen > b.length) return null;
    let size = b[s] & (0xff >> sizeLen);
    let allOnes = size === 0xff >> sizeLen;
    for (let i = 1; i < sizeLen; i++) {
        size = size * 256 + b[s + i];
        if (b[s + i] !== 0xff) allOnes = false;
    }
    return {id, size: allOnes ? null : size, data: s + sizeLen};
}

function bad(): never {
    throw new BlockMismatch('malformed element');
}

function uint(b: Uint8Array, at: number, len: number): number {
    let v = 0;
    for (let i = 0; i < len; i++) v = v * 256 + b[at + i];
    return v;
}

export interface Head {
    videoTrack: number;
    firstCluster: number;   // the file offset of the first Cluster, or the snapshot size
}

/** Read the head: EBML header with DocType `matroska`, one Segment, the Tracks, the first Cluster. */
export async function readHead(files: TakeFiles, path: string, size: number): Promise<Head> {
    let end = Math.min(size, HEAD_STEP);
    for (;;) {
        const b = await files.readRange(path, 0, end);
        const head = parseHead(b, end === size);
        if (head) return head;
        if (end === size) throw new BlockMismatch('no Tracks element');
        end = Math.min(size, end + HEAD_STEP);
    }
}

function parseHead(b: Uint8Array, whole: boolean): Head | null {
    const ebml = element(b, 0);
    if (!ebml || ebml.id !== ID.EBML || ebml.size === null) return whole ? bad() : null;
    let docType = '';
    for (let at = ebml.data; at < ebml.data + ebml.size;) {
        const e = element(b, at);
        if (!e || e.size === null) return whole ? bad() : null;
        if (e.id === ID.DocType) docType = new TextDecoder().decode(b.subarray(e.data, e.data + e.size)).replace(/\0+$/, '');
        at = e.data + e.size;
    }
    if (docType !== 'matroska') bad();
    const seg = element(b, ebml.data + ebml.size);
    if (!seg) return whole ? bad() : null;
    if (seg.id !== ID.Segment) bad();
    let videoTrack: number | null = null;
    let at = seg.data;
    for (;;) {
        const e = element(b, at);
        if (!e) return whole && videoTrack !== null ? {videoTrack, firstCluster: b.length} : whole ? bad() : null;
        if (e.id === ID.Cluster) return videoTrack === null ? bad() : {videoTrack, firstCluster: at};
        if (e.size === null) bad();
        if (e.data + e.size > b.length) return whole ? bad() : null;
        if (e.id === ID.Tracks) videoTrack = videoTrackOf(b, e.data, e.data + e.size);
        at = e.data + e.size;
    }
}

function videoTrackOf(b: Uint8Array, from: number, to: number): number {
    let first: number | null = null;
    for (let at = from; at < to;) {
        const entry = element(b, at) ?? bad();
        if (entry.size === null) bad();
        if (entry.id === ID.TrackEntry) {
            let number: number | null = null;
            let type: number | null = null;
            for (let i = entry.data; i < entry.data + entry.size;) {
                const e = element(b, i) ?? bad();
                if (e.size === null) bad();
                if (e.id === ID.TrackNumber) number = uint(b, e.data, e.size);
                if (e.id === ID.TrackType) type = uint(b, e.data, e.size);
                i = e.data + e.size;
            }
            if (number !== null && type === 1) return number;
            first ??= number;
        }
        at = entry.data + entry.size;
    }
    return first ?? bad();
}

/**
 * Walk a range that starts at the end of the block of the row before the first row (or at the first
 * Cluster) and check that each block is the next expected block: the video track, no lacing, the
 * payload at `byte_offset` with `byte_size` bytes. Gives the payload of each expected block.
 */
export function walkBlocks(b: Uint8Array, rangeStart: number, videoTrack: number, expected: {offset: number; size: number}[]): Uint8Array[] {
    const out: Uint8Array[] = [];
    let at = 0;
    while (out.length < expected.length) {
        const e = element(b, at) ?? bad();
        if (CONTAINERS.has(e.id)) {
            at = e.data;
            continue;
        }
        if (e.size === null) bad();
        if (e.id === ID.SimpleBlock) {
            const want = expected[out.length];
            const trackLen = Math.clz32(b[e.data]) - 23;
            if (trackLen < 1 || trackLen > 8) bad();
            const track = uint(b, e.data, trackLen) - 2 ** (7 * trackLen);   // the vint value: the marker bit off
            const flags = b[e.data + trackLen + 2];
            const payload = e.data + trackLen + 3;
            const length = e.size - trackLen - 3;
            if (track !== videoTrack || (flags & 0x06) !== 0 || rangeStart + payload !== want.offset || length !== want.size) {
                throw new BlockMismatch(`the block at ${rangeStart + at} is not the block of its row`);
            }
            out.push(b.subarray(payload, payload + length));
        }
        at = e.data + e.size;
    }
    return out;
}

/** SFF-759 at the open: no block after the last block that a row points at. */
export async function checkTail(files: TakeFiles, path: string, from: number, size: number): Promise<void> {
    let at = from;
    while (at < size) {
        const end = Math.min(size, at + TAIL_STEP);
        const b = await files.readRange(path, at, end);
        let i = 0;
        let e: Element | null;
        while (i < b.length && (e = element(b, i))) {
            if (e.id === ID.SimpleBlock || e.id === ID.BlockGroup) throw new BlockMismatch('a block after the last row');
            if (CONTAINERS.has(e.id)) i = e.data;
            else if (e.size === null) return;
            else i = e.data + e.size;
        }
        // an element cut by the snapshot end, or by a repair, ends the walk
        if (i < b.length && end === size) return;
        at += i;
    }
}
