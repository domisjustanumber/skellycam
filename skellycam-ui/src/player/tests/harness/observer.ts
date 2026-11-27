// The observer outside the page, of the player bench (specs/player.md 12.3) and of the step 4b preview tests
// (specs/preview-4b.md 7.2). The Electron main process takes each composited image of a window
// (`beginFrameSubscription`, about 30 images/s, so a time resolution of about 33 ms) and reads the barcode
// row of each tile at the window points that the page gives (layout, no pixel read in the page). A tile
// value is the camera number in 4 bits, then the frame number in 12 bits; 0 is a tile with no light cell
// ("none", a black tile); -1 is a tile with no place. The reader runs in the harness main process
// (`observeWindow` below, used through `globalThis.__harness`), so that the preview bench can run it with no
// Playwright attached (Q869).
import type {ElectronApplication} from '@playwright/test';
import type {BrowserWindow, NativeImage} from 'electron';

const CYCLE = 60;

/** Window points (CSS pixels) of the 16 barcode cells of each tile, and of the reference strip (k*) of the
 * player bench. */
export interface Geometry {
    tiles: number[][][];
    ref?: number[][];
    innerWidth: number;
}

/** The main-process side: start reading each composited image of `win` into `rows`. Each image gives one row:
 * [time in ms since the epoch, the ref value (when the geometry has `ref`), the value of each tile]. Returns
 * the reader, which also reads one `capturePage()` image (`captureOnce`). */
export function observeWindow(win: BrowserWindow, g: Geometry, rows: number[][]): (image: NativeImage) => void {
    const read = (image: NativeImage) => {
        const s = image.getSize().width / g.innerWidth;
        const out = [performance.timeOrigin + performance.now()];
        for (const pts of [...(g.ref ? [g.ref] : []), ...g.tiles]) {
            if (!pts.length) {
                out.push(-1);
                continue;
            }
            try {
                const x0 = Math.floor(pts[0][0] * s);
                const bmp = image.crop({x: x0, y: Math.round(pts[0][1] * s), width: Math.ceil(pts[pts.length - 1][0] * s) - x0 + 1, height: 1}).toBitmap();
                let v = 0;
                for (const [x] of pts) {
                    const i = (Math.round(x * s) - x0) * 4;
                    v = v * 2 + ((bmp[i] + bmp[i + 1] + bmp[i + 2]) / 3 > 128 ? 1 : 0);
                }
                out.push(v);
            } catch {
                out.push(-1);
            }
        }
        rows.push(out);
    };
    win.webContents.beginFrameSubscription(false, read);
    return read;
}

type HarnessObserver = {
    observe(geo: Geometry, id: number | null): void;
    readings(id: number | null): number[][];
    captureOnce(id: number | null): Promise<void>;
};

/** Start the observer on a window: the first window, or the window `windowId`. */
export async function observe(app: ElectronApplication, geo: Geometry, windowId?: number) {
    await app.evaluate((_e, [g, id]) => (globalThis as never as {__harness: HarnessObserver}).__harness.observe(g, id),
        [geo, windowId ?? null] as const);
}

/** One more row of a running observer from `capturePage()`: a window whose image does not change gives no
 * composited image (specs/preview-4b.md 7.2, Q867). */
export async function captureOnce(app: ElectronApplication, windowId?: number) {
    await app.evaluate((_e, id) => (globalThis as never as {__harness: HarnessObserver}).__harness.captureOnce(id), windowId ?? null);
}

/** Stop the observer of a window and give its rows. */
export async function readings(app: ElectronApplication, windowId?: number): Promise<number[][]> {
    return app.evaluate((_e, id) => (globalThis as never as {__harness: HarnessObserver}).__harness.readings(id), windowId ?? null);
}

/** Stop the observer of the first window. For each tile: the percent of the frames in [from, to] that show
 * the image of k* (the player bench). */
export async function observed(app: ElectronApplication, from: number, to: number) {
    const frames = (await readings(app)).filter(f => f[0] >= from && f[0] <= to);
    const n = frames.length ? frames[0].length - 2 : 0;
    // a tile value is the camera index in 4 bits, then the position in 12 bits
    const shownPercent = Array.from({length: n}, (_, i) =>
        (100 * frames.filter(f => (f[i + 2] & 4095) === f[1] % CYCLE && f[i + 2] >> 12 === i % 16).length) / Math.max(1, frames.length));
    return {frames: frames.length, framesPerSecond: frames.length / ((to - from) / 1000), shownPercent};
}
