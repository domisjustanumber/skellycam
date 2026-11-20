// Unit tests of the take reader (specs/player.md section 6): T-PLAY-02 to T-PLAY-16, T-PLAY-25 to
// T-PLAY-28 and T-PLAY-36.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import type {CameraState} from '../../index.ts';
import {camByIndex, defaultTake, referenceTimes} from '../fixtures/take.ts';
import type {TakePlan} from '../fixtures/take.ts';
import {HEADER_VARIANTS, planOf} from '../fixtures/takes.ts';
import {openFixture, seek} from './helpers.ts';
import type {Opened} from './helpers.ts';

const byLabel = (o: Opened, label: string): CameraState => {
    const c = o.player.state.cameras.find(c => c.label === label);
    assert.ok(c, `camera ${label} is in the state`);
    return c;
};
const labelOf = (plan: TakePlan, index: number) => camByIndex(plan, index).label;

function assertNormalCameras(o: Opened) {
    const plan = o.built.plan;
    assert.deepEqual(o.player.state.cameras.map(c => c.label), plan.cameras.map(c => c.label), 'group_position order');
    for (const [i, c] of o.player.state.cameras.entries()) {
        assert.equal(c.name, o.built.cameras[i].mkv);
        assert.equal(c.state, 'finished');
        assert.equal(c.rows, 120);
    }
}

test('T-PLAY-02 open normal through the manifest', async t => {
    const o = await openFixture(t, 'normal');
    assertNormalCameras(o);
    assert.equal(o.player.state.take.manifest, 'present');
    assert.deepEqual(o.player.state.take.warnings, []);
    for (const c of o.player.state.cameras) assert.deepEqual(c.warnings.filter(w => w !== 'prerelease'), []);
    // each pair comes from cameras[]: the reader reads the paths of the manifest
    const csvReads = new Set(o.files.reads.filter(r => r.path.endsWith('.csv')).map(r => r.path));
    assert.deepEqual([...csvReads].sort(), o.built.cameras.map(c => c.csv).sort());
    assert.equal(o.player.state.frameCount, 120);
});

test('T-PLAY-03 open no_manifest by a scan', async t => {
    const o = await openFixture(t, 'no_manifest');
    assertNormalCameras(o);
    assert.equal(o.player.state.take.manifest, 'missing');
    assert.ok(o.player.state.take.warnings.includes('manifest_missing'));
});

test('T-PLAY-04 open the three bad_manifest takes', async t => {
    for (const name of ['bad_manifest_not_json', 'bad_manifest_not_manifest', 'bad_manifest_other_uuid']) {
        const o = await openFixture(t, name);
        assertNormalCameras(o);
        assert.equal(o.player.state.take.manifest, 'invalid', name);
        assert.ok(o.player.state.take.warnings.includes('manifest_missing'), name);
    }
});

test('T-PLAY-05 counts: deleted sidecar, 3 of 4, 5 for 4, a refused pair', async t => {
    for (const name of ['counts_deleted_sidecar', 'counts_three_of_four']) {
        const o = await openFixture(t, name);
        assert.equal(o.player.state.take.state, 'incomplete', name);
        assert.ok(o.player.state.take.warnings.includes('incomplete_take'), name);
        assert.equal(o.player.state.cameras.length, 3, name);
    }
    const extra = await openFixture(t, 'counts_extra');
    assert.ok(extra.player.state.take.warnings.includes('extra_files'));
    assert.equal(extra.player.state.cameras.length, 5);

    const refused = await openFixture(t, 'counts_refused');
    const plan = refused.built.plan;
    assert.equal(refused.player.state.take.state, 'complete', 'the refused pair counts as present');
    assert.ok(!refused.player.state.take.warnings.includes('incomplete_take'));
    const c2 = byLabel(refused, labelOf(plan, 2));
    assert.equal(c2.state, 'invalid');
    assert.equal(c2.reason, 'bad_rotation');
    assert.equal(refused.player.state.frameCount, 120, 'the refused file is not in K');
    await seek(refused, 10);
    assert.deepEqual(refused.tiles[2].mark, {kind: 'not_readable', reason: 'bad_rotation'});
});

test('T-PLAY-06 pairs: lone files, a sidecar with no mark, no audio read', async t => {
    const o = await openFixture(t, 'pairs');
    const plan = o.built.plan;
    const names = o.player.state.cameras.map(c => c.name);
    assert.ok(!names.some(n => n.includes('.lonely.')), 'the lone MKV is not in the take');
    const lone = byLabel(o, labelOf(plan, 2));
    assert.equal(lone.state, 'invalid');
    assert.equal(lone.reason, 'missing_media');
    assert.ok(!o.player.state.take.warnings.includes('extra_files'), 'the lone sidecar does not count');
    assert.ok(!o.player.state.take.warnings.includes('incomplete_take'));
    assert.ok(!o.player.state.cameras.some(c => c.label === labelOf(plan, 3)), 'a sidecar with no mark is ignored');
    assert.ok(!o.files.reads.some(r => r.path.endsWith('.m4a')), 'no read of the audio file');
    assert.equal(o.player.state.frameCount, 10);
});

test('T-PLAY-07 pairs: two takes and a .tmp file', async t => {
    const o = await openFixture(t, 'pairs');
    const plan = o.built.plan;
    const labels = o.player.state.cameras.map(c => c.label);
    assert.ok(labels.includes(labelOf(plan, 0)) && labels.includes(labelOf(plan, 1)), 'take A opens');
    assert.ok(!labels.includes(labelOf(plan, 4)) && !labels.includes(labelOf(plan, 5)), 'take B does not open');
    assert.ok(o.player.state.take.warnings.includes('multiple_takes'));
    assert.ok(o.player.state.take.warnings.includes('stray_tmp'));
    assert.ok(!o.files.reads.some(r => r.path.endsWith('.tmp')), 'the .tmp files are not read');
});

test('T-PLAY-08 header forms: each gives invalid with its reason', async t => {
    for (const [name, v] of Object.entries(HEADER_VARIANTS)) {
        const o = await openFixture(t, name);
        const c1 = o.player.state.cameras[1];
        assert.equal(c1.state, 'invalid', name);
        assert.equal(c1.reason, v.reason, name);
        for (const i of [0, 2, 3]) assert.equal(o.player.state.cameras[i].state, 'finished', `${name}: camera ${i} opens`);
    }
});

test('T-PLAY-09 versions, prerelease and the flags gap and encode_skip', async t => {
    const major = await openFixture(t, 'header_major3');
    assert.equal(major.player.state.cameras[1].state, 'unsupported_version');
    assert.equal(major.player.state.cameras[1].reason, null);

    const minor = await openFixture(t, 'header_minor1');
    assert.equal(minor.player.state.cameras[1].state, 'finished');
    assert.equal(minor.player.state.cameras[1].rows, 120);
    await seek(minor, 7);
    assert.equal(minor.shown(1).identity?.row, 7, 'the row with flag bit 7 is chosen as other rows');

    const pre1 = await openFixture(t, 'header_prerelease1');
    assert.ok(pre1.player.state.cameras[1].warnings.includes('prerelease'));
    const pre0 = await openFixture(t, 'header_prerelease0');
    assert.ok(!pre0.player.state.cameras[1].warnings.includes('prerelease'));

    const flags = await openFixture(t, 'gap_flags');
    const w = flags.player.state.cameras[1].warnings;
    assert.ok(w.includes('gap') && w.includes('encode_skip'));
    for (const k of [30, 31]) {
        await seek(flags, k);
        assert.equal(flags.shown(1).identity?.row, k);
        assert.equal(flags.shown(1).mark, null);
    }
});

test('T-PLAY-10 times of 2^53 - 1 and 2^53; a take start above 2^53', async t => {
    const o = await openFixture(t, 'header_times_2p53');
    assert.notEqual(o.player.state.cameras[1].state, 'invalid', '2^53 - 1 reads');
    assert.equal(o.player.state.cameras[2].state, 'invalid');
    assert.equal(o.player.state.cameras[2].reason, 'bad_time');
    assert.equal(o.player.state.cameras[0].state, 'finished', 'the large take start parses');
    await seek(o, 119);
    assert.equal(o.tiles[1].label?.timeNs, 2 ** 53 - 1, '2^53 - 1 is exact');
});

test('T-PLAY-11 bad_crc: camera 1 damaged at row 50', async t => {
    const o = await openFixture(t, 'bad_crc');
    const c1 = o.player.state.cameras[1];
    assert.equal(c1.state, 'damaged');
    assert.equal(c1.reason, 'crc_mismatch');
    assert.equal(c1.rows, 50);
    assert.equal(c1.damagedAt, 50);
    assert.equal(o.player.state.frameCount, 50);
    for (const i of [0, 2, 3]) assert.equal(o.player.state.cameras[i].rows, 120);
});

test('T-PLAY-12 unfinished camera 3: a torn last line', async t => {
    const o = await openFixture(t, 'unfinished');
    const c3 = o.player.state.cameras[3];
    assert.equal(c3.state, 'unfinished');
    assert.equal(c3.rows, 110, 'the torn row is not used');
    assert.equal(c3.tornBytes, '110,1110,3676'.length, 'torn_bytes holds the bytes of the torn line');
});

test('T-PLAY-13 footer cases', async t => {
    const after = defaultTake('rows_after_end');
    camByIndex(after, 1).footer.rowsAfterEnd = 5;
    const oa = await openFixture(t, after);
    assert.equal(oa.player.state.cameras[1].rows, 115, 'no row after the first footer line');
    assert.equal(oa.player.state.cameras[1].state, 'unfinished', 'the last line is not # end');

    const repaired = defaultTake('repair_end');
    camByIndex(repaired, 1).footer = {repair: true, end: true};
    const or = await openFixture(t, repaired);
    assert.equal(or.player.state.cameras[1].state, 'repaired');

    const interrupted = defaultTake('repair_no_end');
    camByIndex(interrupted, 1).footer = {repair: true, end: false};
    const oi = await openFixture(t, interrupted);
    assert.equal(oi.player.state.cameras[1].state, 'unfinished');
});

/** SFF-777 with BigInt and floor division, written here again, apart from the builder. */
function fitted(plan: TakePlan, index: number): bigint[] {
    const cam = camByIndex(plan, index);
    return cam.rows.map((r, p) => {
        const s = cam.fit!.find(s => p >= s.posFirst && p <= s.posLast)!;
        const f = cam.rows[s.posFirst].sfn;
        const d = r.sfn !== null && f !== null ? r.sfn - f : BigInt(p - s.posFirst);
        const x = d * s.periodPs;
        const q = x / 1000n;
        return s.t0 + (x < 0n && q * 1000n !== x ? q - 1n : q);
    });
}

async function shownTimes(o: Opened, camera: number, rows: number[]): Promise<number[]> {
    const out: number[] = [];
    for (const k of rows) {
        await seek(o, k);
        assert.equal(o.shown(camera).identity?.row, k);
        out.push(o.tiles[camera].label!.timeNs!);
    }
    return out;
}

test('T-PLAY-14 fitted times: two segments, a gap, a remainder, a negative d', async t => {
    const rows = [0, 1, 49, 50, 51, 119];
    const two = planOf('two_segments');
    const o = await openFixture(t, two);
    assert.deepEqual(await shownTimes(o, 1, rows), rows.map(k => Number(fitted(two, 1)[k])));

    const neg = planOf('fit_negative');
    const on = await openFixture(t, neg);
    const want = fitted(neg, 0);
    assert.ok(want[61] < want[60], 'the fixture has a negative d at row 61');
    assert.deepEqual(await shownTimes(on, 0, [59, 61, 62]), [59, 61, 62].map(k => Number(want[k])));
    // 7.3: at k* = 60 the image is row 61, the higher position whose running-maximum time is at T_60
    await seek(on, 60);
    assert.equal(on.shown(0).identity?.row, 61);
    assert.equal(on.tiles[0].label!.timeNs, Number(want[61]));

    const other = planOf('two_segments');
    other.name = 'two_segments_other_fitter';
    camByIndex(other, 1).fitter = 'another-fitter';
    const oo = await openFixture(t, other);
    assert.deepEqual(await shownTimes(oo, 1, rows), rows.map(k => Number(fitted(two, 1)[k])), 'a change of fitter changes nothing');
});

test('T-PLAY-15 arrival times and missing_fit', async t => {
    const o = await openFixture(t, 'no_fit');
    for (const i of [2, 3]) {
        const c = o.player.state.cameras[i];
        assert.equal(c.fit, false, `camera ${i}`);
        assert.ok(c.warnings.includes('missing_fit'), `camera ${i}`);
        const times = await shownTimes(o, i, [0, 60, 110]);
        const arrival = camByIndex(o.built.plan, i).rows.map(r => Number(r.arrival));
        assert.deepEqual(times, [arrival[0], arrival[60], arrival[110]], `camera ${i} uses arrival_ns`);
    }
    assert.equal(o.player.state.cameras[0].fit, true);

    const u = await openFixture(t, 'unfinished');
    const c2 = u.player.state.cameras[2];
    assert.equal(c2.fit, false, 'fit lines of an unfinished file are not used');
    assert.ok(c2.warnings.includes('missing_fit'));
    const arrival2 = camByIndex(u.built.plan, 2).rows.map(r => Number(r.arrival));
    assert.deepEqual(await shownTimes(u, 2, [5, 50]), [arrival2[5], arrival2[50]]);

    const synth = defaultTake('synthetic');
    for (const c of synth.cameras) c.header.clock = 'synthetic';
    camByIndex(synth, 1).fit = null;
    const os = await openFixture(t, synth);
    assert.equal(os.player.state.cameras[1].fit, false);
    assert.ok(!os.player.state.cameras[1].warnings.includes('missing_fit'), 'synthetic: no missing_fit');
});

test('T-PLAY-16 a wrong frame value and a decreasing time', async t => {
    const f = await openFixture(t, 'header_frame_value');
    assert.equal(f.player.state.cameras[1].state, 'finished', 'not refused');
    await seek(f, 5);
    assert.equal(f.shown(1).identity?.row, 5, 'the position is the row index');

    const d = await openFixture(t, 'header_time_decreasing');
    assert.equal(d.player.state.cameras[1].state, 'finished', 'not refused');
    const times = referenceTimes(camByIndex(d.built.plan, 1)).map(Number);
    const all = d.built.plan.cameras.map(c => referenceTimes(c).map(Number));
    let T = -Infinity;
    const Tk = times.map((_, k) => (T = Math.max(T, ...all.map(a => a[k]))));
    for (const k of [17, 18, 19, 20, 21]) {
        await seek(d, k);
        // the reference: the running maximum of camera 1, then the largest row at or before T_k
        let run = -Infinity;
        let want: number | null = null;
        times.forEach((p, r) => {
            run = Math.max(run, p);
            if (run <= Tk[k]) want = r;
        });
        assert.equal(d.shown(1).identity?.row, want, `k* = ${k}`);
    }
});

test('T-PLAY-25 frames with a 2-byte track number and 8-byte sizes', async t => {
    const o = await openFixture(t, 'block_wide');
    for (let k = 0; k < 20; k++) {
        await seek(o, k);
        for (const c of [0, 1]) assert.deepEqual(o.tiles[c].image, o.built.cameras[c].payloads[k], `camera ${c} row ${k}`);
    }
});

test('T-PLAY-26 frames around a Void, a Cluster start, a placeholder and an unknown-size Cluster', async t => {
    const o = await openFixture(t, 'block_void_cluster');
    for (const k of [9, 10, 12, 13, 14]) {
        await seek(o, k);
        assert.deepEqual(o.tiles[1].image, o.built.cameras[1].payloads[k], `row ${k}`);
    }
    await seek(o, 11);
    assert.equal(o.shown(1).identity?.row, 10);
    assert.deepEqual(o.shown(1).mark, {kind: 'no_frame'});
});

test('T-PLAY-27 rows and blocks that differ', async t => {
    for (const [name, k] of [['block_offset_wrong', 30], ['block_extra_middle', 31], ['block_laced', 30]] as const) {
        const o = await openFixture(t, name);
        const errors: unknown[] = [];
        o.player.on('error', e => void errors.push(e));
        await seek(o, k);
        assert.equal(o.player.state.cameras[1].state, 'invalid', name);
        assert.equal(o.player.state.cameras[1].reason, 'bad_metadata', name);
        assert.ok(errors.length > 0, `${name}: an error event`);
        assert.deepEqual(o.tiles[1].mark, {kind: 'not_readable', reason: 'bad_metadata'}, name);
    }
    const end = await openFixture(t, 'block_extra_end');
    assert.equal(end.player.state.cameras[1].state, 'invalid', 'an extra block at the end: invalid at the open');
    assert.equal(end.player.state.cameras[1].reason, 'bad_metadata');
    const cues = await openFixture(t, 'normal');
    assert.ok(cues.player.state.cameras.every(c => c.state === 'finished'), 'a Cues tail passes');
});

test('T-PLAY-28 a camera file with no EBML magic', async t => {
    const o = await openFixture(t, 'no_magic');
    const label = o.built.plan.cameras[1].label;
    const c = byLabel(o, label);
    assert.equal(c.state, 'invalid');
    assert.equal(c.reason, 'missing_media');
    const mkv = readFileSync(path.join(o.built.dir, o.built.cameras[1].mkv));
    assert.notDeepEqual([...mkv.subarray(0, 4)], [0x1a, 0x45, 0xdf, 0xa3]);
});

test('T-PLAY-36 a duplicate label and a take key that differs', async t => {
    const dup = await openFixture(t, 'counts_duplicate_label');
    assert.ok(dup.player.state.take.warnings.includes('duplicate_label'));
    assert.equal(dup.player.state.cameras.length, 4, 'both files are kept');

    const mismatch = defaultTake('counts_group_size_mismatch');
    camByIndex(mismatch, 2).header.group_size = '5';
    const om = await openFixture(t, mismatch);
    assert.ok(om.player.state.take.warnings.includes('take_fact_mismatch'));
    // the values of group_position 0: group_size 4, so 4 files are a complete take
    assert.ok(!om.player.state.take.warnings.includes('incomplete_take'));
    assert.equal(om.player.state.take.state, 'complete');
});
