// The observer outside the page, of the player bench (specs/player.md 12.3) and of the step 4b preview tests
// (specs/preview-4b.md 7.2). The Electron main process takes each composited image of a window
// (`beginFrameSubscription`, about 30 images/s, so a time resolution of about 33 ms) and reads the barcode
// row of each tile at the window points that the page gives (layout, no pixel read in the page). A tile
// value is the camera number in 4 bits, then the frame number in 12 bits; 0 is a tile with no light cell
// ("none", a black tile); -1 is a tile with no place.
import type {ElectronApplication} from '@playwright/test';

const CYCLE = 60;

/** Window points (CSS pixels) of the 16 barcode cells of each tile, and of the reference strip (k*) of the
 * player bench. */
export interface Geometry {
    tiles: number[][][];
    ref?: number[][];
    innerWidth: number;
}

/** Start the observer on a window: the first window, or the window `windowId`. Each image gives one row:
 * [time in ms since the epoch, the ref value (when the geometry has `ref`), the value of each tile]. */
export async function observe(app: ElectronApplication, geo: Geometry, windowId?: number) {
    await app.evaluate(({BrowserWindow}, [g, id]) => {
        const G = globalThis as never as {__observed: Record<string, number[][]>; __readers: Record<string, (image: Electron.NativeImage) => void>};
        const rows: number[][] = [];
        G.__observed = {...G.__observed, [String(id)]: rows};
        const win = id === null ? BrowserWindow.getAllWindows()[0] : BrowserWindow.fromId(id)!;
        const read = (image: Electron.NativeImage) => {
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
        G.__readers = {...G.__readers, [String(id)]: read};
        win.webContents.beginFrameSubscription(false, read);
    }, [geo, windowId ?? null] as const);
}

/** One more row of a running observer from `capturePage()`: a window whose image does not change gives no
 * composited image (specs/preview-4b.md 7.2, Q867). */
export async function captureOnce(app: ElectronApplication, windowId?: number) {
    await app.evaluate(async ({BrowserWindow}, id) => {
        const G = globalThis as never as {__readers: Record<string, (image: Electron.NativeImage) => void>};
        const win = id === null ? BrowserWindow.getAllWindows()[0] : BrowserWindow.fromId(id)!;
        G.__readers[String(id)](await win.webContents.capturePage());
    }, windowId ?? null);
}

/** Stop the observer of a window and give its rows. */
export async function readings(app: ElectronApplication, windowId?: number): Promise<number[][]> {
    return app.evaluate(({BrowserWindow}, id) => {
        const win = id === null ? BrowserWindow.getAllWindows()[0] : BrowserWindow.fromId(id);
        win?.webContents.endFrameSubscription();
        return (globalThis as never as {__observed: Record<string, number[][]>}).__observed?.[String(id)] ?? [];
    }, windowId ?? null);
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
