// The take builder (specs/player.md section 12.2). A plan is plain data; `writeTake` writes it into a
// folder from the format rules, with no recorder code. Tests change a plan before they write it.
import {mkdirSync, writeFileSync, rmSync} from 'node:fs';
import path from 'node:path';
import {crc32} from 'node:zlib';
import {barcodeJpeg, insertDht, placeholderFor, IMAGE_HEIGHT, IMAGE_WIDTH} from './jpeg.ts';
import type {JpegOptions, Sampling} from './jpeg.ts';
import {writeMkv} from './matroska.ts';
import type {MkvBlock} from './matroska.ts';
import {COLUMNS, FLAG, HEADER_KEYS, headerLines, rowLine} from './sidecar.ts';

export const MEDIA = 'synchronized_videos';
export const NS_PER_FRAME_30 = 33_333_333n;

export interface RowPlan {
    kind: 'real' | 'missing' | 'missing_noblock';
    sfn: bigint | null;
    arrival: bigint | null;
    sample?: bigint | null;
    flags?: number;                          // bits other than `missing`; `missing` is added from `kind`
    frameValue?: string;                     // a `frame` field that is not the position (T-PLAY-16)
    fields?: Record<string, string>;         // raw field overrides, for example an out-of-range integer
    badCrc?: boolean;
    jpeg?: JpegOptions & {insertDht?: boolean};
    payload?: Uint8Array;                    // a payload of the caller (the benchmarks)
    offsetDelta?: number;                    // the CSV `byte_offset` is wrong by this (T-PLAY-27)
    laced?: boolean;
    voidBefore?: boolean;
    unknownSizeCluster?: boolean;
    extraBlockAfter?: boolean;               // a block with no row after the block of this row
}

export interface FitSegment {
    posFirst: number;
    posLast: number;
    t0: bigint;
    periodPs: bigint;
}

export interface CameraPlan {
    index: number;                           // the camera index of the barcode
    label: string;
    key: string;
    position: number;
    rate: [number, number];
    rotation: string;
    sampling: Sampling;
    rows: RowPlan[];
    fit: FitSegment[] | null;
    fitter: string;
    footer: {repair: boolean; end: boolean; rowsAfterEnd?: number; torn?: string};
    header: Record<string, string | null>;   // overrides of the header values; null leaves a key out
    extraHeader?: string[];                  // more header lines, after the last key
    columns?: string[];                      // a changed column line
    mkv: {form: 'finished' | 'live'; sizeLength?: number; trackNumberLength?: 1 | 2; noMagic?: boolean;
          cutInBlock?: number; extraBlockAtEnd?: boolean};
    stem?: string;                           // the file name stem, default `<rec>.<label>`
    noMkv?: boolean;
    noCsv?: boolean;
    firstLine?: string;                      // replace the mark line (a sidecar with no mark)
}

export interface WarningPlan {
    code: string;
    camera: number | null;                   // an index into `cameras`
    detail: string | null;
}

export interface TakePlan {
    name: string;
    rec: string;
    takeUuid: string;
    takeStartHost: bigint;
    groupSize: number;
    cameras: CameraPlan[];
    manifest: 'finished' | 'recording' | 'missing' | 'not_json' | 'not_manifest' | 'other_uuid';
    warnings: WarningPlan[];
    manifestVideo?: (cam: CameraPlan, i: number) => {video: string; timing: string};
    deleteAfter?: string[];
    extraFiles?: {path: string; content: Uint8Array | string}[];
}

export interface BuiltCamera {
    plan: CameraPlan;
    mkv: string;                             // relative paths with `/`
    csv: string;
    payloads: (Uint8Array | null)[];         // the block payload of each row, null when the row has no block
    blocks: ({offset: number; size: number} | null)[];
    placeholder: Uint8Array;
    mkvSize: number;
    csvSize: number;
    blockPayloadEnds: number[];              // the payload end of each block in file order, extra blocks included
}

export interface Identity {
    camera: number;
    row: number | null;                      // null for a placeholder
    placeholder: boolean;
}

export interface BuiltTake {
    plan: TakePlan;
    dir: string;
    cameras: BuiltCamera[];
    identify(jpeg: Uint8Array | null | undefined): Identity | null;
}

const keyOf = (b: Uint8Array) => `${b.length}:${crc32(b) >>> 0}`;

export function msOf(k: number, [num, den]: [number, number]): number {
    return Math.floor((2 * k * den * 1000 + num) / (2 * num));
}

export function defaultCamera(index: number, rows = 120, offsetNs = 0n): CameraPlan {
    const key = (0xa1b2c3 + index * 0x010101).toString(16) + '0123456789';
    const start = 10_000_000n + offsetNs;
    const rowPlans: RowPlan[] = [];
    for (let k = 0; k < rows; k++) {
        const jitter = BigInt(((index * 7919 + k * 104729) % 2001) - 1000);
        rowPlans.push({kind: 'real', sfn: 1000n + BigInt(k), arrival: start + BigInt(k) * NS_PER_FRAME_30 + jitter});
    }
    return {
        index, key, label: key.slice(0, 6), position: index, rate: [30, 1], rotation: '0', sampling: '422',
        rows: rowPlans, fit: [{posFirst: 0, posLast: rows - 1, t0: start, periodPs: 33_333_333_333n}],
        fitter: 'fixture', footer: {repair: false, end: true}, header: {}, mkv: {form: 'finished'},
    };
}

export function defaultTake(name: string, cameraCount = 4, rows = 120): TakePlan {
    const cameras = Array.from({length: cameraCount}, (_, i) => defaultCamera(i, rows));
    return {
        name, rec: `take_${name}`, takeUuid: '6f1c2c1e1d7e4c479a3e2f2b3c4d5e6f', takeStartHost: 123_456_789_000n,
        groupSize: cameraCount, cameras, manifest: 'finished', warnings: [],
    };
}

export function camByIndex(plan: TakePlan, index: number): CameraPlan {
    const c = plan.cameras.find(c => c.index === index);
    if (!c) throw new Error(`no camera ${index}`);
    return c;
}

/** Make rows `from` to `to` (inclusive) of a camera `missing`. With `keepTimes` false the times go. */
export function markMissing(cam: CameraPlan, from: number, to: number, keepTimes: boolean, kind: 'missing' | 'missing_noblock' = 'missing'): void {
    for (let k = from; k <= to; k++) {
        const r = cam.rows[k];
        cam.rows[k] = keepTimes ? {...r, kind} : {kind, sfn: null, arrival: null, sample: null};
    }
}

function fmt(v: bigint | null | undefined): string {
    return v === null || v === undefined ? '' : v.toString();
}

function headerValues(plan: TakePlan, cam: CameraPlan): Record<string, string> {
    const v: Record<string, string> = {
        skellyfileformat: 'video_timing', format_version: '2.0', format_prerelease: '1', writer: 'fixture 1.0.0',
        take_uuid: plan.takeUuid, take_start_host_ns: plan.takeStartHost.toString(),
        take_start_utc_ns: '1795000000000000000', utc_offset_min: '0', clock: 'windows_qpc', clock_hz: '',
        group_size: String(plan.groupSize), audio_count: '0', group_position: String(cam.position),
        camera_key: cam.key, camera_label: cam.label, nominal_rate: `${cam.rate[0]}/${cam.rate[1]}`,
        display_rotation: cam.rotation,
    };
    for (const [k, val] of Object.entries(cam.header)) {
        if (val === null) delete v[k];
        else v[k] = val;
    }
    return v;
}

function writeFile(dir: string, rel: string, content: Uint8Array | string): void {
    const full = path.join(dir, ...rel.split('/'));
    mkdirSync(path.dirname(full), {recursive: true});
    writeFileSync(full, content);
}

export function stemOf(plan: TakePlan, cam: CameraPlan): string {
    return cam.stem ?? `${plan.rec}.${cam.label}`;
}

export function writeTake(root: string, plan: TakePlan): BuiltTake {
    const dir = path.join(root, plan.name);
    mkdirSync(path.join(dir, MEDIA), {recursive: true});
    const ids = new Map<string, Identity>();
    const cameras: BuiltCamera[] = plan.cameras.map(cam => {
        const stem = stemOf(plan, cam);
        const payloadOf = (r: RowPlan, k: number) => {
            if (r.payload) return r.payload;
            const j = barcodeJpeg(cam.index, k, cam.sampling, r.jpeg ?? {});
            return r.jpeg?.insertDht ? insertDht(j) : j;
        };
        const firstReal = cam.rows.findIndex(r => r.kind === 'real');
        const placeholder = placeholderFor(firstReal >= 0 ? payloadOf(cam.rows[firstReal], firstReal) : barcodeJpeg(cam.index, 0, cam.sampling));
        ids.set(keyOf(placeholder), {camera: cam.index, row: null, placeholder: true});
        const payloads = cam.rows.map((r, k) => {
            if (r.kind === 'missing_noblock') return null;
            if (r.kind === 'missing') return placeholder;
            const p = payloadOf(r, k);
            ids.set(keyOf(p), {camera: cam.index, row: k, placeholder: false});
            return p;
        });
        // blocks in file order, with the extra blocks of T-PLAY-27
        const mkvBlocks: MkvBlock[] = [];
        const rowBlock: (number | null)[] = [];
        cam.rows.forEach((r, k) => {
            const p = payloads[k];
            if (!p) {
                rowBlock.push(null);
                return;
            }
            rowBlock.push(mkvBlocks.length);
            mkvBlocks.push({payload: p, ms: msOf(k, cam.rate), laced: r.laced, voidBefore: r.voidBefore, unknownSizeCluster: r.unknownSizeCluster});
            if (r.extraBlockAfter) mkvBlocks.push({payload: barcodeJpeg(cam.index, 4000, cam.sampling), ms: msOf(k, cam.rate)});
        });
        if (cam.mkv.extraBlockAtEnd) mkvBlocks.push({payload: barcodeJpeg(cam.index, 4001, cam.sampling), ms: msOf(cam.rows.length, cam.rate)});
        const mkv = writeMkv(mkvBlocks, {
            width: IMAGE_WIDTH, height: IMAGE_HEIGHT, rate: cam.rate, form: cam.mkv.form, sizeLength: cam.mkv.sizeLength,
            trackNumberLength: cam.mkv.trackNumberLength, noMagic: cam.mkv.noMagic,
        });
        let mkvBytes = mkv.bytes;
        if (cam.mkv.cutInBlock !== undefined) {
            const b = mkv.payloads[cam.mkv.cutInBlock];
            mkvBytes = mkvBytes.subarray(0, b.offset + Math.floor(b.size / 2));
        }
        const blocks = rowBlock.map(i => (i === null ? null : mkv.payloads[i]));

        const columns = cam.columns ?? COLUMNS;
        let csv = cam.firstLine !== undefined ? cam.firstLine + '\n' : '';
        const values = headerValues(plan, cam);
        csv += headerLines(values, cam.firstLine !== undefined ? HEADER_KEYS.slice(1) : HEADER_KEYS);
        for (const line of cam.extraHeader ?? []) csv += line + '\n';
        csv += columns.join(',') + '\n';
        const rowText = (r: RowPlan, k: number) => {
            const b = blocks[k];
            const fields: Record<string, string> = {
                frame: r.frameValue ?? String(k), source_frame_number: fmt(r.sfn), arrival_ns: fmt(r.arrival),
                sample_ns: fmt(r.sample), flags: String((r.flags ?? 0) | (r.kind === 'real' ? 0 : FLAG.missing)),
                byte_offset: b ? String(b.offset + (r.offsetDelta ?? 0)) : '', byte_size: b ? String(b.size) : '',
                future_col: 'x', ...r.fields,
            };
            return rowLine(columns, fields, r.badCrc);
        };
        const rowsAfterEnd = cam.footer.rowsAfterEnd ?? 0;
        const mainRows = cam.rows.slice(0, cam.rows.length - rowsAfterEnd);
        mainRows.forEach((r, k) => (csv += rowText(r, k)));
        if (cam.fit) {
            csv += `# fit fitter=${cam.fitter} fitter_version=1.0.0 fitter_params={"window":5}\n`;
            for (const s of cam.fit) csv += `# fit_segment pos_first=${s.posFirst} pos_last=${s.posLast} t0_ns=${s.t0} period_ps=${s.periodPs}\n`;
        }
        if (cam.footer.repair) csv += '# repair cut_bytes=0 media_cut_bytes=0 repair_writer=fixture 1.0.0\n';
        if (cam.footer.end) {
            const count = (bit: number) => mainRows.filter(r => (r.flags ?? 0) & bit).length;
            const missing = mainRows.filter(r => r.kind !== 'real').length;
            csv += `# end rows=${mainRows.length} gaps=${count(FLAG.gap)} filled=0 missing=${missing} encode_skips=${count(FLAG.encode_skip)}\n`;
        }
        cam.rows.slice(cam.rows.length - rowsAfterEnd).forEach((r, j) => (csv += rowText(r, mainRows.length + j)));
        if (cam.footer.torn) csv += cam.footer.torn;
        const mkvRel = `${MEDIA}/${stem}.mkv`;
        const csvRel = `${MEDIA}/${stem}.csv`;
        if (!cam.noMkv) writeFile(dir, mkvRel, mkvBytes);
        if (!cam.noCsv) writeFile(dir, csvRel, csv);
        return {
            plan: cam, mkv: mkvRel, csv: csvRel, payloads, blocks, placeholder, mkvSize: mkvBytes.length,
            csvSize: Buffer.byteLength(csv), blockPayloadEnds: mkv.payloads.map(p => p.offset + p.size),
        };
    });
    if (plan.manifest !== 'missing') writeFile(dir, 'recording_manifest.json', manifestText(plan));
    for (const f of plan.extraFiles ?? []) writeFile(dir, f.path, f.content);
    for (const rel of plan.deleteAfter ?? []) rmSync(path.join(dir, ...rel.split('/')), {force: true});
    return {
        plan, dir, cameras,
        identify: jpeg => (jpeg ? ids.get(keyOf(jpeg)) ?? null : null),
    };
}

export function manifestText(plan: TakePlan): string {
    if (plan.manifest === 'not_json') return '{"skellyfileformat": "recording_manifest", ';
    if (plan.manifest === 'not_manifest') return JSON.stringify({skellyfileformat: 'capture_info', format_version: '2.0'}, null, 2) + '\n';
    const takeUuid = plan.manifest === 'other_uuid' ? 'ffffffffffffffffffffffffffffffff' : plan.takeUuid;
    const m = {
        skellyfileformat: 'recording_manifest', format_version: '2.0', format_prerelease: 1, writer: 'fixture 1.0.0',
        take_uuid: takeUuid, recording_name: plan.rec, purpose: 'motion_capture',
        state: plan.manifest === 'recording' ? 'recording' : 'finished',
        cameras: plan.cameras.filter(c => !c.noCsv || !c.noMkv).map((c, i) => ({
            camera_key: c.key, camera_label: c.label, group_position: c.position,
            ...(plan.manifestVideo ? plan.manifestVideo(c, i) : {video: `${MEDIA}/${stemOf(plan, c)}.mkv`, timing: `${MEDIA}/${stemOf(plan, c)}.csv`}),
            calibration_camera: null,
        })),
        audio: null, calibration: null, files: [],
        warnings: plan.warnings.map(w => ({
            code: w.code, source: 'skellycam', camera_key: w.camera === null ? null : camByIndex(plan, w.camera).key, detail: w.detail,
        })),
        privacy: {fields: ['/recording_name'], media_shows_people: true},
        summary: {
            take_start_utc: '2026-11-19T12:00:00Z', duration_s: null, cameras: [], audio: null, calibration: null,
            processing_runs: [], warnings: [...new Set(plan.warnings.map(w => w.code))].sort(),
        },
    };
    return JSON.stringify(m, null, 2) + '\n';
}

/** The player time of each row by SFF-781 and SFF-777, as a test reference: fitted or arrival. */
export function referenceTimes(cam: CameraPlan): (bigint | null)[] {
    const finished = cam.footer.end && !cam.footer.rowsAfterEnd && !cam.footer.torn;
    const fit = finished && cam.fit && holdsEachPosition(cam.fit, cam.rows.length) ? cam.fit : null;
    if (!fit) return cam.rows.map(r => r.arrival);
    return cam.rows.map((r, p) => {
        const seg = fit.find(s => p >= s.posFirst && p <= s.posLast)!;
        const first = cam.rows[seg.posFirst];
        const d = r.sfn !== null && first.sfn !== null ? r.sfn - first.sfn : BigInt(p - seg.posFirst);
        const x = d * seg.periodPs;
        const floor = (x - (((x % 1000n) + 1000n) % 1000n)) / 1000n;
        return seg.t0 + floor;
    });
}

function holdsEachPosition(fit: FitSegment[], rows: number): boolean {
    let next = 0;
    for (const s of fit) {
        if (s.posFirst !== next || s.posLast < s.posFirst) return false;
        next = s.posLast + 1;
    }
    return next === rows;
}
