// Unit tests of the clock, the frame choice and the scheduling: T-PLAY-29 to T-PLAY-34 and T-PLAY-38
// (specs/player.md sections 7 and 9).
import assert from 'node:assert/strict';
import test from 'node:test';
import type {TileMark} from '../../index.ts';
import {defaultTake, referenceTimes} from '../fixtures/take.ts';
import type {TakePlan} from '../fixtures/take.ts';
import {planOf} from '../fixtures/takes.ts';
import {fakeCanvas, FakeLoop, openFixture, player, product, seek, settle, spyFiles, tempRoot, testDecoder} from './helpers.ts';
import {nodeTakeFiles} from '../fixtures/node-take-files.ts';
import {writeTake} from '../fixtures/take.ts';

type Choose = typeof import('../../clock/choose.ts');
const choose = () => product<Choose>('clock/choose.ts');

const RATES = [0.1, 0.25, 0.5, 1, 1.5, 2, 4, 8];

// ---- brute-force references, written apart from the product ----

function refT(times: (number | null)[][], K: number): number[] {
    const all = times.flat().filter((v): v is number => v !== null);
    const out: number[] = [];
    for (let k = 0; k < K; k++) {
        const here = times.map(c => c[k]).filter((v): v is number => v !== null);
        const prev = k === 0 ? (here.length ? -Infinity : Math.min(...all)) : out[k - 1];
        out.push(Math.max(prev, ...here));
    }
    return out;
}

function refImage(times: (number | null)[], missing: boolean[], t: number, K: number): number | null {
    let run = -Infinity;
    let best: number | null = null;
    for (let k = 0; k < K; k++) {
        if (times[k] !== null) run = Math.max(run, times[k]!);
        if (!missing[k] && times[k] !== null && run <= t) best = k;
    }
    return best;
}

function refFrame(T: number[], t: number): number {
    let k = 0;
    for (let i = 0; i < T.length; i++) if (T[i] <= t) k = i;
    return k;
}

function refMark(missing: boolean[], deadFrom: number | null, k: number): TileMark | null {
    if (!missing[k]) return null;
    return deadFrom !== null && k >= deadFrom ? {kind: 'camera_lost', frame: deadFrom} : {kind: 'no_frame'};
}

const timesOf = (plan: TakePlan) => plan.cameras.map(c => referenceTimes(c).map(v => (v === null ? null : Number(v))));
const missingOf = (plan: TakePlan) => plan.cameras.map(c => c.rows.map(r => r.kind !== 'real'));

test('T-PLAY-29 frame choice on fixed lists', async () => {
    const {chooseImage} = await choose();
    const times = [100, 200, 200, 350, 400, 500];
    const missing = [false, false, false, false, true, false];
    const cases: [number, number | null][] = [
        [99, null], [100, 0], [101, 0], [199, 0], [200, 2], [201, 2], [349, 2], [350, 3], [351, 3],
        [450, 3], [499, 3], [500, 5], [501, 5], [1e12, 5],
    ];
    for (const [t, want] of cases) assert.equal(chooseImage(times, missing, t, 6), want, `t = ${t}`);
    assert.equal(chooseImage(times, missing, 1e12, 4), 3, 'only rows below K');
    // irregular times: a choice by index x rate would give another row
    assert.equal(chooseImage([0, 10, 1000, 1001], [false, false, false, false], 500, 4), 1);
    // a missing row with no time is not a candidate and has no time
    assert.equal(chooseImage([100, null, 300], [false, true, false], 250, 3), 0);
    // a decreasing time: the running maximum
    assert.equal(chooseImage([100, 300, 200, 400], [false, false, false, false], 250, 4), 0);
    assert.equal(chooseImage([100, 300, 200, 400], [false, false, false, false], 300, 4), 2);
});

test('T-PLAY-30 T_k on offsets and steps', async t => {
    const plan = planOf('offsets');
    const T = refT(timesOf(plan), 120);
    assert.equal(T[50], T[51], 'the fixture has two equal values of T_k');
    const o = await openFixture(t, plan);
    for (let k = 0; k < 120; k++) {
        await seek(o, k);
        assert.equal(o.player.state.time, T[k], `T_${k}`);
    }
    const steps: [number, number, number][] = [
        [49, 1, 50], [50, 1, 51], [51, -1, 50], [50, -1, 49], [49, 10, 59], [59, -10, 49], [45, 10, 55],
        [0, -1, 0], [0, -10, 0], [5, -10, 0], [119, 1, 119], [119, 10, 119], [115, 10, 119],
    ];
    for (const [from, n, want] of steps) {
        await seek(o, from);
        o.player.step(n);
        await o.settle();
        assert.equal(o.player.state.frame, want, `step(${n}) from ${from}`);
        assert.equal(o.player.state.time, T[want]);
    }
    await seek(o, 500);
    assert.equal(o.player.state.frame, 119);
    await seek(o, -5);
    assert.equal(o.player.state.frame, 0);
});

test('T-PLAY-31 the clock: rates, the end, the loop, play at the end, pause', async t => {
    const o = await openFixture(t, 'normal');
    const T = refT(timesOf(o.built.plan), 120);
    for (const rate of RATES) {
        await seek(o, 10);
        o.player.setSpeed(rate);
        o.player.play();
        o.loop.refresh(16);
        const t1 = o.player.state.time;
        o.loop.refresh(100);
        const t2 = o.player.state.time;
        assert.ok(Math.abs(t2 - t1 - rate * 100_000_000) <= 1, `rate ${rate}: t advances by rate x elapsed`);
        assert.ok(Number.isInteger(t2), 'whole nanoseconds');
        o.player.pause();
    }
    o.player.setSpeed(1);
    // end with loop off
    await seek(o, 117);
    o.player.play();
    for (let i = 0; i < 20 && o.player.state.playing; i++) o.loop.refresh(50);
    assert.equal(o.player.state.playing, false);
    assert.equal(o.player.state.frame, 119);
    // play at the last frame starts from frame 0
    o.player.play();
    assert.equal(o.player.state.frame, 0);
    assert.equal(o.player.state.time, T[0]);
    assert.equal(o.player.state.playing, true);
    o.player.pause();
    // loop on
    o.player.setLoop(true);
    await seek(o, 118);
    o.player.play();
    let wrapped = false;
    for (let i = 0; i < 20; i++) {
        o.loop.refresh(50);
        if (o.player.state.frame < 118) wrapped = true;
    }
    assert.ok(wrapped, 'loop: frame 0 after the end');
    assert.equal(o.player.state.playing, true);
    o.player.setLoop(false);
    // pause sets t = T_k*
    o.loop.refresh(20);
    o.player.pause();
    assert.equal(o.player.state.time, T[o.player.state.frame]);
});

test('T-PLAY-32 100 seeks in 200 ms to one tile: newest wins', async t => {
    const {openTake, Tile} = await player();
    const built = writeTake(tempRoot(t), defaultTake('seeks'));
    const files = spyFiles(await nodeTakeFiles(built.dir));
    const loop = new FakeLoop();
    const p = await openTake(files, {frameLoop: loop.frameLoop, decode: testDecoder(built).decode});
    t.after(() => p.close());
    const tileDecoder = testDecoder(built, () => 1 + Math.floor(Math.random() * 30));
    const c = fakeCanvas();
    const tile = new Tile(c.canvas, {}, {decode: tileDecoder.decode});
    t.after(() => tile.close());
    p.attachTile(0, tile);
    await settle(files);
    const targets = Array.from({length: 119}, (_, i) => i + 1).sort(() => Math.random() - 0.5).slice(0, 100);
    const drawnBefore = c.drawn().length;
    for (const k of targets) {
        p.seekFrame(k);
        await new Promise(r => setTimeout(r, 2));
    }
    await settle(files);
    await new Promise(r => setTimeout(r, 200));
    assert.ok(tileDecoder.maxInFlight() <= 1, 'at most one decode in flight');
    const drawn = c.drawn().slice(drawnBefore).map(img => img.identity?.row);
    assert.equal(drawn.at(-1), targets.at(-1), 'the tile shows the last target');
    const order = drawn.map(row => targets.indexOf(row!));
    for (let i = 1; i < order.length; i++) assert.ok(order[i] > order[i - 1], 'no draw of an older request after a newer draw');
});

test('T-PLAY-33 play at rates 1 and 8 with a slow decoder', async t => {
    const {openTake, Tile} = await player();
    const built = writeTake(tempRoot(t), defaultTake('slow'));
    for (const rate of [1, 8]) {
        const files = spyFiles(await nodeTakeFiles(built.dir));
        const loop = new FakeLoop();
        const decoder = testDecoder(built, () => 20);
        const p = await openTake(files, {frameLoop: loop.frameLoop, decode: decoder.decode});
        const canvases = p.state.cameras.map(() => fakeCanvas());
        const tiles = canvases.map(c => new Tile(c.canvas, {}, {decode: decoder.decode}));
        tiles.forEach((tile, i) => p.attachTile(i, tile));
        await settle(files);
        p.setSpeed(rate);
        p.play();
        for (let i = 0; i < 60; i++) {
            loop.refresh(1000 / 60);
            await new Promise(r => setTimeout(r, 5));
        }
        p.pause();
        await settle(files);
        for (const [i, c] of canvases.entries()) {
            const rows = c.drawn().map(img => img.identity!.row!);
            for (let j = 1; j < rows.length; j++) assert.ok(rows[j] >= rows[j - 1], `rate ${rate} camera ${i}: the drawn position never goes down`);
        }
        await p.close();
        tiles.forEach(tile => tile.close());
        assert.equal(decoder.open(), 0, `rate ${rate}: each image is closed`);
    }
});

test('T-PLAY-34 456 shuffled ticks against a brute-force reference', async () => {
    const {chooseImage, frameTimes, frameAt, chooseMark} = await choose();
    for (const name of ['offsets', 'missing']) {
        const plan = planOf(name);
        const times = timesOf(plan);
        const missing = missingOf(plan);
        const K = 120;
        const T = refT(times, K);
        assert.deepEqual(frameTimes(times, K), T, `${name}: T_k`);
        const ticks: number[] = [];
        let seed = 7;
        const rnd = () => (seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31;
        const pick = () => Math.floor(rnd() * K);
        while (ticks.length < 456) {
            const k = pick();
            const c = Math.floor(rnd() * times.length);
            const base = times[c][k] ?? T[k];
            const forms = [base, base - 1, base + 1, base - 1_000_000, base + 1_000_000, (T[k] + T[Math.min(K - 1, k + 1)]) / 2, T[0] - 5, T[K - 1] + 5];
            ticks.push(Math.round(forms[ticks.length % forms.length]));
        }
        // inside the missing runs of camera 1 (rows 40 to 59 of `missing`)
        for (let k = 40; k < 60 && name === 'missing'; k++) ticks[k] = T[k] + 7;
        ticks.sort(() => rnd() - 0.5);
        for (const t of ticks) {
            const kStar = refFrame(T, t);
            assert.equal(frameAt(T, t), kStar, `${name} t=${t}: k*`);
            for (let c = 0; c < times.length; c++) {
                assert.equal(chooseImage(times[c], missing[c], t, K), refImage(times[c], missing[c], t, K), `${name} t=${t} camera ${c}: image`);
                assert.deepEqual(chooseMark(missing[c], null, kStar), refMark(missing[c], null, kStar), `${name} t=${t} camera ${c}: mark`);
            }
        }
    }
});

test('T-PLAY-38 open images for N = 4 and N = 16; none after close', async t => {
    const {openTake, Tile} = await player();
    for (const [n, rows] of [[4, 60], [16, 30]]) {
        const built = writeTake(tempRoot(t), defaultTake(`memory_${n}`, n, rows));
        const files = spyFiles(await nodeTakeFiles(built.dir));
        const loop = new FakeLoop();
        const decoder = testDecoder(built, () => 2);
        const p = await openTake(files, {frameLoop: loop.frameLoop, decode: decoder.decode});
        const tiles = p.state.cameras.map(() => new Tile(fakeCanvas().canvas, {}, {decode: decoder.decode}));
        tiles.forEach((tile, i) => p.attachTile(i, tile));
        const limit = Math.min(8, Math.max(2, Math.floor(64 / n))) + 2;
        const check = (when: string) => {
            for (let c = 0; c < n; c++) assert.ok(decoder.open(c) <= limit, `N = ${n} ${when}: camera ${c} has ${decoder.open(c)} open images, limit ${limit}`);
        };
        await settle(files);
        check('after open');
        p.play();
        for (let i = 0; i < 30; i++) {
            loop.refresh(1000 / 60);
            await new Promise(r => setTimeout(r, 3));
            check('during play');
        }
        p.pause();
        for (const k of [3, rows - 2, 10, 0, rows - 1]) {
            p.seekFrame(k);
            await settle(files);
            check('after a seek');
        }
        await p.close();
        tiles.forEach(tile => tile.close());
        assert.equal(decoder.open(), 0, `N = ${n}: 0 open images after close`);
    }
});

test('T-PLAY-73 seeks faster than decodes: the tile draws each newest finished image', async t => {
    const {openTake, Tile} = await player();
    const built = writeTake(tempRoot(t), defaultTake('fast_seeks'));
    const files = spyFiles(await nodeTakeFiles(built.dir));
    const decoder = testDecoder(built, () => 30);
    const p = await openTake(files, {frameLoop: new FakeLoop().frameLoop, decode: decoder.decode});
    t.after(() => p.close());
    const c = fakeCanvas();
    const tile = new Tile(c.canvas, {}, {decode: decoder.decode});
    t.after(() => tile.close());
    p.attachTile(0, tile);
    await settle(files);
    const before = c.drawn().length;
    // one seek each 5 ms, a decode takes 30 ms (7.5)
    for (let k = 1; k <= 40; k++) {
        p.seekFrame(k);
        await new Promise(r => setTimeout(r, 5));
    }
    const duringSeeks = c.drawn().slice(before).map(img => img.identity!.row!);
    await settle(files);
    await new Promise(r => setTimeout(r, 100));
    const rows = c.drawn().slice(before).map(img => img.identity!.row!);
    assert.ok(duringSeeks.length >= 3, `the tile advances during the seeks: ${duringSeeks}`);
    for (let i = 1; i < rows.length; i++) assert.ok(rows[i] > rows[i - 1], `never an older request after a newer one: ${rows}`);
    assert.equal(rows.at(-1), 40, 'the tile ends on the last sought frame');
});
