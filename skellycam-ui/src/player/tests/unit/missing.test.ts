// Unit tests of missing rows, dead cameras, short files and unfinished takes: T-PLAY-17 to T-PLAY-24
// and T-PLAY-71 (specs/player.md sections 6.7, 6.11, 7.2 and 7.3).
import assert from 'node:assert/strict';
import {readdirSync, readFileSync, statSync} from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import {camByIndex, defaultTake, markMissing, referenceTimes} from '../fixtures/take.ts';
import type {TakePlan} from '../fixtures/take.ts';
import {planOf} from '../fixtures/takes.ts';
import {openFixture, seek} from './helpers.ts';
import type {Opened} from './helpers.ts';

/** T_k of section 7.2, from the reference times of the builder. */
function referenceT(plan: TakePlan): number[] {
    const times = plan.cameras.map(c => referenceTimes(c).map(v => (v === null ? null : Number(v))));
    const all = times.flat().filter((v): v is number => v !== null);
    const out: number[] = [];
    for (let k = 0; k < plan.cameras[0].rows.length; k++) {
        const here = times.map(c => c[k]).filter((v): v is number => v !== null);
        const prev = k === 0 ? (here.length ? -Infinity : Math.min(...all)) : out[k - 1];
        out.push(Math.max(prev, ...here));
    }
    return out;
}

function assertNoPlaceholderDecoded(o: Opened) {
    for (const img of o.decoder.images) assert.ok(!img.identity?.placeholder, 'no placeholder is decoded');
    for (const tile of o.tiles) for (const u of tile.updates) assert.ok(!o.built.identify(u.jpeg)?.placeholder, 'no placeholder is given to a tile');
}

test('T-PLAY-17 missing: rows, placeholders, images and marks', async t => {
    const o = await openFixture(t, 'missing');
    const c1 = o.player.state.cameras[1];
    assert.equal(c1.rows, 120, 'the missing rows are usable');
    assert.equal(c1.missingRows, 22);
    assert.equal(c1.state, 'finished');
    // at open k* = 0: row 0 of camera 1 is missing with no time, so the tile is black
    assert.equal(o.shown(1).identity, null, 'black at k* = 0');
    assert.deepEqual(o.shown(1).mark, {kind: 'no_frame'});
    const cases: [number, number, boolean][] = [[9, 9, false], [10, 9, true], [40, 39, true], [59, 39, true], [60, 60, false]];
    for (const [k, row, mark] of cases) {
        await seek(o, k);
        assert.equal(o.shown(1).identity?.row, row, `k* = ${k}`);
        assert.deepEqual(o.shown(1).mark, mark ? {kind: 'no_frame'} : null, `k* = ${k}`);
    }
    // each missing row maps to its placeholder block: reads of camera 1 may cover them, decodes never
    assertNoPlaceholderDecoded(o);
});

test('T-PLAY-18 dead: camera 2 lost at frame 70', async t => {
    const o = await openFixture(t, 'dead');
    const c2 = o.player.state.cameras[2];
    assert.notEqual(c2.state, 'invalid', 'not refused');
    assert.equal(c2.deadFrom, 70);
    assert.equal(o.player.state.frameCount, 120);
    const T = referenceT(o.built.plan);
    for (const k of [70, 95, 119]) {
        await seek(o, k);
        assert.equal(o.shown(2).identity?.row, 69, `k* = ${k}`);
        assert.deepEqual(o.shown(2).mark, {kind: 'camera_lost', frame: 70});
        assert.equal(o.player.state.time, T[k], 'T_k from cameras 0, 1 and 3');
    }
    await seek(o, 69);
    assert.equal(o.shown(2).identity?.row, 69);
    assert.equal(o.shown(2).mark, null);
    assertNoPlaceholderDecoded(o);
});

test('T-PLAY-19 dead_no_manifest and trailing_damage', async t => {
    const o = await openFixture(t, 'dead_no_manifest');
    assert.equal(o.player.state.cameras[2].deadFrom, 70, 'from the run of missing rows at the end');
    await seek(o, 100);
    assert.deepEqual(o.shown(2).mark, {kind: 'camera_lost', frame: 70});

    const d = await openFixture(t, 'trailing_damage');
    assert.ok(d.player.state.cameras.every(c => c.deadFrom === null), 'no dead camera');
    for (const k of [115, 119]) {
        await seek(d, k);
        assert.equal(d.shown(1).identity?.row, 114);
        assert.deepEqual(d.shown(1).mark, {kind: 'no_frame'});
    }
});

test('T-PLAY-20 T_k with missing rows that have and have no time', async t => {
    const o = await openFixture(t, 'missing');
    const T = referenceT(o.built.plan);
    for (const k of [0, 10, 40, 59]) {
        await seek(o, k);
        assert.equal(o.player.state.time, T[k], `T_${k}`);
    }
    const t1row10 = Number(referenceTimes(camByIndex(o.built.plan, 1))[10]);
    assert.ok(T[10] >= t1row10, 'T_10 uses the time of camera 1 at row 10');

    // a row where no camera has a time
    const p = planOf('missing');
    p.name = 'missing_no_time_row';
    for (const c of p.cameras) markMissing(c, 30, 30, false);
    const v = await openFixture(t, p);
    await seek(v, 30);
    const at30 = v.player.state.time;
    await seek(v, 29);
    assert.equal(at30, v.player.state.time, 'T_30 = T_29');
    await seek(v, 10);
    assert.equal(v.shown(1).identity?.row, 9, 'images as T-PLAY-17');
});

test('T-PLAY-21 dead_short: the short file of a killed process', async t => {
    const o = await openFixture(t, 'dead_short');
    const c3 = o.player.state.cameras[3];
    assert.equal(c3.state, 'repaired');
    assert.equal(c3.rows, 120);
    assert.equal(c3.deadFrom, 80);
    await seek(o, 40);
    assert.deepEqual(o.tiles[3].image, o.built.cameras[3].payloads[40], 'the live MKV form is read');
    for (const k of [80, 119]) {
        await seek(o, k);
        assert.equal(o.shown(3).identity?.row, 79);
        assert.deepEqual(o.shown(3).mark, {kind: 'camera_lost', frame: 80});
    }
    const mkvSize = o.built.cameras[3].mkvSize;
    for (const r of o.files.reads) if (r.path === o.built.cameras[3].mkv) assert.ok(r.end <= mkvSize, 'rows 80 to 119 have no block');

    const none = planOf('dead_short');
    none.name = 'dead_short_none';
    none.warnings[0].detail = 'last_frame=none reason=hang';
    const on = await openFixture(t, none);
    assert.equal(on.player.state.cameras[3].deadFrom, 0);
});

test('T-PLAY-22 unfinished: usable counts and K', async t => {
    const o = await openFixture(t, 'unfinished');
    // `rows` counts each usable row, also after the last complete block (SFF-740)
    assert.deepEqual(o.player.state.cameras.map(c => c.rows), [120, 120, 120, 110]);
    assert.equal(o.player.state.frameCount, 97, 'K: camera 1 has 97 usable frames');
    o.player.seekFrame(500);
    await o.settle();
    assert.equal(o.player.state.frame, 96);
    assert.equal(o.player.state.lastTime, o.player.state.time, 'T_96 is the last time');
});

test('T-PLAY-23 unfinished and recording_finished: read only', async t => {
    const snapshot = (dir: string) => readdirSync(dir, {recursive: true}).map(String).sort()
        .map(f => {
            const s = statSync(path.join(dir, f));
            return `${f}:${s.size}:${s.mtimeMs}`;
        });
    const o = await openFixture(t, 'unfinished');
    const before = snapshot(o.built.dir);
    assert.equal(o.player.state.take.unfinished, true);
    const c1 = o.built.cameras[1];
    const lastEnd = c1.blocks[96]!.offset + c1.blocks[96]!.size;
    await seek(o, 96);
    assert.equal(o.shown(1).identity?.row, 96);
    for (const r of o.files.reads) if (r.path === c1.mkv) assert.ok(r.end <= lastEnd, 'no read past the last complete block');
    assert.equal(o.player.state.cameras[1].tornBytes, c1.mkvSize - lastEnd, 'torn_bytes: the bytes after the last complete block');
    await o.player.close();
    assert.deepEqual(snapshot(o.built.dir), before, 'no file is written');

    const r = await openFixture(t, 'recording_finished');
    assert.equal(r.player.state.take.unfinished, true);
    assert.ok(r.player.state.cameras.every(c => c.state === 'finished'));
});

test('T-PLAY-24 snapshot sizes below the file sizes', async t => {
    // camera 0: 2 rows and the footer, and half of the last block, are past the snapshot
    let mkvCut = 0;
    const o = await openFixture(t, defaultTake('snapshot_short'), {
        files: built => {
            const cam0 = built.cameras[0];
            const csvText = readFileSync(path.join(built.dir, cam0.csv), 'utf8');
            const last = cam0.blocks[119]!;
            mkvCut = last.offset + Math.floor(last.size / 2);
            return {sizes: {[cam0.csv]: Buffer.byteLength(csvText.slice(0, csvText.indexOf('\n118,') + 1)), [cam0.mkv]: mkvCut}};
        },
    });
    const c0 = o.player.state.cameras[0];
    assert.equal(c0.state, 'unfinished');
    assert.equal(c0.rows, 118);
    assert.equal(o.player.state.frameCount, 118);
    for (const r of o.files.reads) if (r.path === o.built.cameras[0].mkv) assert.ok(r.end <= mkvCut, 'no byte past the snapshot');
});

test('T-PLAY-71 write_error_short: a short file with no dead camera', async t => {
    const o = await openFixture(t, 'write_error_short');
    assert.equal(o.player.state.frameCount, 120);
    const c3 = o.player.state.cameras[3];
    assert.equal(c3.state, 'repaired');
    assert.equal(c3.deadFrom, null);
    for (const k of [80, 119]) {
        await seek(o, k);
        assert.equal(o.shown(3).identity?.row, 79);
        assert.deepEqual(o.shown(3).mark, {kind: 'no_frame'}, 'never camera lost');
    }
    await seek(o, 79);
    assert.equal(o.shown(3).identity?.row, 79);
    assert.ok(o.player.state.take.warnings.includes('camera_file_short'));
    assert.ok(o.player.state.take.warnings.includes('take_error'));
});
