// One run of the step 4b preview benchmarks (T-PRV-51, T-PRV-52; specs/preview-4b.md 6.2) in the harness main
// process, with no Playwright attached to the app: the devtools link of Playwright copies each websocket frame of
// the page and overflows at 256 MB with 8 cameras at 1080p (Q869). The bench side (preview.bench.ts) starts the app
// with PREVIEW_BENCH_RUN = the path of a JSON config, and reads the result file. The main process gives the
// outside observer, the CDP metrics of the page (its own debugger, no Network domain), the process metrics and,
// at the end only, the claim of the product (`drawnCount`). It prints `@bench measure-start` and
// `@bench measure-end`, so that the bench reads the counts of ui_server.py at the same times.
import {app, BrowserWindow, screen} from 'electron';
import {readFileSync, writeFileSync} from 'node:fs';
import {observeWindow} from './observer.ts';
import type {Geometry} from './observer.ts';

export interface PreviewBenchConfig {
    port: number;
    cameras: {id: string; index: number; name: string}[];
    size: [number, number];
    warmupMs: number;
    measureMs: number;
    out: string;
}

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

export async function runPreviewBench(openWindow: (name: string) => number, configPath: string): Promise<void> {
    const c = JSON.parse(readFileSync(configPath, 'utf8')) as PreviewBenchConfig;
    const ids = c.cameras.map(k => k.id);
    const win = BrowserWindow.fromId(openWindow('preview'))!;
    const js = <T>(code: string) => win.webContents.executeJavaScript(code) as Promise<T>;
    let result: unknown;
    try {
        await new Promise(resolve => win.webContents.once('did-finish-load', resolve));
        for (let i = 0; i < 200 && !(await js<boolean>("'preview' in window")); i++) await sleep(50);
        await js(`window.preview.start(${JSON.stringify({port: c.port, cameras: c.cameras, viewer: null})})`);
        const deadline = Date.now() + 30_000;
        const notDrawn = () => js<string[]>(`${JSON.stringify(ids)}.filter(id => !window.preview.overlay(id)?.frame)`);
        while ((await notDrawn()).length && Date.now() < deadline) await sleep(100);
        const missing = await notDrawn();
        if (missing.length) throw new Error(`no frame drawn in 30 s for ${missing.join(', ')}`);
        const firstDraw = Date.now();
        const refresh = screen.getPrimaryDisplay().displayFrequency;
        await sleep(c.warmupMs);

        const geo = await js<{tiles: number[][][]; missing: string[]; innerWidth: number}>(
            `window.preview.layout(${JSON.stringify(ids)}, ${JSON.stringify(c.size)})`);
        if (geo.missing.length) throw new Error(`no tile canvas for ${geo.missing.join(', ')}`);
        const d = win.webContents.debugger;
        d.attach('1.3');
        await d.sendCommand('Performance.enable');
        const metrics = async () => Object.fromEntries(((await d.sendCommand('Performance.getMetrics')) as {metrics: {name: string; value: number}[]})
            .metrics.map(m => [m.name, m.value]));
        const processes = () => app.getAppMetrics().map(m => ({pid: m.pid, type: m.type, cpu: m.cpu.cumulativeCPUUsage ?? 0, ws: m.memory.workingSetSize}));
        const m0 = await metrics();
        const p0 = processes();
        const rows: number[][] = [];
        console.log('@bench measure-start');
        observeWindow(win, geo as Geometry, rows);
        const from = Date.now();
        await sleep(c.measureMs);
        const to = Date.now();
        win.webContents.endFrameSubscription();
        const m1 = await metrics();
        const p1 = processes();
        console.log('@bench measure-end');
        // the claim of the product, read only now, at the end of the run
        const drawn = await js<Record<string, number> | null>('window.preview.drawnCount()');
        result = {ok: true, firstDraw, refresh, from, to, end: Date.now(), rows, m0, m1, p0, p1, drawn};
    } catch (e) {
        result = {ok: false, error: String(e)};
    }
    writeFileSync(c.out, JSON.stringify(result));
    app.quit();
}
