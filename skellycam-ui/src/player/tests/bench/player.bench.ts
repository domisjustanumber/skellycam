// The benchmarks T-PLAY-65 to T-PLAY-70 (specs/player.md sections 11.3 and 12.3). They run by hand on
// the Windows test machine (playwright.player-bench.config.ts), not in CI. Each one writes its result
// as JSON to PLAYER_BENCH_OUT. A missed target is a soft failure: it goes to the user and does not stop
// step 6a by itself [agent 36]. JPEGs: 60 distinct Chromium JPEGs per camera, used in turn, so the
// barcode holds the row modulo 60.
import {expect} from '@playwright/test';
import type {ElectronApplication} from '@playwright/test';
import {mkdirSync, writeFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {harnessTest} from '../browser/harness.ts';
import type {Harness} from '../browser/harness.ts';
import {defaultTake} from '../fixtures/take.ts';
import type {RowPlan} from '../fixtures/take.ts';
import {patternBytes} from '../fixtures/take-files-checks.ts';

const test = harnessTest('harness');
const UI = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..');
const OUT = process.env.PLAYER_BENCH_OUT ?? path.join(UI, 'test-results', 'player-bench', 'results');
const CYCLE = 60;

function record(id: string, result: unknown) {
    mkdirSync(OUT, {recursive: true});
    writeFileSync(path.join(OUT, `${id}.json`), JSON.stringify({id, at: new Date().toISOString(), platform: process.platform, result}, null, 2));
}

interface Metrics {
    cpuPercentByType: Record<string, number>;   // percent of one core, summed by process type
    workingSetMB: number;
}

/** Electron process metrics over `run`: CPU by process type, and the largest working set. The CPU is the
 * change of `cumulativeCPUUsage` over the whole run; `percentCPUUsage` covered only the interval since
 * the last sample of the timer (at most 1 s). */
async function measure<T>(app: ElectronApplication, run: () => Promise<T>): Promise<{result: T; metrics: Metrics}> {
    const sample = () => app.evaluate(({app: a}) => a.getAppMetrics().map(m => ({pid: m.pid, type: m.type, cpu: m.cpu.cumulativeCPUUsage ?? 0, ws: m.memory.workingSetSize})));
    const first = await sample();
    const t0 = performance.now();
    let peak = 0;
    const timer = setInterval(() => void sample().then(s => (peak = Math.max(peak, s.reduce((a, m) => a + m.ws, 0) / 1024))), 1000);
    const result = await run();
    clearInterval(timer);
    const end = await sample();
    const seconds = (performance.now() - t0) / 1000;
    const cpuPercentByType: Record<string, number> = {};
    for (const m of end) {
        const before = first.find(f => f.pid === m.pid)?.cpu ?? 0;
        cpuPercentByType[m.type] = (cpuPercentByType[m.type] ?? 0) + (100 * (m.cpu - before)) / seconds;
    }
    return {result, metrics: {cpuPercentByType, workingSetMB: Math.max(peak, end.reduce((a, m) => a + m.ws, 0) / 1024)}};
}

type Geometry = Awaited<ReturnType<Window['bench']['layout']>>;

/** Lay out the tiles in a grid and size the window, so that each tile is in the window for the observer. */
async function layout(h: Harness, n: number): Promise<Geometry> {
    const cols = n === 1 ? 1 : n <= 4 ? 2 : 4;
    const width = cols * 520 + 20;
    await h.app.evaluate(({BrowserWindow}, [w, hh]) => BrowserWindow.getAllWindows()[0].setContentSize(w, hh), [width, Math.ceil(n / cols) * 264 + 40] as const);
    await h.page.waitForFunction(w => innerWidth === w, width);
    return h.page.evaluate(c => window.bench.layout(c), cols);
}

/** The observer outside the page: the main process takes each composited frame of the window
 * (`beginFrameSubscription`, about 30 frames/s, so a time resolution of about 33 ms) and reads from it the
 * reference strip (k*) and the barcode of each tile. */
async function observe(app: ElectronApplication, geo: Geometry) {
    await app.evaluate(({BrowserWindow}, g) => {
        const G = globalThis as never as {__observed: number[][]};
        G.__observed = [];
        BrowserWindow.getAllWindows()[0].webContents.beginFrameSubscription(false, image => {
            const s = image.getSize().width / g.innerWidth;
            const out = [performance.timeOrigin + performance.now()];
            for (const pts of [g.ref, ...g.tiles]) {
                const x0 = Math.floor(pts[0][0] * s);
                const bmp = image.crop({x: x0, y: Math.round(pts[0][1] * s), width: Math.ceil(pts[pts.length - 1][0] * s) - x0 + 1, height: 1}).toBitmap();
                let v = 0;
                for (const [x] of pts) {
                    const i = (Math.round(x * s) - x0) * 4;
                    v = v * 2 + ((bmp[i] + bmp[i + 1] + bmp[i + 2]) / 3 > 128 ? 1 : 0);
                }
                out.push(v);
            }
            G.__observed.push(out);
        });
    }, geo);
}

/** Stop the observer. For each tile: the percent of the frames in [from, to] that show the image of k*. */
async function observed(app: ElectronApplication, from: number, to: number) {
    const frames = (await app.evaluate(({BrowserWindow}) => {
        BrowserWindow.getAllWindows()[0].webContents.endFrameSubscription();
        return (globalThis as never as {__observed: number[][]}).__observed;
    })).filter(f => f[0] >= from && f[0] <= to);
    const n = frames.length ? frames[0].length - 2 : 0;
    // a tile value is the camera index in 4 bits, then the position in 12 bits
    const shownPercent = Array.from({length: n}, (_, i) =>
        (100 * frames.filter(f => (f[i + 2] & 4095) === f[1] % CYCLE && f[i + 2] >> 12 === i % 16).length) / Math.max(1, frames.length));
    return {frames: frames.length, framesPerSecond: frames.length / ((to - from) / 1000), shownPercent};
}

/** Play for `seconds` and measure: the page draws k* at each refresh, the observer reads the tiles. */
async function watchPlay(h: Harness, geo: Geometry, seconds: number) {
    await observe(h.app, geo);
    await h.page.evaluate(() => window.harness.command('play'));
    const {result: w, metrics} = await measure(h.app, () => h.page.evaluate(s => window.bench.watch(s, 1), seconds));
    const o = await observed(h.app, w.from, w.to);
    return {refreshes: w.refreshes, refreshesPerSecond: w.refreshesPerSecond, observerFrames: o.frames, observerFramesPerSecond: o.framesPerSecond, shownPercent: o.shownPercent, metrics};
}

const totalCores = (m: Metrics) => Object.values(m.cpuPercentByType).reduce((a, b) => a + b, 0) / 100;

/** A take of `n` cameras of Chromium JPEGs at `width` x `height` and `fps`, `seconds` long. */
async function benchTake(h: Harness, name: string, n: number, width: number, height: number, fps: number, seconds: number) {
    const rows = fps * seconds;
    const plan = defaultTake(name, n, rows);
    const period = BigInt(Math.round(1e9 / fps));
    for (const cam of plan.cameras) {
        const {base64} = await h.page.evaluate(([c, w, hh]) => window.bench.jpegs(c, 60, w, hh), [cam.index, width, height] as const);
        const jpegs = base64.map(b => new Uint8Array(Buffer.from(b, 'base64')));
        cam.rate = [fps, 1];
        cam.fit = [{posFirst: 0, posLast: rows - 1, t0: 10_000_000n, periodPs: period * 1000n}];
        cam.rows = Array.from({length: rows}, (_, k): RowPlan => ({kind: 'real', sfn: 1000n + BigInt(k), arrival: 10_000_000n + BigInt(k) * period, payload: jpegs[k % CYCLE]}));
    }
    const built = h.build(plan);
    await h.page.evaluate(([w, hh]) => window.bench.setImageSize(w, hh), [width, height] as const);
    // closePlayer keeps the canvases of the take before
    await h.page.evaluate(() => document.querySelectorAll('#tiles canvas').forEach(c => c.remove()));
    await h.page.evaluate(f => window.harness.openPlayer(f), built.dir);
    return layout(h, n);
}

test('T-PLAY-65 transport: 16 readers x 60 fps x 150 kB for 60 s through the handler', async ({harness: h}) => {
    await h.requireProduct();
    const folder = path.join(h.recordings, 'transport');
    mkdirSync(path.join(folder, 'synchronized_videos'), {recursive: true});
    writeFileSync(path.join(folder, 'synchronized_videos', 't.mkv'), patternBytes(1, 0, 64 * 1024 * 1024));
    const opened = await h.page.evaluate(f => (window as never as {skellycamTake: {open(f: string): Promise<{token: string}>}}).skellycamTake.open(f), folder);
    const url = `skellycam-take://${opened.token}/synchronized_videos/t.mkv`;
    const {result, metrics} = await measure(h.app, () => h.page.evaluate(u => window.bench.transport(u, 64 * 1024 * 1024, 16, 60, 150_000, 60), url));
    record('T-PLAY-65', {...result, metrics});
    expect.soft(result.droppedPercent, 'target: at most 0.5 % dropped ticks').toBeLessThanOrEqual(0.5);
});

test('T-PLAY-66 play N = 4 and N = 8, 1080p30, 60 s', async ({harness: h}) => {
    test.setTimeout(60 * 60_000);
    await h.requireProduct();
    for (const n of [4, 8]) {
        const geo = await benchTake(h, `play_${n}`, n, 1920, 1080, 30, 62);
        const result = await watchPlay(h, geo, 60);
        const {metrics} = result;
        await h.page.evaluate(() => window.harness.closePlayer());
        record(`T-PLAY-66-N${n}`, result);
        if (n === 8) {
            for (const p of result.shownPercent) expect.soft(p, 'target: 99 % of refreshes (observer frames)').toBeGreaterThanOrEqual(99);
            expect.soft(totalCores(metrics), 'target: at most 2.0 cores').toBeLessThanOrEqual(2.0);
            expect.soft(metrics.workingSetMB, 'target: at most 1.5 GB').toBeLessThanOrEqual(1536);
        }
    }
});

test('T-PLAY-67 200 seeks at N = 1, 4 and 8', async ({harness: h}) => {
    test.setTimeout(30 * 60_000);
    await h.requireProduct();
    const results: Record<string, unknown> = {};
    for (const n of [1, 4, 8]) {
        await benchTake(h, `seek_${n}`, n, 1920, 1080, 30, 20);
        const r = await h.page.evaluate(() => window.bench.seeks(200, 600, 60));
        await h.page.evaluate(() => window.harness.closePlayer());
        results[`N${n}`] = r;
        if (n === 4) {
            expect.soft(r.p50, 'target: p50 at most 10 ms').toBeLessThanOrEqual(10);
            expect.soft(r.p95, 'target: p95 at most 33 ms').toBeLessThanOrEqual(33);
        }
    }
    record('T-PLAY-67', results);
});

test('T-PLAY-68 scrub at 90 frames/s for 8 s at N = 4 and 8', async ({harness: h}) => {
    test.setTimeout(30 * 60_000);
    await h.requireProduct();
    const results: Record<string, unknown> = {};
    for (const n of [4, 8]) {
        await benchTake(h, `scrub_${n}`, n, 1920, 1080, 30, 30);
        const {result, metrics} = await measure(h.app, () => h.page.evaluate(() => window.bench.scrub(8, 90, 900, 60)));
        await h.page.evaluate(() => window.harness.closePlayer());
        results[`N${n}`] = {...result, metrics};
        if (n === 8) for (const s of result.shownPerSecond) expect.soft(s, 'target: at least 50 shown frames/s').toBeGreaterThanOrEqual(50);
    }
    record('T-PLAY-68', results);
});

test('T-PLAY-69 IPC round trips while the transport case runs', async ({harness: h}) => {
    await h.requireProduct();
    const folder = path.join(h.recordings, 'transport_ipc');
    mkdirSync(path.join(folder, 'synchronized_videos'), {recursive: true});
    writeFileSync(path.join(folder, 'synchronized_videos', 't.mkv'), patternBytes(1, 0, 64 * 1024 * 1024));
    const opened = await h.page.evaluate(f => (window as never as {skellycamTake: {open(f: string): Promise<{token: string}>}}).skellycamTake.open(f), folder);
    const url = `skellycam-take://${opened.token}/synchronized_videos/t.mkv`;
    // the main-process event loop: the delay of a 10 ms timer
    await h.app.evaluate(() => {
        const g = globalThis as never as {__lag: number[]};
        g.__lag = [];
        let last = Date.now();
        setInterval(() => {
            const now = Date.now();
            g.__lag.push(now - last - 10);
            last = now;
        }, 10);
    });
    const [transport, ipc] = await h.page.evaluate(async u => Promise.all([
        window.bench.transport(u, 64 * 1024 * 1024, 16, 60, 150_000, 60),
        window.bench.ipc(60, () => window.harnessIpc.invoke('harness:product-error')),
    ]), url);
    const lag = await h.app.evaluate(() => {
        const l = [...(globalThis as never as {__lag: number[]}).__lag].sort((a, b) => a - b);
        return {p50: l[Math.floor(l.length / 2)], p95: l[Math.floor(l.length * 0.95)], max: l.at(-1)};
    });
    record('T-PLAY-69', {transport, ipc, mainLoopLagMs: lag});
    expect.soft(ipc.p95, 'target: IPC round trip p95 at most 50 ms').toBeLessThanOrEqual(50);
});

test('T-PLAY-70 cases that nobody measured: 720p60 N = 4, 720p30 N = 16, speed 8 N = 4', async ({harness: h}) => {
    test.setTimeout(60 * 60_000);
    await h.requireProduct();
    const results: Record<string, unknown> = {};
    const cases: [string, number, number, number, number, number][] = [
        ['720p60_N4', 4, 1280, 720, 60, 1], ['720p30_N16', 16, 1280, 720, 30, 1], ['1080p30_N4_speed8', 4, 1920, 1080, 30, 8],
    ];
    for (const [id, n, w, hh, fps, speed] of cases) {
        const geo = await benchTake(h, id, n, w, hh, fps, speed === 8 ? 62 : 32);
        await h.page.evaluate(s => window.harness.command('setSpeed', s), speed);
        results[id] = await watchPlay(h, geo, speed === 8 ? 7 : 30);
        await h.page.evaluate(() => window.harness.closePlayer());
    }
    record('T-PLAY-70', results);
});
