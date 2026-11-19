// The video timing sidecar of the fixtures: sections 7 and 8 of the format spec, with the flag
// `missing` (bit 4) and `missing=` in the `# end` line (F-1 of the recorder spec).
import {crc32} from 'node:zlib';

export const HEADER_KEYS = [
    'skellyfileformat', 'format_version', 'format_prerelease', 'writer', 'take_uuid', 'take_start_host_ns',
    'take_start_utc_ns', 'utc_offset_min', 'clock', 'clock_hz', 'group_size', 'audio_count', 'group_position',
    'camera_key', 'camera_label', 'nominal_rate', 'display_rotation',
] as const;

export const COLUMNS = ['frame', 'source_frame_number', 'arrival_ns', 'sample_ns', 'flags', 'byte_offset', 'byte_size', 'crc32'];

export const FLAG = {gap: 1, filled: 2, encode_skip: 4, repeat: 8, missing: 16} as const;

export function crcHex(text: string): string {
    return (crc32(Buffer.from(text, 'utf8')) >>> 0).toString(16).padStart(8, '0');
}

/** A data row: the fields before `crc32`, by column name. The CRC is computed unless `badCrc`. */
export function rowLine(columns: string[], fields: Record<string, string>, badCrc = false): string {
    const body = columns.slice(0, -1).map(c => fields[c] ?? '').join(',');
    let crc = crcHex(body);
    if (badCrc) crc = ((parseInt(crc, 16) ^ 1) >>> 0).toString(16).padStart(8, '0');
    return `${body},${crc}\n`;
}

export function headerLines(values: Record<string, string>, order: readonly string[] = HEADER_KEYS): string {
    return order.filter(k => k in values).map(k => `# ${k}=${values[k]}\n`).join('');
}
