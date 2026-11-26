// The main process of the test Electron app (specs/player.md section 12.1). It installs the take
// handler with a temporary recordings folder and picked-folders file, and gives the tests two hooks
// through `globalThis.__harness` (Playwright `electronApp.evaluate`): a dialog pick and a read fault.
// A missing product module is recorded, and the window still opens, so each test fails on its own.
// The page `preview` is the harness page of the step 4b preview (specs/preview-4b.md 7.2). With
// PLAYER_HARNESS_PRODUCT_THROTTLING=1 (T-PRV-49) the app has no switch against backgrounding, as the product
// app, and `openWindow(name, {productThrottling: true})` opens a window with the default `backgroundThrottling`.
import {app, BrowserWindow, ipcMain, protocol} from 'electron';
import type {NativeImage} from 'electron';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {patternBytes} from '../fixtures/take-files-checks.ts';
import {observeWindow} from './observer.ts';
import type {Geometry} from './observer.ts';
import {runPreviewBench} from './preview-bench-run.ts';

type SchemeModule = typeof import('../../main/take-scheme.ts');
type Handler = Awaited<ReturnType<SchemeModule['installTakeHandler']>>;

const here = path.dirname(fileURLToPath(import.meta.url));
const recordingsFolder = process.env.PLAYER_HARNESS_RECORDINGS ?? '';
const pickedFoldersFile = process.env.PLAYER_HARNESS_PICKED ?? '';
const firstPage = process.env.PLAYER_HARNESS_PAGE ?? 'harness';
const productThrottling = process.env.PLAYER_HARNESS_PRODUCT_THROTTLING === '1';

if (!productThrottling) {
    for (const s of ['disable-renderer-backgrounding', 'disable-background-timer-throttling', 'disable-backgrounding-occluded-windows']) app.commandLine.appendSwitch(s);
}

let productError: string | null = null;
let scheme: SchemeModule | null = null;
let handler: Handler | null = null;
try {
    // Electron waits for this top-level await before `ready`, so the scheme registers in time.
    scheme = await import('../../main/take-scheme.ts');
    scheme.registerTakeScheme();
} catch (e) {
    productError = String(e);
}

const pages: Record<string, string> = {
    harness: path.join(here, '..', 'renderer', 'player', 'tests', 'harness', 'index.html'),
    host: path.join(here, '..', 'renderer', 'components', 'playback', 'tests', 'host', 'index.html'),
    preview: path.join(here, '..', 'renderer', 'components', 'camera-views', 'tests', 'harness', 'preview', 'index.html'),
};

interface WindowOptions {
    productThrottling?: boolean;   // the default `backgroundThrottling` of the product window (T-PRV-49)
}

function openWindow(name = firstPage, options: WindowOptions = {}): number {
    // a hidden window must run requestAnimationFrame and timers as a shown one (CI runs hidden)
    const throttling = options.productThrottling ? {} : {backgroundThrottling: false};
    const win = new BrowserWindow({
        width: 1400, height: 1000, show: process.env.PLAYER_HARNESS_SHOW === '1',
        webPreferences: {preload: path.join(here, '..', 'preload', 'preload.mjs'), contextIsolation: true, sandbox: true, ...throttling},
    });
    // a never-shown window paints about once a second once a canvas draws: show it transparent, inactive
    // and click-through instead, so hidden runs behave as shown runs
    // Linux runs under xvfb, which shows nothing, and has no window opacity: show the window as it is
    if (process.platform === 'linux') win.show();
    else if (process.env.PLAYER_HARNESS_SHOW !== '1') {
        win.setOpacity(0);
        win.setIgnoreMouseEvents(true);
        win.showInactive();
    }
    void win.loadFile(pages[name]);
    return win.id;
}

/** T-PLAY-59: a handler variant that answers 200 with the exact length, 200 with the whole file, or
 * 206 with a wrong Content-Range start. It serves the pattern of `take-files-checks.ts` (seed 2). */
function installVariant(mode: 'ok-exact' | 'ok-whole' | 'bad-start'): void {
    const size = 300_000;
    const whole = patternBytes(2, 0, size);
    protocol.unhandle('skellycam-take');
    protocol.handle('skellycam-take', req => {
        const m = /^bytes=(\d+)-(\d+)$/.exec(req.headers.get('Range') ?? '');
        const headers = {'Content-Type': 'application/octet-stream', 'Cache-Control': 'no-store', 'Access-Control-Allow-Origin': '*',
            'Access-Control-Expose-Headers': 'Content-Range, Content-Length, Accept-Ranges'};
        if (!m || mode === 'ok-whole') return new Response(whole, {status: 200, headers});
        const a = Number(m[1]);
        const b = Math.min(Number(m[2]), size - 1);
        if (mode === 'ok-exact') return new Response(whole.slice(a, b + 1), {status: 200, headers});
        return new Response(whole.slice(a + 1, b + 2), {status: 206, headers: {...headers, 'Content-Range': `bytes ${a + 1}-${b + 1}/${size}`}});
    });
}

const observed: Record<string, {rows: number[][]; read: (image: NativeImage) => void}> = {};

const need = (): Handler => {
    if (!handler) throw new Error(productError ?? 'the take handler is not installed');
    return handler;
};

(globalThis as Record<string, unknown>).__harness = {
    productError: () => productError,
    recordPick: (folder: string) => need().recordPick(folder),
    setReadFault: (relativePath: string | null) => need().setReadFault(relativePath),
    openWindow: (name?: string, options?: WindowOptions) => openWindow(name, options),
    installVariant,
    channels: async () => (await import('../../main/bridge.ts')).TAKE_CHANNELS,
    // the outside observer (observer.ts): the rows and the reader of each observed window
    observe: (geo: Geometry, id: number | null) => {
        const win = id === null ? BrowserWindow.getAllWindows()[0] : BrowserWindow.fromId(id)!;
        const rows: number[][] = [];
        observed[String(id)] = {rows, read: observeWindow(win, geo, rows)};
    },
    readings: (id: number | null) => {
        const win = id === null ? BrowserWindow.getAllWindows()[0] : BrowserWindow.fromId(id);
        win?.webContents.endFrameSubscription();
        return observed[String(id)]?.rows ?? [];
    },
    captureOnce: async (id: number | null) => {
        const win = id === null ? BrowserWindow.getAllWindows()[0] : BrowserWindow.fromId(id)!;
        observed[String(id)].read(await win.webContents.capturePage());
    },
};

ipcMain.handle('harness:product-error', () => productError);

void app.whenReady().then(async () => {
    if (scheme) {
        try {
            handler = await scheme.installTakeHandler({recordingsFolder, pickedFoldersFile});
        } catch (e) {
            productError = String(e);
        }
    }
    // the preview bench runs in this process, with no Playwright attached (preview-bench-run.ts, Q869)
    if (process.env.PREVIEW_BENCH_RUN) void runPreviewBench(name => openWindow(name), process.env.PREVIEW_BENCH_RUN);
    else openWindow();
});

app.on('window-all-closed', () => app.quit());
