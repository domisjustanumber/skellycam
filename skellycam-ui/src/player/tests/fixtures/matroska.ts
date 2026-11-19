// The Matroska writer of the fixtures (specs/player.md section 12.2): one V_MJPEG track, one SimpleBlock
// per Cluster. "finished" has known sizes and a Cues tail. "live" is the form that FFmpeg writes while
// the file is live and after a kill (recorder spec 6.3): a Segment of unknown size, and Clusters of known
// size, each with a CRC-32 child first.
import {crc32} from 'node:zlib';

export const ID = {
    EBML: 0x1a45dfa3, EBMLVersion: 0x4286, EBMLReadVersion: 0x42f7, EBMLMaxIDLength: 0x42f2,
    EBMLMaxSizeLength: 0x42f3, DocType: 0x4282, DocTypeVersion: 0x4287, DocTypeReadVersion: 0x4285,
    Segment: 0x18538067, Info: 0x1549a966, TimestampScale: 0x2ad7b1, MuxingApp: 0x4d80, WritingApp: 0x5741,
    Tracks: 0x1654ae6b, TrackEntry: 0xae, TrackNumber: 0xd7, TrackUID: 0x73c5, TrackType: 0x83, CodecID: 0x86,
    DefaultDuration: 0x23e383, Video: 0xe0, PixelWidth: 0xb0, PixelHeight: 0xba,
    Cluster: 0x1f43b675, Timestamp: 0xe7, SimpleBlock: 0xa3, CRC32: 0xbf, Void: 0xec,
    Cues: 0x1c53bb6b, CuePoint: 0xbb, CueTime: 0xb3, CueTrackPositions: 0xb7, CueTrack: 0xf7, CueClusterPosition: 0xf1,
} as const;

export interface MkvBlock {
    payload: Uint8Array;
    ms: number;                   // the container time (SFF-736)
    laced?: boolean;              // set a lacing bit (a defect of T-PLAY-27)
    voidBefore?: boolean;         // a Void element before this Cluster, and one inside it before the block
    unknownSizeCluster?: boolean; // this Cluster has an unknown size
}

export interface MkvOptions {
    width: number;
    height: number;
    rate: [number, number];
    form: 'finished' | 'live';
    sizeLength?: number;          // the length of each known element size (8 for T-PLAY-25), else the shortest
    trackNumberLength?: 1 | 2;    // the length of the track number in the block header
    noMagic?: boolean;            // T-PLAY-28: the first 4 bytes are not the EBML magic
}

export interface MkvResult {
    bytes: Uint8Array;
    payloads: {offset: number; size: number}[];   // one for each block, in file order
}

type Node = {id: number; data?: Uint8Array; children?: Node[]; unknownSize?: boolean; crc?: boolean; mark?: number};
type Out = {bytes: Uint8Array; marks: Map<number, number>};   // mark -> offset of the data of the marked node

function idBytes(id: number): number[] {
    const out: number[] = [];
    for (let v = id; v > 0; v = Math.floor(v / 256)) out.unshift(v & 0xff);
    return out;
}

function sizeBytes(size: number | null, forced?: number): number[] {
    if (size === null) return [0x01, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff];
    let len = forced ?? 1;
    while (!forced && size >= 2 ** (7 * len) - 1) len++;
    const out = new Array(len).fill(0);
    let v = size;
    for (let i = len - 1; i >= 0; i--, v = Math.floor(v / 256)) out[i] = v % 256;
    out[0] |= 1 << (8 - len);
    return out;
}

function uintBytes(v: number): number[] {
    const out: number[] = [];
    let x = v;
    do {
        out.unshift(x % 256);
        x = Math.floor(x / 256);
    } while (x > 0);
    return out;
}

const uint = (id: number, v: number): Node => ({id, data: Uint8Array.from(uintBytes(v))});
const str = (id: number, s: string): Node => ({id, data: Uint8Array.from(s, c => c.charCodeAt(0))});
const concat = (parts: Uint8Array[]) => new Uint8Array(Buffer.concat(parts));

function serialise(n: Node, forced?: number): Out {
    const parts: Uint8Array[] = [];
    let length = 0;
    const marks = new Map<number, number>();
    if (n.children) {
        for (const c of n.children) {
            const o = serialise(c, forced);
            for (const [m, off] of o.marks) marks.set(m, length + off);
            parts.push(o.bytes);
            length += o.bytes.length;
        }
    } else {
        parts.push(n.data!);
        length = n.data!.length;
    }
    if (n.crc) {
        const c = crc32(concat(parts)) >>> 0;
        const crcEl = Uint8Array.from([ID.CRC32, 0x84, c & 0xff, (c >>> 8) & 0xff, (c >>> 16) & 0xff, (c >>> 24) & 0xff]);
        for (const [m, off] of marks) marks.set(m, off + crcEl.length);
        parts.unshift(crcEl);
        length += crcEl.length;
    }
    const head = Uint8Array.from([...idBytes(n.id), ...sizeBytes(n.unknownSize ? null : length, n.unknownSize ? undefined : forced)]);
    for (const [m, off] of marks) marks.set(m, off + head.length);
    if (n.mark !== undefined) marks.set(n.mark, head.length);
    return {bytes: concat([head, ...parts]), marks};
}

export function writeMkv(blocks: MkvBlock[], options: MkvOptions): MkvResult {
    const [num, den] = options.rate;
    const forced = options.sizeLength;
    const live = options.form === 'live';
    const track = options.trackNumberLength === 2 ? [0x40, 0x01] : [0x81];
    const header: Node = {id: ID.EBML, children: [
        uint(ID.EBMLVersion, 1), uint(ID.EBMLReadVersion, 1), uint(ID.EBMLMaxIDLength, 4),
        uint(ID.EBMLMaxSizeLength, 8), str(ID.DocType, 'matroska'), uint(ID.DocTypeVersion, 4),
        uint(ID.DocTypeReadVersion, 2),
    ]};
    const children: Node[] = [
        {id: ID.Info, children: [uint(ID.TimestampScale, 1_000_000), str(ID.MuxingApp, 'fixture'), str(ID.WritingApp, 'fixture')]},
        {id: ID.Tracks, children: [{id: ID.TrackEntry, children: [
            uint(ID.TrackNumber, 1), uint(ID.TrackUID, 1), uint(ID.TrackType, 1), str(ID.CodecID, 'V_MJPEG'),
            uint(ID.DefaultDuration, Math.floor((1e9 * den) / num)),
            {id: ID.Video, children: [uint(ID.PixelWidth, options.width), uint(ID.PixelHeight, options.height)]},
        ]}]},
    ];
    const clusterIndex = new Set<number>();
    blocks.forEach((b, i) => {
        const inner: Node[] = [uint(ID.Timestamp, b.ms)];
        if (b.voidBefore) {
            children.push({id: ID.Void, data: new Uint8Array(5)});
            inner.push({id: ID.Void, data: new Uint8Array(3)});
        }
        // the mark is the offset of the SimpleBlock data: the payload starts after the block header
        inner.push({id: ID.SimpleBlock, data: concat([Uint8Array.from([...track, 0, 0, 0x80 | (b.laced ? 0x06 : 0)]), b.payload]), mark: i});
        clusterIndex.add(children.length);
        children.push({id: ID.Cluster, children: inner, unknownSize: !!b.unknownSizeCluster, crc: live && !b.unknownSizeCluster});
    });
    const build = (cues: Node | null) => ({
        h: serialise(header, forced),
        s: serialise({id: ID.Segment, children: cues ? [...children, cues] : children, unknownSize: live}, forced),
    });
    let cues: Node | null = null;
    if (!live) {
        // Cue positions are relative to the start of the Segment data; each child offset comes from a
        // serialise of the children before it.
        let pos = 0;
        const clusterPos: number[] = [];
        children.forEach((c, i) => {
            if (clusterIndex.has(i)) clusterPos.push(pos);
            pos += serialise(c, forced).bytes.length;
        });
        cues = {id: ID.Cues, children: clusterPos.map((p, i) => ({id: ID.CuePoint, children: [
            uint(ID.CueTime, blocks[i].ms),
            {id: ID.CueTrackPositions, children: [uint(ID.CueTrack, 1), uint(ID.CueClusterPosition, p)]},
        ]}))};
    }
    const {h, s} = build(cues);
    const bytes = concat([h.bytes, s.bytes]);
    const payloads = blocks.map((b, i) => ({offset: h.bytes.length + s.marks.get(i)! + track.length + 3, size: b.payload.length}));
    if (options.noMagic) bytes.set([0x00, 0x00, 0x00, 0x00], 0);
    return {bytes, payloads};
}
