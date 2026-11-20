// Component tests of the player with real tiles, the Electron TakeFiles and the real handler:
// T-PLAY-46 to T-PLAY-50, T-PLAY-54 and T-PLAY-72 (specs/player.md sections 6, 7 and 8).
import {expect} from '@playwright/test';
import {referenceTimes} from '../fixtures/take.ts';
import type {BuiltTake, TakePlan} from '../fixtures/take.ts';
import {planOf} from '../fixtures/takes.ts';
import {harnessTest} from './harness.ts';
import type {Harness} from './harness.ts';

const test = harnessTest('harness');

type Reading = {camera: number; position: number; black: boolean; mark: string | null};

async function open(h: Harness, plan: TakePlan | string, initialFrame?: number): Promise<BuiltTake> {
    await h.requireProduct();
    const built = h.build(plan);
    await h.page.evaluate(([folder, k]) => window.harness.openPlayer(folder as string, k as number | undefined), [built.dir, initialFrame] as const);
    return built;
}

const tile = (h: Harness, i: number): Promise<Reading> => h.page.evaluate(n => window.harness.readPlayerTile(n), i);
const state = (h: Harness) => h.page.evaluate(() => window.harness.state());
const command = (h: Harness, name: string, ...args: unknown[]) => h.page.evaluate(([n, a]) => window.harness.command(n as never, ...(a as unknown[])), [name, args] as const);

async function seekAndExpect(h: Harness, k: number, camera: number, want: Partial<Reading>) {
    await command(h, 'seekFrame', k);
    await expect.poll(() => tile(h, camera), {message: `k* = ${k} camera ${camera}`}).toMatchObject(want);
}

async function playToEnd(h: Harness, maxMs = 60_000) {
    await expect.poll(async () => (await state(h)).playing, {timeout: maxMs}).toBe(false);
}

function refT(plan: TakePlan): number[] {
    const times = plan.cameras.map(c => referenceTimes(c).map(v => (v === null ? null : Number(v))));
    const all = times.flat().filter((v): v is number => v !== null);
    const out: number[] = [];
    for (let k = 0; k < plan.cameras[0].rows.length; k++) {
        const here = times.map(c => c[k]).filter((v): v is number => v !== null);
        out.push(Math.max(k === 0 ? (here.length ? -Infinity : Math.min(...all)) : out[k - 1], ...here));
    }
    return out;
}

test('T-PLAY-46 player on missing: no frame, never the placeholder', async ({harness: h}) => {
    await open(h, 'missing');
    await seekAndExpect(h, 9, 1, {position: 9, mark: null});
    await seekAndExpect(h, 10, 1, {position: 9, black: false, mark: 'no frame'});
    for (let k = 40; k <= 59; k++) await seekAndExpect(h, k, 1, {position: 39, black: false, mark: 'no frame'});
    await seekAndExpect(h, 0, 1, {black: true, mark: 'no frame'});
    await h.page.evaluate(() => window.harness.closePlayer());
});

test('T-PLAY-47 player on dead and dead_no_manifest: camera lost at frame 70', async ({harness: h}) => {
    for (const name of ['dead', 'dead_no_manifest']) {
        await open(h, name);
        await seekAndExpect(h, 69, 2, {position: 69, mark: null});
        await seekAndExpect(h, 70, 2, {position: 69, mark: 'camera lost at frame 70'});
        await seekAndExpect(h, 119, 2, {position: 69, mark: 'camera lost at frame 70'});
        await h.page.evaluate(() => window.harness.closePlayer());
    }
});

test('T-PLAY-48 unfinished and recording_finished: the mark and the end of play', async ({harness: h}) => {
    for (const name of ['unfinished', 'recording_finished']) {
        const built = await open(h, name);
        for (let i = 0; i < built.plan.cameras.length; i++) await expect.poll(() => tile(h, i), {message: `${name} camera ${i}`}).toMatchObject({mark: 'unfinished'});
        await command(h, 'setSpeed', 8);
        await command(h, 'play');
        await playToEnd(h);
        expect((await state(h)).frame).toBe(name === 'unfinished' ? 96 : 119);
        await h.page.evaluate(() => window.harness.closePlayer());
    }
});

test('T-PLAY-49 offsets and missing: 456 ticks through seekFrame and the clock, real handler', async ({harness: h}) => {
    test.setTimeout(300_000);
    for (const name of ['offsets', 'missing']) {
        const plan = planOf(name);
        await open(h, plan);
        const T = refT(plan);
        const times = plan.cameras.map(c => referenceTimes(c).map(v => (v === null ? null : Number(v))));
        // the ticks of T-PLAY-34, as frame numbers: the player has no seek to a time, so each tick
        // goes through seekFrame(k*) and the clock gives t = T_k*
        let seed = 7;
        const rnd = () => (seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31;
        const ticks = Array.from({length: 456}, (_, i) => {
            const k = Math.floor(rnd() * 120);
            const base = times[Math.floor(rnd() * times.length)][k] ?? T[k];
            return Math.round([base, base - 1, base + 1, base - 1_000_000, base + 1_000_000][i % 5]);
        });
        for (const t of ticks) {
            let k = 0;
            T.forEach((v, i) => (v <= t ? (k = i) : 0));
            await command(h, 'seekFrame', k);
            for (const [c, cam] of plan.cameras.entries()) {
                let run = -Infinity;
                let row: number | null = null;
                times[c].forEach((p, r) => {
                    if (p !== null) run = Math.max(run, p);
                    if (cam.rows[r].kind === 'real' && p !== null && run <= T[k]) row = r;
                });
                const mark = cam.rows[k].kind === 'real' ? null : 'no frame';
                await expect.poll(() => tile(h, c), {message: `${name} t=${t} k*=${k} camera ${c}`})
                    .toMatchObject(row === null ? {black: true, mark} : {position: row, mark});
            }
        }
        await h.page.evaluate(() => window.harness.closePlayer());
    }
});

test('T-PLAY-50 normal: play, pause, the end and the loop', async ({harness: h}) => {
    const built = await open(h, 'normal');
    const T = refT(built.plan);
    await command(h, 'play');
    await h.page.waitForTimeout(3000);
    await command(h, 'pause');
    const s = await state(h);
    expect(s.time).toBe(T[s.frame]);
    for (let c = 0; c < 4; c++) await expect.poll(() => tile(h, c)).toMatchObject({position: s.frame});
    await command(h, 'play');
    await playToEnd(h);
    expect((await state(h)).frame).toBe(119);
    await command(h, 'setLoop', true);
    await command(h, 'seekFrame', 110);
    await command(h, 'play');
    await expect.poll(async () => (await state(h)).frame, {timeout: 5000}).toBeLessThan(30);
    expect((await state(h)).playing).toBe(true);
    await command(h, 'pause');
    await h.page.evaluate(() => window.harness.closePlayer());
});

test('T-PLAY-54 damaged, not readable and read error marks; the other tiles keep playing', async ({harness: h}) => {
    await open(h, 'bad_crc');
    await expect.poll(() => tile(h, 1)).toMatchObject({mark: 'damaged at frame 50'});
    await h.page.evaluate(() => window.harness.closePlayer());

    await open(h, 'counts_refused');
    await expect.poll(() => tile(h, 2)).toMatchObject({mark: 'camera file not readable: bad_rotation'});
    await h.page.evaluate(() => window.harness.closePlayer());

    const built = await open(h, 'normal');
    await command(h, 'play');
    await h.page.waitForTimeout(500);
    await h.app.evaluate((_e, p) => (globalThis as never as {__harness: {setReadFault(p: string): void}}).__harness.setReadFault(p), built.cameras[3].mkv);
    await expect.poll(() => tile(h, 3), {timeout: 5000}).toMatchObject({black: false, mark: 'read error'});
    const before = await Promise.all([0, 1, 2].map(c => tile(h, c)));
    await h.page.waitForTimeout(700);
    const after = await Promise.all([0, 1, 2].map(c => tile(h, c)));
    for (const c of [0, 1, 2]) expect(after[c].position, `camera ${c} keeps playing`).toBeGreaterThan(before[c].position);
    await command(h, 'pause');
    await h.page.evaluate(() => window.harness.closePlayer());
});

test('T-PLAY-72 player on write_error_short: camera 3 holds row 79 with no frame', async ({harness: h}) => {
    await open(h, 'write_error_short', 70);
    await command(h, 'play');
    const seen: Reading[] = [];
    while ((await state(h)).playing) {
        const s = await state(h);
        const r = await tile(h, 3);
        if (s.frame >= 81) seen.push(r);
        await h.page.waitForTimeout(50);
    }
    expect((await state(h)).frame).toBe(119);
    expect(seen.length).toBeGreaterThan(0);
    for (const r of seen) expect(r).toMatchObject({position: 79, mark: 'no frame'});
    for (const c of [0, 1, 2]) await expect.poll(() => tile(h, c)).toMatchObject({position: 119});
    await h.page.evaluate(() => window.harness.closePlayer());
});
