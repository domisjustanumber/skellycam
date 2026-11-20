// The video timing sidecar (specs/player.md sections 6.4 to 6.8; format spec sections 7 and 8).

export const VIDEO_MARK = '# skellyfileformat=video_timing';

const REQUIRED_KEYS = [
    'skellyfileformat', 'format_version', 'format_prerelease', 'writer', 'take_uuid', 'take_start_host_ns',
    'take_start_utc_ns', 'utc_offset_min', 'clock', 'clock_hz', 'group_size', 'audio_count', 'group_position',
    'camera_key', 'camera_label', 'nominal_rate', 'display_rotation',
];
/** The take keys of SFF-749, from `take_uuid` to `audio_count`. */
export const TAKE_KEYS = ['take_uuid', 'take_start_host_ns', 'take_start_utc_ns', 'utc_offset_min', 'clock', 'clock_hz', 'group_size', 'audio_count'];
const COLUMNS = ['frame', 'source_frame_number', 'arrival_ns', 'sample_ns', 'flags', 'byte_offset', 'byte_size', 'crc32'];
const CLOCKS = new Set(['windows_qpc', 'linux_monotonic', 'macos_uptime_raw', 'synthetic']);
const FLAG = {gap: 1, encode_skip: 4, missing: 16};
const INT = /^(0|-?[1-9][0-9]*)$/;
const TWO_53 = 2n ** 53n;

export type FileState = 'finished' | 'repaired' | 'unfinished' | 'damaged' | 'invalid' | 'unsupported_version';

export interface FitSegment {
    posFirst: number;
    posLast: number;
    t0: bigint;
    periodPs: bigint;
}

export interface Sidecar {
    header: Record<string, string>;
    state: FileState;
    reason: string | null;
    warnings: string[];
    /** The usable rows; empty for a refused file. */
    sfn: (bigint | null)[];
    arrival: (bigint | null)[];
    flags: number[];
    offset: (number | null)[];
    size: (number | null)[];
    tornBytes: number;
    damagedAt: number | null;
    fit: FitSegment[] | null;    // the fit lines of a finished or repaired file, null when there are none
    endLast: boolean;            // the last line is `# end`
}

const CRC_TABLE = Array.from({length: 256}, (_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
});

export function crc32(bytes: Uint8Array, start = 0, end = bytes.length): number {
    let c = 0xffffffff;
    for (let i = start; i < end; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
}

const isInt = (v: string | undefined) => v !== undefined && INT.test(v);
const nonNegative = (v: string) => isInt(v) && !v.startsWith('-') && BigInt(v) < TWO_53;

/** The reason that the header refuses the file, or null (SFF-748 to SFF-753, SFF-772). */
function headerFault(h: Record<string, string>): string | null {
    if (REQUIRED_KEYS.some(k => !(k in h))) return 'missing_metadata';
    const rate = /^([0-9]+)\/([0-9]+)$/.exec(h.nominal_rate);
    const inRate = (v: string) => isInt(v) && Number(v) >= 1 && Number(v) <= 2 ** 20;
    if (!rate || !inRate(rate[1]) || !inRate(rate[2])) return 'bad_rate';
    if (!['0', '90', '180', '270'].includes(h.display_rotation)) return 'bad_rotation';
    if (!/^([0-9a-f]{6,8}|cam(0|[1-9][0-9]*))$/.test(h.camera_label)) return 'bad_label';
    const ok = h.skellyfileformat === 'video_timing' && /^[0-9a-f]{32}$/.test(h.take_uuid) && /^([0-9a-f]{16}|0)$/.test(h.camera_key)
        && CLOCKS.has(h.clock) && (h.clock_hz === '' || nonNegative(h.clock_hz))
        && ['take_start_host_ns', 'take_start_utc_ns', 'utc_offset_min'].every(k => isInt(h[k]))
        && ['format_prerelease', 'group_size', 'audio_count', 'group_position'].every(k => nonNegative(h[k]));
    return ok ? null : 'bad_metadata';
}

/** Read the sidecar bytes of the snapshot. The caller knows that the first line is the video mark. */
export function readSidecar(bytes: Uint8Array): Sidecar {
    const text = new TextDecoder().decode(bytes);
    const out: Sidecar = {
        header: {}, state: 'unfinished', reason: null, warnings: [], sfn: [], arrival: [], flags: [], offset: [], size: [],
        tornBytes: 0, damagedAt: null, fit: null, endLast: false,
    };
    const refuse = (state: FileState, reason: string | null) => {
        out.state = state;
        out.reason = reason;
        out.sfn = out.arrival = out.flags = out.offset = out.size = [];
        out.fit = null;
        return out;
    };
    // lines as byte ranges, so that the CRC and torn_bytes count bytes
    const lines: [number, number][] = [];
    let at = 0;
    for (let i = 0; i < bytes.length; i++) {
        if (bytes[i] === 0x0a) {
            lines.push([at, i]);
            at = i + 1;
        }
    }
    const torn = bytes.length - at;
    const lineText = ([a, b]: [number, number]) => new TextDecoder().decode(bytes.subarray(a, b));

    let li = 0;
    for (; li < lines.length; li++) {
        const s = lineText(lines[li]);
        const m = /^# ([a-z0-9_]+)=(.*)$/.exec(s);
        if (!m) break;
        out.header[m[1]] = m[2];
    }
    if (isInt(out.header.format_prerelease) && Number(out.header.format_prerelease) > 0) out.warnings.push('prerelease');
    const version = /^([0-9]+)\.([0-9]+)$/.exec(out.header.format_version ?? '');
    if (version && Number(version[1]) !== 2) return refuse('unsupported_version', null);
    const fault = headerFault(out.header) ?? (version ? null : 'bad_metadata');
    if (fault) return refuse('invalid', fault);
    if (li >= lines.length) return refuse('invalid', 'missing_metadata');
    const columns = lineText(lines[li++]).split(',');
    const col = Object.fromEntries(COLUMNS.map(c => [c, columns.indexOf(c)]));
    if (COLUMNS.some(c => col[c] < 0)) return refuse('invalid', 'missing_metadata');

    const footer: string[] = [];
    for (; li < lines.length; li++) {
        const [a, b] = lines[li];
        if (bytes[a] === 0x23) break;
        const comma = bytes.lastIndexOf(0x2c, b - 1);
        const fields = lineText([a, b]).split(',');
        const crcOk = comma >= a && fields.length === columns.length
            && crc32(bytes, a, comma).toString(16).padStart(8, '0') === fields[fields.length - 1];
        if (!crcOk) {
            out.state = 'damaged';
            out.reason = 'crc_mismatch';
            out.damagedAt = out.sfn.length;
            break;
        }
        const f = (name: string) => fields[col[name]];
        const flags = f('flags');
        if (!nonNegative(flags)) return refuse('invalid', 'bad_metadata');
        const missing = (Number(flags) & FLAG.missing) !== 0;
        for (const name of ['frame', 'source_frame_number', 'byte_offset', 'byte_size']) {
            const v = f(name);
            const emptyOk = name === 'source_frame_number' || (missing && name !== 'frame');
            if (!(v === '' ? emptyOk : nonNegative(v))) return refuse('invalid', 'bad_metadata');
        }
        for (const name of ['arrival_ns', 'sample_ns']) {
            const v = f(name);
            if (v === '' ? !(missing || name === 'sample_ns') : !isInt(v)) return refuse('invalid', 'bad_metadata');
            if (v !== '' && (BigInt(v) >= TWO_53 || BigInt(v) <= -TWO_53)) return refuse('invalid', 'bad_time');
        }
        if ((f('byte_offset') === '') !== (f('byte_size') === '')) return refuse('invalid', 'bad_metadata');
        out.sfn.push(f('source_frame_number') === '' ? null : BigInt(f('source_frame_number')));
        out.arrival.push(f('arrival_ns') === '' ? null : BigInt(f('arrival_ns')));
        out.flags.push(Number(flags));
        out.offset.push(f('byte_offset') === '' ? null : Number(f('byte_offset')));
        out.size.push(f('byte_size') === '' ? null : Number(f('byte_size')));
    }
    if (out.state !== 'damaged') {
        for (; li < lines.length; li++) footer.push(lineText(lines[li]));
        out.tornBytes = torn;
        const last = footer.at(-1) ?? '';
        out.endLast = torn === 0 && footer.length > 0 && /^# end( |$)/.test(last) && footer.every(l => l.startsWith('#'));
        if (out.endLast) out.state = footer.some(l => /^# repair( |$)/.test(l)) ? 'repaired' : 'finished';
        if (out.endLast) out.fit = readFit(footer);
    }
    if (out.flags.some(v => v & FLAG.gap)) out.warnings.push('gap');
    if (out.flags.some(v => v & FLAG.encode_skip)) out.warnings.push('encode_skip');
    return out;
}

function readFit(footer: string[]): FitSegment[] | null {
    const segments: FitSegment[] = [];
    for (const line of footer) {
        if (!/^# fit_segment( |$)/.test(line)) continue;
        const kv = Object.fromEntries([...line.matchAll(/ ([a-z0-9_]+)=(\S*)/g)].map(m => [m[1], m[2]]));
        if (!['pos_first', 'pos_last', 't0_ns', 'period_ps'].every(k => isInt(kv[k]))) return null;
        segments.push({posFirst: Number(kv.pos_first), posLast: Number(kv.pos_last), t0: BigInt(kv.t0_ns), periodPs: BigInt(kv.period_ps)});
    }
    return segments.length ? segments : null;
}

export const isMissing = (flags: number) => (flags & FLAG.missing) !== 0;
