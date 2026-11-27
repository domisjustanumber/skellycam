// The page of the test Electron app. It holds no host code: the tile tests load only `tile/tile.ts`,
// and the player tests load `index.ts` (specs/player.md section 12.1). The tests call `window.harness`.
import {canvasPoint, readTile} from '../fixtures/barcode.ts';
import type {Rgb, TileReading} from '../fixtures/barcode.ts';
import {runTakeFilesChecks} from '../fixtures/take-files-checks.ts';
import {makeBench} from './bench.ts';
import type {PlayerEvent, TakePlayer, TileUpdate} from '../../index.ts';
import type {TakeFiles} from '../../files/take-files.ts';

type TileModule = typeof import('../../tile/tile.ts');
type TimingsModule = typeof import('../../tile/timings.ts');
type PlayerModule = typeof import('../../index.ts');
type TileObject = InstanceType<TileModule['Tile']>;
type WireUpdate = Omit<TileUpdate, 'jpeg'> & {jpeg: string | null};

declare global {
    interface Window {
        harness: typeof harness;
        bench: ReturnType<typeof makeBench>;
        harnessIpc: {invoke(channel: string, ...args: unknown[]): Promise<unknown>; send(channel: string, ...args: unknown[]): void; productError(): Promise<string | null>};
        harnessBridgeError?: string;
    }
}

const fromBase64 = (s: string) => Uint8Array.from(atob(s), c => c.charCodeAt(0));
const toBase64 = (b: Uint8Array) => btoa(Array.from(b, c => String.fromCharCode(c)).join(''));

const tiles = new Map<string, {tile: TileObject; canvas: HTMLCanvasElement; rotation: number}>();
let player: TakePlayer | null = null;
let playerCanvases: HTMLCanvasElement[] = [];
let playerTiles: TileObject[] = [];
const events: {type: string; at: number; frame: number}[] = [];
const openFiles = new Map<number, TakeFiles>();
let nextFiles = 1;

function makeCanvas(width: number, height: number): HTMLCanvasElement {
    const c = document.createElement('canvas');
    c.style.width = `${width}px`;
    c.style.height = `${height}px`;
    document.getElementById('tiles')!.append(c);
    return c;
}

function readCanvas(canvas: HTMLCanvasElement, rotation: number): TileReading {
    const {width, height} = canvas;
    const data = canvas.getContext('2d')!.getImageData(0, 0, width, height).data;
    return readTile((x, y) => {
        const i = (Math.min(height - 1, Math.max(0, y)) * width + Math.min(width - 1, Math.max(0, x))) * 4;
        return [data[i], data[i + 1], data[i + 2]] as Rgb;
    }, width, height, rotation);
}

const productError = async () => (await window.harnessIpc.productError()) ?? window.harnessBridgeError ?? null;
const tileModule = () => import('../../tile/tile.ts');
const timingsModule = (): Promise<TimingsModule> => import('../../tile/timings.ts');

// The tile timing tests (specs/capture-timings.md 10.2, T-TIM-25 and T-TIM-26): one TileTimings on a fake clock that
// moves `step` ms at each read, and a decode seam that moves it `decodeMs` ms more. No real time is in a sample.
const clock = {ms: 1000, step: 0.25, decodeMs: 2.5, calls: 0};
const fakeNow = () => {
    clock.calls++;
    const value = clock.ms;
    clock.ms += clock.step;
    return value;
};
let timings: InstanceType<TimingsModule['TileTimings']> | null = null;
const playerModule = (): Promise<PlayerModule> => import('../../index.ts');

function needPlayer(): TakePlayer {
    if (!player) throw new Error('no player is open');
    return player;
}

const harness = {
    productError,

    async makeTile(id: string, width = 640, height = 320): Promise<void> {
        const {Tile} = await tileModule();
        const canvas = makeCanvas(width, height);
        tiles.set(id, {tile: new Tile(canvas), canvas, rotation: 0});
    },

    /** A tile on the fake clock, with the timing handle of `cameraId` (group 'g1'), or with no handle when null. */
    async makeTimedTile(id: string, cameraId: string | null): Promise<void> {
        const [{Tile, decodeJpeg}, {TileTimings}] = await Promise.all([tileModule(), timingsModule()]);
        timings ??= new TileTimings(fakeNow);
        const decode = async (jpeg: Uint8Array) => {
            const image = await decodeJpeg(jpeg);
            clock.ms += clock.decodeMs;
            return image;
        };
        const canvas = makeCanvas(640, 320);
        const seams = cameraId === null ? {decode} : {decode, timing: timings.handle(cameraId, 'g1')};
        tiles.set(id, {tile: new Tile(canvas, {}, seams), canvas, rotation: 0});
    },

    setTimingsOn(on: boolean): void {
        timings!.on = on;
    },

    clockCalls: (): number => clock.calls,

    takeSummaries: () => timings!.takeSummaries(),

    /** An update with an image that the caller decoded ahead, as the player gives it: no decode in the tile. */
    async updateTileWithImage(id: string, u: WireUpdate): Promise<string> {
        const {decodeJpeg} = await tileModule();
        const jpeg = fromBase64(u.jpeg!);
        return tiles.get(id)!.tile.update({...u, jpeg, image: await decodeJpeg(jpeg)});
    },

    /** Updates with no wait between them. */
    async updateMany(id: string, updates: WireUpdate[]): Promise<string[]> {
        const t = tiles.get(id)!;
        return Promise.all(updates.map(u => t.tile.update({...u, jpeg: u.jpeg === null ? null : fromBase64(u.jpeg)})));
    },

    /** A new CSS size of the canvas, then two display refreshes: the ResizeObserver redraws the tile. Gives the
     * canvas width, which only a draw of the tile sets. */
    async resizeTile(id: string, width: number): Promise<number> {
        const {canvas} = tiles.get(id)!;
        canvas.style.width = `${width}px`;
        for (let i = 0; i < 2; i++) await new Promise(resolve => requestAnimationFrame(resolve));
        return canvas.width;
    },

    async updateTile(id: string, u: WireUpdate): Promise<string> {
        const t = tiles.get(id)!;
        t.rotation = u.rotationCwDeg;
        return t.tile.update({...u, jpeg: u.jpeg === null ? null : fromBase64(u.jpeg)});
    },

    /** Two updates with no wait between them. */
    async updateTwice(id: string, a: WireUpdate, b: WireUpdate): Promise<string[]> {
        const t = tiles.get(id)!;
        const first = t.tile.update({...a, jpeg: a.jpeg === null ? null : fromBase64(a.jpeg)});
        t.rotation = b.rotationCwDeg;
        const second = t.tile.update({...b, jpeg: b.jpeg === null ? null : fromBase64(b.jpeg)});
        return Promise.all([first, second]);
    },

    setTileOptions(id: string, o: Parameters<TileObject['setOptions']>[0]): void {
        tiles.get(id)!.tile.setOptions(o);
    },

    readTile(id: string): TileReading {
        const t = tiles.get(id)!;
        return readCanvas(t.canvas, t.rotation);
    },

    pixel(id: string, x: number, y: number): Rgb {
        const c = tiles.get(id)!.canvas;
        const d = c.getContext('2d')!.getImageData(x, y, 1, 1).data;
        return [d[0], d[1], d[2]];
    },

    /** The canvas pixel at the stored image point (x, y), with the rotation of the last update. */
    imagePixel(id: string, x: number, y: number): Rgb {
        const t = tiles.get(id)!;
        const [cx, cy] = canvasPoint(t.canvas.width, t.canvas.height, t.rotation, x, y);
        const d = t.canvas.getContext('2d')!.getImageData(cx, cy, 1, 1).data;
        return [d[0], d[1], d[2]];
    },

    overlay(id: string): {overlay: TileObject['overlay']; title: string} {
        const t = tiles.get(id)!;
        return {overlay: t.tile.overlay, title: t.canvas.title};
    },

    async openPlayer(folder: string, initialFrame?: number): Promise<TakePlayer['state']> {
        const m = await playerModule();
        const files = await m.electronTakeFiles(folder);
        if (!(await m.isTakeFolder(files))) throw new Error('not a take folder');
        player = await m.openTake(files, initialFrame === undefined ? {} : {initialFrame});
        playerCanvases = player.state.cameras.map(() => makeCanvas(512, 256));
        playerTiles = playerCanvases.map(c => new m.Tile(c));
        playerTiles.forEach((tile, i) => needPlayer().attachTile(i, tile));
        for (const type of ['frame', 'state', 'error'] as const) {
            player.on(type, (e: PlayerEvent) => void events.push({type, at: performance.now(), frame: e.state.frame}));
        }
        return player.state;
    },

    command(name: 'play' | 'pause' | 'step' | 'seekFrame' | 'setSpeed' | 'setLoop' | 'setTileOptions', ...args: unknown[]): TakePlayer['state'] {
        const p = needPlayer() as unknown as Record<string, (...a: unknown[]) => void>;
        p[name](...args);
        return needPlayer().state;
    },

    state: () => needPlayer().state,

    readPlayerTile(i: number): TileReading & {mark: string | null; time: string | null} {
        const r = readCanvas(playerCanvases[i], needPlayer().state.cameras[i].rotation);
        const o = playerTiles[i].overlay;
        return {...r, mark: o.mark, time: o.time};
    },

    events: () => events.slice(),

    async closePlayer(): Promise<void> {
        await player?.close();
        playerTiles.forEach(t => t.close());
        player = null;
    },

    async takeFilesChecks(folder: string) {
        const m = await playerModule();
        const files = await m.electronTakeFiles(folder);
        try {
            return await runTakeFilesChecks(files);
        } finally {
            await files.close();
        }
    },

    async openFiles(folder: string): Promise<{id: number; entries: TakeFiles['entries']}> {
        const m = await playerModule();
        const files = await m.electronTakeFiles(folder);
        const id = nextFiles++;
        openFiles.set(id, files);
        return {id, entries: files.entries};
    },

    /** A read through the Electron TakeFiles: the bytes as base64, or the error text. */
    async readRange(id: number, path: string, start: number, end: number): Promise<{ok: true; base64: string} | {ok: false; error: string}> {
        try {
            return {ok: true, base64: toBase64(await openFiles.get(id)!.readRange(path, start, end))};
        } catch (e) {
            return {ok: false, error: String(e)};
        }
    },

    async closeFiles(id: number): Promise<void> {
        await openFiles.get(id)?.close();
        openFiles.delete(id);
    },
};

window.harness = harness;
window.bench = makeBench({player: needPlayer, canvases: () => playerCanvases});
