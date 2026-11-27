// The benchmarks T-PRV-51 and T-PRV-52 of the step 4b preview (specs/preview-4b.md section 6): 8 cameras on the
// main-thread tile at 1080p30 and 1080p60. They run by hand on the Windows test machine
// (playwright.player-bench.config.ts), not in CI. Each one writes its result as JSON to PLAYER_BENCH_OUT. A missed
// target is a soft failure: it goes to the user, and section 6.4 applies.
//
// The observers (6.1): the outside observer (beginFrameSubscription of the main process); the ready messages and
// the send-to-ready times that ui_server.py counts; TaskDuration of the page through CDP; the claim of the product
// (`drawnCount`), read only at the end of a run and never given as an outside proof.
import {expect} from '@playwright/test';
import {spawn} from 'node:child_process';
import {mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {createInterface} from 'node:readline';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {HARNESS_MAIN} from '../../../../player/tests/browser/harness.ts';
import {counts, connectionNumbers, PreviewKit, test, toCaptures, written} from '../browser/preview-kit.ts';
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

/** One run of the harness app in bench mode, with no Playwright attached (preview-bench-run.ts, Q869). `onLine`
 * gets each line that the app prints; the app ends itself after the run. Gives the last 40 lines of its output. */
function runHarness(env: Record<string, string>, onLine: (line: string) => void, timeoutMs: number): Promise<string[]> {
    const electron = createRequire(import.meta.url)('electron') as string;
    const full: Record<string, string> = {};
    for (const [k, v] of Object.entries(process.env)) if (v !== undefined && k !== 'ELECTRON_RUN_AS_NODE') full[k] = v;
    const proc = spawn(electron, [HARNESS_MAIN, '--no-sandbox'], {env: {...full, ...env}, stdio: ['ignore', 'pipe', 'pipe']});
    const tail: string[] = [];
    const keep = (line: string) => {
        tail.push(line);
        if (tail.length > 40) tail.shift();
    };
    createInterface({input: proc.stdout}).on('line', line => {
        keep(line);
        onLine(line);
    });
    createInterface({input: proc.stderr}).on('line', keep);
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
            proc.kill();
            reject(new Error(`the bench app did not end in ${timeoutMs} ms:\n${tail.join('\n')}`));
        }, timeoutMs);
        proc.on('exit', () => {
            clearTimeout(timer);
            resolve(tail);
        });
    });
}

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
    // the seconds below the B-1a ratio, with what the observer saw there (a diagnosis for the user, not a target)
    const misses: {camera: string; second: number; captures: number; distinct: number; frames: (number | string)[]}[] = [];
    const capturesEachSecond: number[] = [];
    const perSecond: Record<string, number[]> = {};
    for (const id of ids) perSecond[id] = [];
    for (let s = 0; s < seconds; s++) {
        const bucket = late.filter(k => k.at >= from + 1000 + s * 1000 && k.at < from + 2000 + s * 1000);
        capturesEachSecond.push(bucket.length);
        for (const id of ids) {
            const distinct = new Set(bucket.map(k => k.tiles[id]).filter(r => typeof r !== 'string').map(r => (r as {frame: number}).frame)).size;
            perSecond[id].push(distinct);
            const ratio = distinct / Math.max(1, 0.9 * Math.min(fps, bucket.length));
            worstDistinctRatio = Math.min(worstDistinctRatio, ratio);
            if (ratio < 1) misses.push({camera: id, second: s, captures: bucket.length, distinct,
                frames: bucket.map(k => (typeof k.tiles[id] === 'string' ? k.tiles[id] as string : (k.tiles[id] as {frame: number}).frame))});
        }
    }
    return {captures: late.length, capturesPerSecond: late.length / ((to - from - 1000) / 1000), wrongCamera, behindMoreThan2: behind,
        worstDistinctRatio, distinctPerSecondMedian: Object.fromEntries(ids.map(id => [id, median(perSecond[id])])),
        seconds, capturesEachSecond, misses};
}

async function run(preview: PreviewKit, fps: number) {
    const server = await preview.server({cameras: CAMS.map(c => ({id: c.id, number: c.number, index: 90 + c.number, name: `ring ${c.id}`})),
        width: SIZE[0], height: SIZE[1], fps, targetBytes: TARGET_BYTES, startTimeoutMs: 600_000});
    const ids = CAMS.map(c => c.id);
    const configFile = path.join(preview.root, 'bench-config.json');
    const outFile = path.join(preview.root, 'bench-run.json');
    writeFileSync(configFile, JSON.stringify({port: server.port, cameras: CAMS.map(c => ({id: c.id, index: c.list, name: c.name})),
        size: SIZE, warmupMs: WARMUP_MS, measureMs: MEASURE_MS, out: outFile}));
    // the counts of the server at the start and the end of the measurement, at the lines of the app
    const marks: Promise<unknown>[] = [];
    let loop0 = {loop_thread_cpu_s: NaN};
    let loop1 = {loop_thread_cpu_s: NaN};
    let w0: Record<string, number> = {};
    let w1: Record<string, number> = {};
    const tail = await runHarness({PREVIEW_BENCH_RUN: configFile, PLAYER_HARNESS_PAGE: 'preview', PLAYER_HARNESS_RECORDINGS: path.join(preview.root, 'recordings'),
        PLAYER_HARNESS_PICKED: path.join(preview.root, 'picked.json')}, line => {
        if (line === '@bench measure-start') marks.push((async () => {
            loop0 = await server.command<{loop_thread_cpu_s: number}>({cmd: 'loop_cpu'});
            w0 = await written(server);
        })());
        if (line === '@bench measure-end') marks.push((async () => {
            loop1 = await server.command<{loop_thread_cpu_s: number}>({cmd: 'loop_cpu'});
            w1 = await written(server);
        })());
    }, WARMUP_MS + MEASURE_MS + 180_000);
    await Promise.all(marks);
    // a lost line or a crash of the app fails here, not as NaN values
    if (marks.length !== 2) throw new Error(`the bench app printed ${marks.length} of its 2 measurement lines:\n${tail.join('\n')}`);
    const r = JSON.parse(readFileSync(outFile, 'utf8'));
    if (!r.ok) throw new Error(`the bench run: ${r.error}\n${tail.join('\n')}`);
    const {firstDraw, refresh, from, to, end, m0, m1, p0, p1, drawn} = r as {firstDraw: number; refresh: number; from: number; to: number;
        end: number; m0: Record<string, number>; m1: Record<string, number>; p0: {pid: number; type: string; cpu: number; ws: number}[];
        p1: {pid: number; type: string; cpu: number; ws: number}[]; drawn: Record<string, number> | null};
    const captures = toCaptures(r.rows, ids);
    const n = await counts(server, from, to);
    const notShown = await server.command<{connections: Record<string, Record<string, number>>}>({cmd: 'not_shown'});

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
