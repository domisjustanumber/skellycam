// Helpers of the unit tests. Each product module is loaded with a dynamic import inside the test, so a
// missing module fails only the tests that use it.
import {mkdtempSync, rmSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import type {TestContext} from 'node:test';
import type {OpenTakeOptions, TakePlayer, TileUpdate, DecodedImage} from '../../index.ts';
import type {TakeFiles} from '../../files/take-files.ts';
import {nodeTakeFiles} from '../fixtures/node-take-files.ts';
import type {NodeTakeFilesOptions} from '../fixtures/node-take-files.ts';
import {writeTake} from '../fixtures/take.ts';
import type {BuiltTake, Identity, TakePlan} from '../fixtures/take.ts';
import {planOf} from '../fixtures/takes.ts';

export type PlayerModule = typeof import('../../index.ts');

export function product<T>(rel: string): Promise<T> {
    return import(new URL(`../../${rel}`, import.meta.url).href) as Promise<T>;
}

export const player = () => product<PlayerModule>('index.ts');

export function tempRoot(t: TestContext): string {
    const dir = mkdtempSync(path.join(os.tmpdir(), 'skellycam-player-'));
    t.after(() => rmSync(dir, {recursive: true, force: true}));
    return dir;
}

export interface ReadRecord {
    kind: 'range' | 'whole';
    path: string;
    start: number;
    end: number;
}

/** A TakeFiles wrapper that records each read and counts the reads in flight. */
export function spyFiles(inner: TakeFiles): TakeFiles & {reads: ReadRecord[]; pending: () => number; failPath?: string} {
    let pending = 0;
    const reads: ReadRecord[] = [];
    const spy = {
        folderName: inner.folderName,
        entries: inner.entries,
        reads,
        pending: () => pending,
        failPath: undefined as string | undefined,
        async readRange(p: string, start: number, end: number, signal?: AbortSignal) {
            reads.push({kind: 'range', path: p, start, end});
            pending++;
            try {
                if (spy.failPath === p) throw new Error(`test read fault: ${p}`);
                return await inner.readRange(p, start, end, signal);
            } finally {
                pending--;
            }
        },
        async readWhole(p: string, maxBytes: number) {
            reads.push({kind: 'whole', path: p, start: 0, end: -1});
            pending++;
            try {
                if (spy.failPath === p) throw new Error(`test read fault: ${p}`);
                return await inner.readWhole(p, maxBytes);
            } finally {
                pending--;
            }
        },
        close: () => inner.close(),
    };
    return spy;
}

/** A tile double for the player tests: it shows the last image that it got, as `Tile` does (8.3). */
export class FakeTile {
    updates: TileUpdate[] = [];
    image: Uint8Array | null = null;
    mark: TileUpdate['mark'] = null;
    label: TileUpdate['label'] = null;
    closed = false;

    update(u: TileUpdate): Promise<'drawn' | 'superseded'> {
        this.updates.push(u);
        if (u.jpeg) this.image = u.jpeg;
        this.mark = u.mark;
        this.label = u.label;
        return Promise.resolve('drawn');
    }

    setOptions(): void {}

    close(): void {
        this.closed = true;
    }
}

/** A scripted display refresh and time source. */
export class FakeLoop {
    now = 0;
    private next = 1;
    private callbacks = new Map<number, (now: number) => void>();
    readonly frameLoop = {
        now: () => this.now,
        request: (cb: (now: number) => void) => {
            const id = this.next++;
            this.callbacks.set(id, cb);
            return id;
        },
        cancel: (id: number) => void this.callbacks.delete(id),
    };

    get waiting(): number {
        return this.callbacks.size;
    }

    /** One display refresh after `ms` milliseconds. */
    refresh(ms: number): void {
        this.now += ms;
        const due = [...this.callbacks.values()];
        this.callbacks.clear();
        for (const cb of due) cb(this.now);
    }
}

export interface TestImage {
    identity: Identity | null;
    closed: boolean;
    displayWidth: number;
    displayHeight: number;
    close(): void;
}

/** A test decoder: it makes a closable image that knows its barcode. */
export function testDecoder(built: BuiltTake | null, delayMs: () => number = () => 0) {
    const images: TestImage[] = [];
    let inFlight = 0;
    let maxInFlight = 0;
    const decode = async (jpeg: Uint8Array): Promise<DecodedImage> => {
        inFlight++;
        maxInFlight = Math.max(maxInFlight, inFlight);
        try {
            const d = delayMs();
            if (d > 0) await new Promise(r => setTimeout(r, d));
            const img: TestImage = {
                identity: built ? built.identify(jpeg) : null, displayWidth: 256, displayHeight: 128, closed: false,
                close() {
                    img.closed = true;
                },
            };
            images.push(img);
            return img;
        } finally {
            inFlight--;
        }
    };
    return {
        decode, images,
        maxInFlight: () => maxInFlight,
        open: (camera?: number) => images.filter(i => !i.closed && (camera === undefined || i.identity?.camera === camera)).length,
    };
}

/** A canvas double for `Tile` under Node: the 2D context records each call. */
export function fakeCanvas(width = 640, height = 320) {
    const calls: [string, unknown[]][] = [];
    const state: Record<string | symbol, unknown> = {};
    const ctx = new Proxy(state, {
        get(target, prop) {
            if (prop in target) return target[prop];
            return (...args: unknown[]) => {
                calls.push([String(prop), args]);
                if (prop === 'measureText') return {width: String(args[0]).length * 7};
                return undefined;
            };
        },
        set(target, prop, value) {
            target[prop] = value;
            return true;
        },
    });
    const canvas = {
        width, height, clientWidth: width, clientHeight: height, title: '',
        getContext: () => ctx,
        addEventListener() {}, removeEventListener() {},
    };
    return {canvas: canvas as unknown as HTMLCanvasElement, calls, drawn: () => calls.filter(c => c[0] === 'drawImage').map(c => c[1][0] as TestImage)};
}

/** Wait until no read is in flight and the event loop is quiet. */
export async function settle(files?: {pending: () => number}, maxMs = 3000): Promise<void> {
    const end = Date.now() + maxMs;
    let quiet = 0;
    while (Date.now() < end && quiet < 3) {
        await new Promise(r => setTimeout(r, 3));
        quiet = !files || files.pending() === 0 ? quiet + 1 : 0;
    }
}

export interface Opened {
    built: BuiltTake;
    files: ReturnType<typeof spyFiles>;
    player: TakePlayer;
    tiles: FakeTile[];
    loop: FakeLoop;
    decoder: ReturnType<typeof testDecoder>;
    /** The identity of the image that tile c shows, and its mark. */
    shown(c: number): {identity: Identity | null; mark: TileUpdate['mark']};
    settle(): Promise<void>;
}

export async function openFixture(
    t: TestContext,
    planOrName: TakePlan | string,
    options: {files?: (built: BuiltTake) => NodeTakeFilesOptions; open?: Partial<OpenTakeOptions>; attach?: boolean} = {},
): Promise<Opened> {
    const {openTake} = await player();
    const built = writeTake(tempRoot(t), typeof planOrName === 'string' ? planOf(planOrName) : planOrName);
    const files = spyFiles(await nodeTakeFiles(built.dir, options.files?.(built)));
    const loop = new FakeLoop();
    const decoder = testDecoder(built);
    const p = await openTake(files, {frameLoop: loop.frameLoop, decode: decoder.decode, ...options.open});
    t.after(() => p.close());
    const tiles = p.state.cameras.map(() => new FakeTile());
    if (options.attach !== false) tiles.forEach((tile, i) => p.attachTile(i, tile as never));
    const o: Opened = {
        built, files, player: p, tiles, loop, decoder,
        shown: c => ({identity: built.identify(tiles[c].image), mark: tiles[c].mark}),
        settle: () => settle(files),
    };
    await o.settle();
    return o;
}

/** Seek and wait for the reads and the tile updates. */
export async function seek(o: Opened, k: number): Promise<void> {
    o.player.seekFrame(k);
    await o.settle();
}

export function cameraIndexOf(o: Opened, label: string): number {
    const i = o.player.state.cameras.findIndex(c => c.label === label);
    if (i < 0) throw new Error(`no camera ${label}`);
    return i;
}
