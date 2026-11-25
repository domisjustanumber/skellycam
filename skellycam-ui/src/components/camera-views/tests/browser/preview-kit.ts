// The Playwright side of the step 4b preview tests (specs/preview-4b.md 7.2, 7.3): `ui_server.py` in a
// subprocess, the harness app with the page `preview`, the outside observer, and the clean-up after each test.
// No camera, no app start, never port 53117. The images are checked only with the observer of the Electron
// main process; the page reads no tile canvas back.
import {expect, test as base} from '@playwright/test';
import type {ElectronApplication, Page} from '@playwright/test';
import {spawn} from 'node:child_process';
import type {ChildProcessWithoutNullStreams} from 'node:child_process';
import {mkdtempSync, rmSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createInterface} from 'node:readline';
import {fileURLToPath} from 'node:url';
import {launch} from '../../../../player/tests/browser/harness.ts';
import {observe, readings} from '../../../../player/tests/harness/observer.ts';
import type {PreviewApi, SeedCamera, ViewerMode} from '../harness/preview/page.tsx';

declare global {
    interface Window {
        preview: PreviewApi;
    }
}

const UI = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../../..');
const REPO = path.resolve(UI, '..');
const PREFIX = '@ui_server ';

export const SIZE_640: [number, number] = [640, 360];
export const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

export interface ServerCamera {
    id: string;
    number: number;   // the camera number of the barcode, 1 to 8
    name: string;
}

export interface ServerOptions {
    mode?: 'fake' | 'capture';
    cameras: object[];   // fake: {id, number, index, name}; capture: {name, script}
    width?: number;
    height?: number;
    fps?: number;
    targetBytes?: number;
    startTimeoutMs?: number;
}

type Reply = Record<string, unknown> & {ok?: boolean; error?: string; event?: string};

/** One `ui_server.py` process. Each command waits for its reply line. */
export class UiServer {
    port = 0;
    cameras: ServerCamera[] = [];
    private proc: ChildProcessWithoutNullStreams;
    private replies: Reply[] = [];
    private waiters: ((r: Reply) => void)[] = [];
    private tail: string[] = [];
    private chain: Promise<unknown> = Promise.resolve();
    private exited = false;

    private constructor(proc: ChildProcessWithoutNullStreams) {
        this.proc = proc;
        const keep = (line: string) => {
            this.tail.push(line);
            if (this.tail.length > 60) this.tail.shift();
        };
        createInterface({input: proc.stdout}).on('line', line => {
            if (!line.startsWith(PREFIX)) return keep(line);
            const reply = JSON.parse(line.slice(PREFIX.length)) as Reply;
            const waiter = this.waiters.shift();
            if (waiter) waiter(reply);
            else this.replies.push(reply);
        });
        createInterface({input: proc.stderr}).on('line', keep);
        proc.on('exit', () => {
            this.exited = true;
            for (const w of this.waiters.splice(0)) w({ok: false, event: 'exit', error: `ui_server.py ended:\n${this.tail.join('\n')}`});
        });
    }

    static async start(o: ServerOptions): Promise<UiServer> {
        const args = ['run', 'python', '-m', 'skellycam.tests.preview.ui_server', '--mode', o.mode ?? 'fake',
            '--cameras', JSON.stringify(o.cameras), '--width', String(o.width ?? 640), '--height', String(o.height ?? 360),
            '--fps', String(o.fps ?? 30), '--target-bytes', String(o.targetBytes ?? 0)];
        const s = new UiServer(spawn('uv', args, {cwd: REPO, stdio: ['pipe', 'pipe', 'pipe']}));
        const started = await s.next(o.startTimeoutMs ?? 120_000);
        if (started.event !== 'started') throw new Error(`ui_server.py did not start: ${JSON.stringify(started)}\n${s.tail.join('\n')}`);
        s.port = started.port as number;
        s.cameras = started.cameras as ServerCamera[];
        expect(s.port, 'never the port of the product server').not.toBe(53117);
        return s;
    }

    private next(timeoutMs: number): Promise<Reply> {
        const ready = this.replies.shift();
        if (ready) return Promise.resolve(ready);
        if (this.exited) return Promise.resolve({ok: false, event: 'exit', error: `ui_server.py ended:\n${this.tail.join('\n')}`});
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => {
                this.waiters = this.waiters.filter(w => w !== waiter);
                reject(new Error(`ui_server.py: no reply in ${timeoutMs} ms\n${this.tail.join('\n')}`));
            }, timeoutMs);
            const waiter = (r: Reply) => {
                clearTimeout(timer);
                resolve(r);
            };
            this.waiters.push(waiter);
        });
    }

    /** One command (see ui_server.py). Throws the error of a refused command. */
    command<T = Record<string, unknown>>(cmd: Record<string, unknown>, timeoutMs = 60_000): Promise<T> {
        const run = async () => {
            this.proc.stdin.write(JSON.stringify(cmd) + '\n');
            const reply = await this.next(timeoutMs);
            if (!reply.ok) throw new Error(`ui_server.py ${String(cmd.cmd)}: ${reply.error}\n${String(reply.trace ?? '')}`);
            return reply as T;
        };
        const p = this.chain.then(run, run);
        this.chain = p.catch(() => undefined);
        return p;
    }

    /** A clean stop: the server closes its connections, its port and its rings, and ends. */
    async stop(): Promise<void> {
        if (this.exited) return;
        try {
            await this.command({cmd: 'stop'}, 30_000);
            const end = await this.next(60_000);
            if (end.event !== 'stopped' && end.event !== 'exit') throw new Error(`ui_server.py stop: ${JSON.stringify(end)}`);
            const deadline = Date.now() + 30_000;
            while (!this.exited && Date.now() < deadline) await sleep(50);
        } finally {
            // shortcut: a kill only when the clean stop failed; the test has failed then anyway
            if (!this.exited) this.proc.kill();
        }
    }

    get stopped() {
        return this.exited;
    }
}

export interface PreviewWindow {
    app: ElectronApplication;
    page: Page;
    windowId: number;
    consoleErrors: {text: string; at: number}[];
}

export interface OpenOptions {
    viewer?: ViewerMode;
    gridHeight?: number;
    env?: Record<string, string>;
}

async function wrap(app: ElectronApplication, page: Page): Promise<PreviewWindow> {
    const consoleErrors: {text: string; at: number}[] = [];
    page.on('console', m => {
        if (m.type() === 'error') consoleErrors.push({text: m.text(), at: Date.now()});
    });
    page.on('pageerror', e => consoleErrors.push({text: `pageerror: ${e.message}`, at: Date.now()}));
    const windowId = await (await app.browserWindow(page)).evaluate(w => w.id);
    return {app, page, windowId, consoleErrors};
}

/** The servers and apps of one test; `close` stops each of them after the test. */
export class PreviewKit {
    private servers: UiServer[] = [];
    private apps: ElectronApplication[] = [];
    readonly root = mkdtempSync(path.join(os.tmpdir(), 'skellycam-preview-e2e-'));

    async server(o: ServerOptions): Promise<UiServer> {
        const s = await UiServer.start(o);
        this.servers.push(s);
        return s;
    }

    /** Launch the harness app with the page `preview` and start the page on `server`. */
    async open(server: UiServer, cameras: SeedCamera[], o: OpenOptions = {}): Promise<PreviewWindow> {
        const {app, page} = await launch(path.join(this.root, 'recordings'), path.join(this.root, 'picked.json'), 'preview', o.env);
        this.apps.push(app);
        const win = await wrap(app, page);
        await page.evaluate(opts => window.preview.start(opts), {port: server.port, cameras, viewer: o.viewer ?? null, gridHeight: o.gridHeight});
        return win;
    }

    /** A second window of the same app with the page `preview` and its own connection. */
    async openSecond(first: PreviewWindow, server: UiServer, cameras: SeedCamera[], o: OpenOptions & {productThrottling?: boolean} = {}): Promise<PreviewWindow> {
        const [page] = await Promise.all([
            first.app.waitForEvent('window'),
            first.app.evaluate((_e, opts) => (globalThis as never as {__harness: {openWindow(n: string, o: object): number}}).__harness.openWindow('preview', opts),
                {productThrottling: o.productThrottling ?? false}),
        ]);
        await page.waitForFunction(() => 'preview' in window);
        const win = await wrap(first.app, page);
        await page.evaluate(opts => window.preview.start(opts), {port: server.port, cameras, viewer: o.viewer ?? null, gridHeight: o.gridHeight});
        return win;
    }

    async close(): Promise<void> {
        for (const app of this.apps) await app.close().catch(() => undefined);
        for (const s of this.servers) await s.stop().catch(e => console.log(`ui_server.py stop: ${e}`));
        rmSync(this.root, {recursive: true, force: true});
    }
}

export const test = base.extend<{preview: PreviewKit}>({
    preview: async ({}, use) => {
        const kit = new PreviewKit();
        try {
            await use(kit);
        } finally {
            await kit.close();
        }
    },
});

// ---- Checks of the page ----

/** Fail with the missing behaviour when the provider gives no PreviewTiles (the 4b product code is missing). */
export async function requirePreviewTiles(page: Page, timeoutMs = 5_000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        if (await page.evaluate(() => typeof window.__previewTiles === 'object' && window.__previewTiles !== null)) return;
        await sleep(100);
    }
    const notes = await page.evaluate(() => window.preview.notes());
    throw new Error(`window.__previewTiles is undefined: the provider gives no PreviewTiles (useServer().getPreviewTiles of spec 5.5); notes: ${notes.join(', ')}`);
}

/** Wait until the tile of each camera drew a frame: its kept overlay has a frame text. */
export async function waitDrawn(page: Page, ids: string[], timeoutMs = 10_000) {
    await expect.poll(async () => {
        const overlays = await page.evaluate(i => i.map(id => window.preview.overlay(id)), ids);
        return ids.filter((_, k) => !overlays[k]?.frame);
    }, {message: `each tile draws a frame (cameras with no tile or no frame text)`, timeout: timeoutMs}).toEqual([]);
}

/** The frame number of the kept overlay text ("F000123" gives 123), or null. */
export const overlayFrame = (frame: string | null | undefined) => (frame ? Number(frame.replace(/^F/, '')) : null);

export async function geometry(page: Page, ids: string[], imageSize: [number, number]) {
    const g = await page.evaluate(([i, size]) => window.preview.layout(i, size), [ids, imageSize] as const);
    expect(g.missing, `a tile canvas (canvas[data-camera-id]) with a size for each camera`).toEqual([]);
    return g;
}

/** A reading of a tile: its camera number and frame number (modulo 60), "none" (a black tile) or "off" (no place). */
export type Reading = {camera: number; frame: number} | 'none' | 'off';
export interface Capture {
    at: number;
    tiles: Record<string, Reading>;
}

export function toCaptures(rows: number[][], ids: string[]): Capture[] {
    return rows.map(r => ({
        at: r[0],
        tiles: Object.fromEntries(ids.map((id, i) => {
            const v = r[i + 1];
            return [id, v < 0 ? 'off' : v === 0 ? 'none' : {camera: v >> 12, frame: v & 4095}];
        })),
    }));
}

/** Observe the tiles of `ids` for `ms` with the outside observer of the window. */
export async function watch(win: PreviewWindow, ids: string[], ms: number, imageSize: [number, number] = SIZE_640): Promise<Capture[]> {
    const geo = await geometry(win.page, ids, imageSize);
    await observe(win.app, geo, win.windowId);
    await sleep(ms);
    return toCaptures(await readings(win.app, win.windowId), ids);
}

export const sameReading = (a: Reading, b: Reading) =>
    typeof a === 'string' || typeof b === 'string' ? a === b : a.camera === b.camera && a.frame === b.frame;

export const describe = (r: Reading) => (typeof r === 'string' ? r : `camera ${r.camera} frame ${r.frame}`);

// ---- Server counts ----

export interface CameraCounts {
    sent: number[];
    ready: number[];
    send_to_ready_ms: number[];
}

export interface Counts {
    now: number;
    connections: Record<string, {opened: number; cameras: Record<string, CameraCounts>}>;
}

export const counts = (server: UiServer, since = 0, until?: number) =>
    server.command<Counts>(until === undefined ? {cmd: 'counts', since} : {cmd: 'counts', since, until});

/** The numbers of the connections, in the order in which they opened. */
export const connectionNumbers = (c: Counts) => Object.keys(c.connections).map(Number).sort((a, b) => a - b);

export const written = async (server: UiServer) => (await server.command<{written: Record<string, number>}>({cmd: 'written'})).written;

/** The console errors that do not come from the connection: the failed connect of a stopped server is logged by
 * Chromium and by websocket-connection.ts. */
export const otherErrors = (errors: {text: string; at: number}[], since = 0) =>
    errors.filter(e => e.at >= since && !/^WebSocket error:|WebSocket connection to .* failed/.test(e.text));
