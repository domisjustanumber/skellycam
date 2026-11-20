// The takes of specs/player.md section 12.2, as plans. `buildTake(name, root)` writes one into a new
// folder below `root`. A test can also take a plan, change it and write it with `writeTake`.
import {camByIndex, defaultCamera, defaultTake, markMissing, MEDIA, NS_PER_FRAME_30, writeTake} from './take.ts';
import type {BuiltTake, TakePlan} from './take.ts';
import {FLAG} from './sidecar.ts';

const OTHER_UUID = '9a3e2f2b3c4d5e6f6f1c2c1e1d7e4c47';

function noFit(plan: TakePlan): TakePlan {
    for (const c of plan.cameras) c.fit = null;
    return plan;
}

function live(plan: TakePlan, index: number): void {
    camByIndex(plan, index).mkv.form = 'live';
}

function shortCamera3(plan: TakePlan): void {
    const c3 = camByIndex(plan, 3);
    markMissing(c3, 80, 119, false, 'missing_noblock');
    c3.footer = {repair: true, end: true};
    c3.fit = null;
    live(plan, 3);
}

/** The header variants of T-PLAY-08 to T-PLAY-10 and T-PLAY-16: each changes camera 1 of `normal`. */
export const HEADER_VARIANTS: Record<string, {apply: (p: TakePlan) => void; reason: string | null}> = {
    header_leading_zero: {apply: p => (camByIndex(p, 1).header.group_size = '04'), reason: 'bad_metadata'},
    header_plus_sign: {apply: p => (camByIndex(p, 1).header.utc_offset_min = '+60'), reason: 'bad_metadata'},
    // a take_uuid that does not read: the pair is in no take (SFF-865, SFF-889), so no reason
    header_uuid_dashes: {apply: p => (camByIndex(p, 1).header.take_uuid = '6f1c2c1e-1d7e-4c47-9a3e-2f2b3c4d5e6f'), reason: null},
    header_row_2p53: {apply: p => (camByIndex(p, 1).rows[5].fields = {byte_size: '9007199254740992'}), reason: 'bad_metadata'},
    header_rate_zero: {apply: p => (camByIndex(p, 1).header.nominal_rate = '0/1'), reason: 'bad_rate'},
    header_rate_big: {apply: p => (camByIndex(p, 1).header.nominal_rate = '1048577/1'), reason: 'bad_rate'},
    header_rotation_45: {apply: p => (camByIndex(p, 1).header.display_rotation = '45'), reason: 'bad_rotation'},
    header_bad_label: {apply: p => (camByIndex(p, 1).header.camera_label = 'CAM-1'), reason: 'bad_label'},
    header_missing_key: {apply: p => (camByIndex(p, 1).header.take_start_utc_ns = null), reason: 'missing_metadata'},
    header_missing_column: {
        apply: p => (camByIndex(p, 1).columns = ['frame', 'source_frame_number', 'arrival_ns', 'sample_ns', 'flags', 'byte_offset', 'crc32']),
        reason: 'missing_metadata',
    },
    header_unknown_clock: {apply: p => (camByIndex(p, 1).header.clock = 'sundial'), reason: 'bad_metadata'},
};

export const VERSION_VARIANTS: Record<string, (p: TakePlan) => void> = {
    header_major3: p => (camByIndex(p, 1).header.format_version = '3.0'),
    header_minor1: p => {
        const c = camByIndex(p, 1);
        c.header.format_version = '2.1';
        c.extraHeader = ['# future_key=1'];
        c.columns = ['frame', 'source_frame_number', 'arrival_ns', 'sample_ns', 'flags', 'byte_offset', 'byte_size', 'future_col', 'crc32'];
        c.rows[7].flags = 128;
    },
    header_prerelease0: p => (camByIndex(p, 1).header.format_prerelease = '0'),
    header_prerelease1: p => (camByIndex(p, 1).header.format_prerelease = '1'),
};

export const PLANS: Record<string, () => TakePlan> = {
    normal: () => defaultTake('normal'),

    offsets: () => {
        const p = noFit(defaultTake('offsets'));
        const offsets = [0n, 7_650_000n, -3_000_000n, 19_900_000n];
        p.cameras = p.cameras.map((c, i) => ({...defaultCamera(i, 120, offsets[i]), fit: null}));
        // two rows 11 us apart (GF08 section 1.1)
        camByIndex(p, 1).rows[30].arrival = camByIndex(p, 0).rows[30].arrival! + 11_000n;
        // two equal values of T_k: camera 0 has one time at rows 50 and 51, later than each time of row 51
        const late = 10_000_000n + 51n * NS_PER_FRAME_30 + 25_000_000n;
        camByIndex(p, 0).rows[50].arrival = late;
        camByIndex(p, 0).rows[51].arrival = late;
        return p;
    },

    missing: () => {
        const p = defaultTake('missing');
        const c1 = camByIndex(p, 1);
        markMissing(c1, 0, 0, false);
        markMissing(c1, 10, 10, true);
        markMissing(c1, 40, 59, true);
        return p;
    },

    dead: () => {
        const p = defaultTake('dead');
        markMissing(camByIndex(p, 2), 70, 119, false);
        p.warnings.push({code: 'camera_dead', camera: 2, detail: 'last_frame=69 reason=disconnected'});
        return p;
    },

    dead_no_manifest: () => {
        const p = PLANS.dead();
        p.name = 'dead_no_manifest';
        p.manifest = 'missing';
        return p;
    },

    dead_short: () => {
        const p = defaultTake('dead_short');
        shortCamera3(p);
        p.warnings.push({code: 'camera_dead', camera: 3, detail: 'last_frame=79 reason=hang'});
        p.warnings.push({code: 'camera_file_short', camera: 3, detail: 'blocks=80 rows=120'});
        return p;
    },

    write_error_short: () => {
        const p = defaultTake('write_error_short');
        shortCamera3(p);
        p.warnings.push({code: 'camera_file_short', camera: 3, detail: 'blocks=80 rows=120'});
        p.warnings.push({code: 'take_error', camera: 3, detail: 'write error: disk full'});
        return p;
    },

    trailing_damage: () => {
        const p = defaultTake('trailing_damage');
        markMissing(camByIndex(p, 1), 115, 119, true);
        return p;
    },

    unfinished: () => {
        const p = noFit(defaultTake('unfinished'));
        p.manifest = 'recording';
        for (const c of p.cameras) {
            c.footer = {repair: false, end: false};
            c.mkv.form = 'live';
        }
        // camera 1: the MKV ends in the middle of the block of row 97, so 97 blocks are complete
        camByIndex(p, 1).mkv.cutInBlock = 97;
        // camera 2: fit lines in a file with no `# end` (they must not be used)
        const c2 = camByIndex(p, 2);
        c2.fit = defaultCamera(2).fit;
        // camera 3: 110 complete rows, then a torn line
        const c3 = camByIndex(p, 3);
        c3.rows = c3.rows.slice(0, 110);
        c3.footer.torn = '110,1110,3676';
        return p;
    },

    recording_finished: () => {
        const p = defaultTake('recording_finished');
        p.manifest = 'recording';
        return p;
    },

    no_manifest: () => ({...defaultTake('no_manifest'), manifest: 'missing'}),
    bad_manifest_not_json: () => ({...defaultTake('bad_manifest_not_json'), manifest: 'not_json'}),
    bad_manifest_not_manifest: () => ({...defaultTake('bad_manifest_not_manifest'), manifest: 'not_manifest'}),
    bad_manifest_other_uuid: () => ({...defaultTake('bad_manifest_other_uuid'), manifest: 'other_uuid'}),

    bad_crc: () => {
        const p = defaultTake('bad_crc');
        camByIndex(p, 1).rows[50].badCrc = true;
        return p;
    },

    rotations: () => {
        const p = defaultTake('rotations', 4, 10);
        p.cameras.forEach((c, i) => (c.rotation = String(i * 90)));
        return p;
    },

    no_fit: () => {
        const p = defaultTake('no_fit');
        camByIndex(p, 2).fit = null;
        // camera 3: a fit that does not hold each position
        const c3 = camByIndex(p, 3);
        c3.fit = [{...c3.fit![0], posLast: 100}];
        return p;
    },

    fit_negative: () => {
        const p = defaultTake('fit_negative');
        const c0 = camByIndex(p, 0);
        // two segments; in the second, row 61 has a source frame number below that of pos_first (60)
        c0.rows[60].sfn = 1065n;
        c0.rows[61].sfn = 1064n;
        // rows 62 on come after row 60, so no later row has the fitted time of row 60
        for (let k = 62; k < 120; k++) c0.rows[k].sfn = 1004n + BigInt(k);
        c0.fit = [
            {posFirst: 0, posLast: 59, t0: 10_000_000n, periodPs: 33_333_333_333n},
            {posFirst: 60, posLast: 119, t0: 10_000_000n + 65n * NS_PER_FRAME_30, periodPs: 33_333_333_333n},
        ];
        return p;
    },

    two_segments: () => {
        // T-PLAY-14: two fit segments, a source frame gap and a period with a remainder
        const p = defaultTake('two_segments');
        const c1 = camByIndex(p, 1);
        for (let k = 50; k < 120; k++) c1.rows[k].sfn = 1003n + BigInt(k);   // a jump of 3 at row 50
        c1.rows[50].flags = FLAG.gap;
        c1.fit = [
            {posFirst: 0, posLast: 49, t0: 10_000_017n, periodPs: 33_333_333_337n},
            {posFirst: 50, posLast: 119, t0: 10_000_000n + 53n * NS_PER_FRAME_30, periodPs: 33_366_666_667n},
        ];
        return p;
    },

    header_frame_value: () => {
        const p = defaultTake('header_frame_value');
        camByIndex(p, 1).rows[5].frameValue = '500';
        return p;
    },

    header_time_decreasing: () => {
        const p = defaultTake('header_time_decreasing');
        const c1 = camByIndex(p, 1);
        c1.fit = null;
        c1.rows[20].arrival = c1.rows[18].arrival! - 1_000_000n;   // row 20 is earlier than rows 18 and 19
        return p;
    },

    header_times_2p53: () => {
        // T-PLAY-10: camera 1 has a time of 2^53 - 1 (it reads), camera 2 a time of 2^53 (bad_time),
        // and the take start is above 2^53
        const p = defaultTake('header_times_2p53');
        p.takeStartHost = 2n ** 60n + 12_345n;
        const c1 = camByIndex(p, 1);
        c1.fit = null;
        c1.rows[119].arrival = 2n ** 53n - 1n;
        const c2 = camByIndex(p, 2);
        c2.fit = null;
        c2.rows[119].arrival = 2n ** 53n;
        return p;
    },

    gap_flags: () => {
        const p = defaultTake('gap_flags');
        const c1 = camByIndex(p, 1);
        c1.rows[30].flags = FLAG.gap;
        c1.rows[31].flags = FLAG.encode_skip;
        return p;
    },

    block_offset_wrong: () => {
        const p = defaultTake('block_offset_wrong');
        camByIndex(p, 1).rows[30].offsetDelta = 1;
        return p;
    },
    block_extra_middle: () => {
        const p = defaultTake('block_extra_middle');
        camByIndex(p, 1).rows[30].extraBlockAfter = true;
        return p;
    },
    block_laced: () => {
        const p = defaultTake('block_laced');
        camByIndex(p, 1).rows[30].laced = true;
        return p;
    },
    block_extra_end: () => {
        const p = defaultTake('block_extra_end');
        camByIndex(p, 1).mkv.extraBlockAtEnd = true;
        return p;
    },
    block_wide: () => {
        const p = defaultTake('block_wide', 2, 20);
        for (const c of p.cameras) c.mkv = {form: 'finished', sizeLength: 8, trackNumberLength: 2};
        return p;
    },
    block_void_cluster: () => {
        const p = defaultTake('block_void_cluster', 2, 30);
        const c1 = camByIndex(p, 1);
        c1.rows[10].voidBefore = true;
        markMissing(c1, 11, 11, true);
        c1.rows[12].unknownSizeCluster = true;
        return p;
    },
    no_magic: () => {
        const p = defaultTake('no_magic');
        camByIndex(p, 1).mkv.noMagic = true;
        return p;
    },

    jpeg_forms: () => {
        const p = noFit(defaultTake('jpeg_forms', 5, 10));
        const forms = [{noDht: true}, {noDht: true, insertDht: true}, {}, {exifOrientation: 6}, {trailingBytes: 1024}];
        p.cameras.forEach((c, i) => c.rows.forEach(r => (r.jpeg = forms[i])));
        return p;
    },

    pairs: () => {
        // T-PLAY-06 and T-PLAY-07: take A (2 cameras) and take B (2 cameras), no manifest, and the odd files
        const p = noFit(defaultTake('pairs', 2, 10));
        p.manifest = 'missing';
        p.takeUuid = '1111aaaa2222bbbb3333cccc4444dddd';
        const lone = {...defaultCamera(2, 10), fit: null, position: 2, noMkv: true};
        const noMark = {...defaultCamera(3, 10), fit: null, position: 3, firstLine: '# not_a_mark=1'};
        // take B: a higher take_uuid, so take A opens first
        const takeB = [4, 5].map((index, position) => ({...defaultCamera(index, 10), fit: null, position, header: {take_uuid: OTHER_UUID}}));
        p.cameras.push(lone, noMark, ...takeB);
        p.extraFiles = [
            {path: `${MEDIA}/${p.rec}.lonely.mkv`, content: new Uint8Array([0x1a, 0x45, 0xdf, 0xa3, 0x80])},
            {path: `${MEDIA}/${p.rec}.audio.m4a`, content: new Uint8Array(64)},
            {path: `${MEDIA}/${p.rec}.audio.csv`, content: '# skellyfileformat=audio_timing\n# format_version=2.0\n'},
            {path: `${MEDIA}/${p.rec}.e0e0e0.csv.tmp`, content: '# skellyfileformat=video_timing\n'},
            {path: `${MEDIA}/${p.rec}.e0e0e0.mkv.tmp`, content: new Uint8Array([0x1a, 0x45, 0xdf, 0xa3])},
        ];
        return p;
    },

    counts_deleted_sidecar: () => {
        const p = defaultTake('counts_deleted_sidecar');
        p.deleteAfter = [`${MEDIA}/${p.rec}.${camByIndex(p, 3).label}.csv`];
        return p;
    },
    counts_three_of_four: () => {
        const p = defaultTake('counts_three_of_four');
        p.cameras = p.cameras.slice(0, 3);
        return p;
    },
    counts_extra: () => {
        const p = defaultTake('counts_extra', 5);
        p.groupSize = 4;
        return p;
    },
    counts_refused: () => {
        const p = defaultTake('counts_refused');
        camByIndex(p, 2).header.display_rotation = '45';
        return p;
    },
    counts_duplicate_label: () => {
        const p = defaultTake('counts_duplicate_label');
        camByIndex(p, 2).label = camByIndex(p, 1).label;
        camByIndex(p, 2).stem = `${p.rec}.${camByIndex(p, 1).label}_b`;
        return p;
    },
    counts_fact_mismatch: () => {
        const p = defaultTake('counts_fact_mismatch');
        camByIndex(p, 2).header.utc_offset_min = '60';
        return p;
    },
};

export function planOf(name: string): TakePlan {
    const make = PLANS[name];
    if (make) return make();
    const header = HEADER_VARIANTS[name];
    const version = VERSION_VARIANTS[name];
    if (!header && !version) throw new Error(`unknown fixture ${name}`);
    const p = defaultTake(name);
    (header ? header.apply : version)(p);
    return p;
}

export function buildTake(name: string, root: string): BuiltTake {
    return writeTake(root, planOf(name));
}

export {OTHER_UUID};
