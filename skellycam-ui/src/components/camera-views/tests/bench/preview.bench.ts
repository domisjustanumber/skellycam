// The benchmarks T-PRV-51 and T-PRV-52 of the step 4b preview (specs/preview-4b.md section 6): 8 cameras on the
// main-thread tile at 1080p30 and 1080p60. They run by hand on the Windows test machine
// (playwright.player-bench.config.ts), not in CI. Each one writes its result as JSON to PLAYER_BENCH_OUT. A missed
// target is a soft failure: it goes to the user, and section 6.4 applies.
//
// The observers (6.1): the outside observer (beginFrameSubscription of the main process); the ready messages and
// the send-to-ready times that ui_server.py counts; TaskDuration of the page through CDP; the claim of the product
// (`drawnCount`), read only at the end of a run and never given as an outside proof.
import {expect} from '@playwright/test';
import type {ElectronApplication} from '@playwright/test';
import {mkdirSync, writeFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {observe, readings} from '../../../../player/tests/harness/observer.ts';
import {counts, connectionNumbers, geometry, PreviewKit, requirePreviewTiles, sleep, test, toCaptures, waitDrawn, written} from '../browser/preview-kit.ts';
import type {Capture} from '../browser/preview-kit.ts';

const UI = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../../..');
const OUT = process.env.PLAYER_BENCH_OUT ?? path.join(UI, 'test-results', 'player-bench', 'results');
const RUNS = 3;
const WARMUP_MS = 2_000;
const MEASURE_MS = 60_000;
const SIZE: [number, number] = [1920, 1080];
const TARGET_BYTES = 190_000;
const CYCLE = 60;
// 8 cameras; the camera list numbers differ from the order of the ids
const CAMS = [3, 1, 4, 8, 5, 2, 7, 6].map((list, i) => ({id: `b${i + 1}`, number: i + 1, list, name: `Bench cam ${i + 1}`}));

function record(id: string, result: unknown) {
    mkdirSync(OUT, {recursive: true});
    writeFileSync(path.join(OUT, `${id}.json`), JSON.stringify({id, at: new Date().toISOString(), platform: process.platform, result}, null, 2));
}

const median = (values: number[]) => {
    const s = [...values].sort((a, b) => a - b);
    return s.length ? (s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2) : NaN;
};
const percentile = (values: number[], p: number) => {
    const s = [...values].sort((a, b) => a - b);
    return s.length ? s[Math.min(s.length - 1, Math.floor((p / 100) * s.length))] : NaN;
};

/** CDP `Performance.getMetrics` of the first window (TaskDuration in seconds) [NV: main thread of the renderer only]. */
async function pageMetrics(app: ElectronApplication): Promise<Record<string, number>> {
    return app.evaluate(async ({BrowserWindow}) => {
        const d = BrowserWindow.getAllWindows()[0].webContents.debugger;
        if (!d.isAttached()) {
            d.attach('1.3');
            await d.sendCommand('Performance.enable');
        }
        const r = await d.sendCommand('Performance.getMetrics') as {metrics: {name: string; value: number}[]};
        return Object.fromEntries(r.metrics.map(m => [m.name, m.value]));
    });
}

const processSample = (app: ElectronApplication) => app.evaluate(({app: a}) =>
    a.getAppMetrics().map(m => ({pid: m.pid, type: m.type, cpu: m.cpu.cumulativeCPUUsage ?? 0, ws: m.memory.workingSetSize})));

/** B-1a (6.3): own camera, at most 2 frames behind the newest tile of the capture, and distinct frame numbers
 * each second. Captures of the first second are left out. */
function outsideProof(captures: Capture[], from: number, to: number, fps: number) {
    const ids = CAMS.map(c => c.id);
    const late = captures.filter(k => k.at >= from + 1000 && k.at <= to);
    let wrongCamera = 0;
    let behind = 0;
    for (const k of late) {
        const frames: number[] = [];
        for (const c of CAMS) {
            const r = k.tiles[c.id];
            if (typeof r === 'string' || r.camera !== c.number) wrongCamera++;
            else frames.push(r.frame);
        }
        if (!frames.length) continue;
        // circular offsets from the first tile (frame numbers are modulo 60), then the lag behind the newest
        const offsets = frames.map(f => ((f - frames[0] + CYCLE + CYCLE / 2) % CYCLE) - CYCLE / 2);
        const newest = Math.max(...offsets);
        if (offsets.some(o => newest - o > 2)) behind++;
    }
    const seconds = Math.floor((to - from - 1000) / 1000);
    let worstDistinctRatio = Infinity;
    const perSecond: Record<string, number[]> = {};
    for (const id of ids) perSecond[id] = [];
    for (let s = 0; s < seconds; s++) {
        const bucket = late.filter(k => k.at >= from + 1000 + s * 1000 && k.at < from + 2000 + s * 1000);
        for (const id of ids) {
            const distinct = new Set(bucket.map(k => k.tiles[id]).filter(r => typeof r !== 'string').map(r => (r as {frame: number}).frame)).size;
            perSecond[id].push(distinct);
            worstDistinctRatio = Math.min(worstDistinctRatio, distinct / Math.max(1, 0.9 * Math.min(fps, bucket.length)));
        }
    }
    return {captures: late.length, capturesPerSecond: late.length / ((to - from - 1000) / 1000), wrongCamera, behindMoreThan2: behind,
        worstDistinctRatio, distinctPerSecondMedian: Object.fromEntries(ids.map(id => [id, median(perSecond[id])]))};
}

async function run(preview: PreviewKit, fps: number) {
    const server = await preview.server({cameras: CAMS.map(c => ({id: c.id, number: c.number, index: 90 + c.number, name: `ring ${c.id}`})),
        width: SIZE[0], height: SIZE[1], fps, targetBytes: TARGET_BYTES, startTimeoutMs: 600_000});
    const win = await preview.open(server, CAMS.map(c => ({id: c.id, index: c.list, name: c.name})), {viewer: null});
    const ids = CAMS.map(c => c.id);
    await requirePreviewTiles(win.page);
    await waitDrawn(win.page, ids, 30_000);
    const firstDraw = Date.now();
    const refresh = await win.app.evaluate(({screen}) => screen.getPrimaryDisplay().displayFrequency);
    await sleep(WARMUP_MS);

    const geo = await geometry(win.page, ids, SIZE);
    const m0 = await pageMetrics(win.app);
    const p0 = await processSample(win.app);
    const loop0 = await server.command<{loop_thread_cpu_s: number}>({cmd: 'loop_cpu'});
    const w0 = await written(server);
    await observe(win.app, geo, win.windowId);
    const from = Date.now();
    await sleep(MEASURE_MS);
    const to = Date.now();
    const captures = toCaptures(await readings(win.app, win.windowId), ids);
    const m1 = await pageMetrics(win.app);
    const p1 = await processSample(win.app);
    const loop1 = await server.command<{loop_thread_cpu_s: number}>({cmd: 'loop_cpu'});
    const w1 = await written(server);
    const n = await counts(server, from, to);
    const notShown = await server.command<{connections: Record<string, Record<string, number>>}>({cmd: 'not_shown'});
    // the claim of the product, read only now, at the end of the run
    const drawn = await win.page.evaluate(() => window.preview.drawnCount());
    const end = Date.now();

    const seconds = (to - from) / 1000;
    const conn = connectionNumbers(n).at(-1)!;
    const perCamera = Object.fromEntries(ids.map(id => {
        const c = n.connections[conn]?.cameras[id];
        const buckets = Array.from({length: Math.floor(seconds)}, (_, s) => (c?.ready ?? []).filter(t => t >= from + s * 1000 && t < from + (s + 1) * 1000).length);
        return [id, {readyPerSecondMedian: median(buckets), readyTotal: c?.ready.length ?? 0, sentTotal: c?.sent.length ?? 0,
            written: w1[id] - w0[id], drawnCount: drawn?.[id] ?? null}];
    }));
    const sendToReady = ids.flatMap(id => n.connections[conn]?.cameras[id]?.send_to_ready_ms ?? []);
    const cpuPercentByType: Record<string, number> = {};
    for (const m of p1) cpuPercentByType[m.type] = (cpuPercentByType[m.type] ?? 0) + (100 * (m.cpu - (p0.find(f => f.pid === m.pid)?.cpu ?? 0))) / seconds;
    const target = 0.9 * Math.min(fps, refresh);
    const runSeconds = (end - firstDraw) / 1000;
    return {
        fps, refresh, seconds,
        b1a: outsideProof(captures, from, to, fps),
        b1b: {perCamera, minReadyPerSecondMedian: Math.min(...ids.map(id => perCamera[id].readyPerSecondMedian)),
            minDrawnRatio: Math.min(...ids.map(id => (drawn?.[id] ?? 0) / (target * runSeconds))), target, runSeconds},
        b2: {p50: percentile(sendToReady, 50), p95: percentile(sendToReady, 95), max: Math.max(...sendToReady), count: sendToReady.length},
        b3: {taskDurationShare: ((m1.TaskDuration ?? NaN) - (m0.TaskDuration ?? NaN)) / seconds},
        recorded: {cpuPercentByType, workingSetMB: p1.reduce((a, m) => a + m.ws, 0) / 1024,
            pythonLoopThreadCpu: (loop1.loop_thread_cpu_s - loop0.loop_thread_cpu_s) / seconds, notShown: notShown.connections[String(conn)] ?? {}},
    };
}

type Run = Awaited<ReturnType<typeof run>>;

async function runs(fps: number): Promise<Run[]> {
    const out: Run[] = [];
    for (let i = 0; i < RUNS; i++) {
        const kit = new PreviewKit();   // a new server and a new harness app for each run
        try {
            out.push(await run(kit, fps));
        } finally {
            await kit.close();
        }
    }
    return out;
}

const medianOf = (rs: Run[], f: (r: Run) => number) => median(rs.map(f));

test('T-PRV-51 8 cameras at 1080p30: the full outside proof', async () => {
    test.setTimeout(60 * 60_000);
    const rs = await runs(30);
    const summary = {
        b1aWrongCamera: medianOf(rs, r => r.b1a.wrongCamera), b1aBehindMoreThan2: medianOf(rs, r => r.b1a.behindMoreThan2),
        b1aWorstDistinctRatio: medianOf(rs, r => r.b1a.worstDistinctRatio),
        b1bMinReadyPerSecondMedian: medianOf(rs, r => r.b1b.minReadyPerSecondMedian), b1bTarget: medianOf(rs, r => r.b1b.target),
        b1bMinDrawnRatio: medianOf(rs, r => r.b1b.minDrawnRatio),
        b2P95: medianOf(rs, r => r.b2.p95), b3TaskDurationShare: medianOf(rs, r => r.b3.taskDurationShare),
    };
    record('T-PRV-51', {summary, runs: rs});
    expect.soft(summary.b1aWrongCamera, 'B-1a: each tile shows its own camera in each capture (outside)').toBe(0);
    expect.soft(summary.b1aBehindMoreThan2, 'B-1a: no tile more than 2 frames behind the newest tile of a capture (outside)').toBe(0);
    expect.soft(summary.b1aWorstDistinctRatio, 'B-1a: distinct frame numbers each second at least 0.9 x min(30, C) (outside)').toBeGreaterThanOrEqual(1);
    expect.soft(summary.b1bMinReadyPerSecondMedian, 'B-1b: median ready messages each second at least 0.9 x min(F, R) (server)').toBeGreaterThanOrEqual(summary.b1bTarget);
    expect.soft(summary.b1bMinDrawnRatio, 'B-1b: drawnCount at least 0.9 x min(F, R) x the run time (claim of the product)').toBeGreaterThanOrEqual(1);
    expect.soft(summary.b2P95, 'B-2: send-to-ready p95 at most 50 ms (server)').toBeLessThanOrEqual(50);
    expect.soft(summary.b3TaskDurationShare, 'B-3: TaskDuration at most 50 % of the run time (CDP)').toBeLessThanOrEqual(0.5);
});

test('T-PRV-52 8 cameras at 1080p60: the inside counts', async () => {
    test.setTimeout(60 * 60_000);
    const rs = await runs(60);
    const summary = {
        b1bMinReadyPerSecondMedian: medianOf(rs, r => r.b1b.minReadyPerSecondMedian), b1bTarget: medianOf(rs, r => r.b1b.target),
        b1bMinDrawnRatio: medianOf(rs, r => r.b1b.minDrawnRatio),
        b2P95: medianOf(rs, r => r.b2.p95), b3TaskDurationShare: medianOf(rs, r => r.b3.taskDurationShare),
        // the values of the outside observer at 60 fps are recorded, with no target (Q9)
        outsideRecordedOnly: rs.map(r => r.b1a),
    };
    record('T-PRV-52', {summary, runs: rs});
    expect.soft(summary.b1bMinReadyPerSecondMedian, 'B-1b: median ready messages each second at least 0.9 x min(F, R) (server)').toBeGreaterThanOrEqual(summary.b1bTarget);
    expect.soft(summary.b1bMinDrawnRatio, 'B-1b: drawnCount at least 0.9 x min(F, R) x the run time (claim of the product)').toBeGreaterThanOrEqual(1);
    expect.soft(summary.b2P95, 'B-2: send-to-ready p95 at most 50 ms (server)').toBeLessThanOrEqual(50);
    expect.soft(summary.b3TaskDurationShare, 'B-3: TaskDuration at most 50 % of the run time (CDP)').toBeLessThanOrEqual(0.5);
});
