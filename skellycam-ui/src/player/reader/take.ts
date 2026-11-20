// The take reader (specs/player.md section 6): the device pairs, the take, the manifest, the sidecars,
// the camera file heads and tails, K and T_k. It gives only the members that the player needs [L2].
import type {TakeFiles} from '../files/take-files.ts';
import {frameTimes} from '../clock/choose.ts';
import {playerTimes} from './fit.ts';
import {deadFromDetail, MANIFEST, readManifest} from './manifest.ts';
import {BlockMismatch, checkTail, EBML_MAGIC, readHead} from './matroska.ts';
import {isMissing, readSidecar, TAKE_KEYS, VIDEO_MARK} from './sidecar.ts';
import type {FileState, Sidecar} from './sidecar.ts';

const MEDIA = /^synchronized_videos\/[^/]+$/;
const UUID = /^[0-9a-f]{32}$/;

export interface CameraState {
    label: string;
    name: string;
    state: FileState;
    reason: string | null;
    rows: number | null;
    tornBytes: number | null;
    fit: boolean | null;
    warnings: string[];
    rotation: 0 | 90 | 180 | 270;
    missingRows: number;
    deadFrom: number | null;
    damagedAt: number | null;
}

export interface TakeState {
    state: 'complete' | 'incomplete';
    manifest: 'present' | 'missing' | 'invalid';
    unfinished: boolean;
    warnings: string[];
}

/** A camera of the take: its public state and what the clock and the frame reads need. */
export interface Camera {
    info: CameraState;
    times: (number | null)[];
    missing: boolean[];
    offset: (number | null)[];
    size: (number | null)[];
    frames: number;            // the usable frames, for K
    videoTrack: number;
    firstCluster: number;
    nominalFps: number;
}

export interface Take {
    take: TakeState;
    recording: boolean;        // the manifest says `recording`: every tile gets "unfinished"
    cameras: Camera[];
    frameCount: number;
    frameTimes: number[];
    nominalFps: number;
}

interface Found {
    csv: string;
    mkv: string;
    mkvSize: number;
    paired: boolean;
    sc: Sidecar;
}

const firstLineIs = (b: Uint8Array, line: string) => new TextDecoder().decode(b.subarray(0, line.length + 1)) === line + '\n';

async function hasMagic(files: TakeFiles, mkv: string, size: number | undefined): Promise<boolean> {
    if (size === undefined || size < 4) return false;
    const b = await files.readRange(mkv, 0, 4);
    return EBML_MAGIC.every((v, i) => b[i] === v);
}

/** True when the folder holds a device pair of a camera (SFF-864). */
export async function isTakeFolder(files: TakeFiles): Promise<boolean> {
    const sizes = new Map(files.entries.map(e => [e.path, e.size]));
    for (const e of files.entries) {
        if (!MEDIA.test(e.path) || !e.path.endsWith('.csv') || e.size <= VIDEO_MARK.length) continue;
        const mkv = e.path.slice(0, -4) + '.mkv';
        if (firstLineIs(await files.readRange(e.path, 0, VIDEO_MARK.length + 1), VIDEO_MARK) && await hasMagic(files, mkv, sizes.get(mkv))) return true;
    }
    return false;
}

const refused = (s: FileState) => s === 'invalid' || s === 'unsupported_version';
const sort = (a: string[]) => [...new Set(a)].sort();

export async function readTake(files: TakeFiles): Promise<Take> {
    const warnings: string[] = [];
    const sizes = new Map(files.entries.map(e => [e.path, e.size]));
    if (files.entries.some(e => e.path.endsWith('.tmp'))) warnings.push('stray_tmp');

    const found: Found[] = [];
    for (const e of files.entries) {
        if (!MEDIA.test(e.path) || !e.path.endsWith('.csv')) continue;
        const bytes = await files.readWhole(e.path, Infinity);
        if (!firstLineIs(bytes, VIDEO_MARK)) continue;
        const mkv = e.path.slice(0, -4) + '.mkv';
        found.push({csv: e.path, mkv, mkvSize: sizes.get(mkv) ?? 0, paired: await hasMagic(files, mkv, sizes.get(mkv)), sc: readSidecar(bytes)});
    }
    const uuids = sort(found.filter(f => f.paired && UUID.test(f.sc.header.take_uuid ?? '')).map(f => f.sc.header.take_uuid));
    if (uuids.length > 1) warnings.push('multiple_takes');
    const chosen = uuids[0];
    // a pair whose take_uuid does not read joins the take as a refused camera, so its tile tells why
    let members = chosen === undefined ? [] : found.filter(f => f.sc.header.take_uuid === chosen || (f.paired && !UUID.test(f.sc.header.take_uuid ?? '')));

    const manifest = sizes.has(MANIFEST) ? await readManifest(files) : null;
    const used = manifest !== null && manifest.takeUuid === chosen ? manifest : null;
    if (!used) warnings.push('manifest_missing');
    else {
        members = members.filter(f => used.timings.has(f.csv));
        warnings.push(...used.warnings.map(w => w.code));
    }

    const position = (f: Found) => (/^(0|[1-9][0-9]*)$/.test(f.sc.header.group_position ?? '') ? Number(f.sc.header.group_position) : Infinity);
    members.sort((a, b) => position(a) - position(b) || (a.mkv < b.mkv ? -1 : a.mkv > b.mkv ? 1 : 0));

    const cameras: Camera[] = [];
    for (const f of members) cameras.push(await readCamera(files, f, used));

    const pairs = members.filter(f => f.paired);
    const checked = pairs.filter(f => !refused(f.sc.state));
    const first = checked[0]?.sc.header;
    if (first && checked.some(f => TAKE_KEYS.some(k => f.sc.header[k] !== first[k]))) warnings.push('take_fact_mismatch');
    const groupSize = first ? Number(first.group_size) : pairs.length;
    if (pairs.length < groupSize) warnings.push('incomplete_take');
    if (pairs.length > groupSize) warnings.push('extra_files');
    const labels = pairs.map(f => f.sc.header.camera_label).filter(l => l !== undefined);
    if (new Set(labels).size < labels.length) warnings.push('duplicate_label');

    const playable = cameras.filter(c => !refused(c.info.state));
    const frameCount = playable.length ? Math.min(...playable.map(c => c.frames)) : 0;
    return {
        take: {
            state: pairs.length < groupSize ? 'incomplete' : 'complete',
            manifest: !sizes.has(MANIFEST) ? 'missing' : used ? 'present' : 'invalid',
            unfinished: !!used?.recording || cameras.some(c => c.info.state === 'unfinished'),
            warnings: sort(warnings),
        },
        recording: !!used?.recording,
        cameras,
        frameCount,
        frameTimes: frameTimes(playable.map(c => c.times), frameCount),
        nominalFps: playable.length ? Math.round(playable[0].nominalFps * 1000) / 1000 : 0,
    };
}

async function readCamera(files: TakeFiles, f: Found, manifest: Awaited<ReturnType<typeof readManifest>>): Promise<Camera> {
    const {sc} = f;
    const h = sc.header;
    const rate = /^([0-9]+)\/([0-9]+)$/.exec(h.nominal_rate ?? '');
    const info: CameraState = {
        label: h.camera_label ?? '', name: f.mkv, state: sc.state, reason: sc.reason, rows: null, tornBytes: null, fit: null,
        warnings: [...sc.warnings], rotation: (Number(h.display_rotation) || 0) as CameraState['rotation'], missingRows: 0,
        deadFrom: null, damagedAt: sc.damagedAt,
    };
    const camera: Camera = {
        info, times: [], missing: [], offset: [], size: [], frames: 0, videoTrack: 0, firstCluster: 0,
        nominalFps: rate ? Number(rate[1]) / Number(rate[2]) : 0,
    };
    const refuse = (reason: string) => {
        Object.assign(info, {state: 'invalid', reason, rows: null, tornBytes: null, fit: null, missingRows: 0, deadFrom: null, damagedAt: null});
        return camera;
    };
    if (!f.paired) return refuse('missing_media');
    if (refused(sc.state)) return camera;

    const ended = sc.state === 'finished' || sc.state === 'repaired';
    const timed = playerTimes(sc.arrival, sc.sfn, ended ? sc.fit : null);
    if (!timed) return refuse('bad_time');
    const missing = sc.flags.map(isMissing);
    Object.assign(camera, {times: timed.times, missing, offset: sc.offset, size: sc.size});
    Object.assign(info, {rows: sc.flags.length, fit: timed.fitted, missingRows: missing.filter(Boolean).length});
    if (!timed.fitted && h.clock !== 'synthetic') info.warnings.push('missing_fit');

    try {
        const head = await readHead(files, f.mkv, f.mkvSize);
        camera.videoTrack = head.videoTrack;
        camera.firstCluster = head.firstCluster;
        // SFF-740: a frame is usable when its block is complete in the snapshot
        const incomplete = sc.offset.findIndex((o, k) => o !== null && o + sc.size[k]! > f.mkvSize);
        if (incomplete >= 0 && ended) return refuse('bad_metadata');
        camera.frames = incomplete >= 0 ? incomplete : sc.flags.length;
        let lastEnd = head.firstCluster;
        for (let k = camera.frames - 1; k >= 0; k--) {
            if (sc.offset[k] !== null) {
                lastEnd = sc.offset[k]! + sc.size[k]!;
                break;
            }
        }
        if (ended) await checkTail(files, f.mkv, lastEnd, f.mkvSize);
        info.tornBytes = sc.tornBytes + (ended || sc.state === 'damaged' ? 0 : f.mkvSize - lastEnd);
    } catch (e) {
        if (e instanceof BlockMismatch) return refuse('bad_metadata');
        throw e;
    }

    // 7.3: a dead camera from `camera_dead` of a finished manifest, else from a run of `missing` rows to the end
    const dead = manifest && !manifest.recording ? manifest.warnings.find(w => w.code === 'camera_dead' && w.cameraKey === h.camera_key) : undefined;
    const fromDetail = dead ? deadFromDetail(dead.detail) : null;
    if (fromDetail !== null) info.deadFrom = fromDetail;
    else if ((!manifest || manifest.recording || dead) && missing.at(-1)) {
        let n = missing.length;
        while (n > 0 && missing[n - 1]) n--;
        info.deadFrom = n;
    }
    return camera;
}
