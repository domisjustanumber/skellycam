// Helpers of the 4b unit tests (specs/preview-4b.md 7.4). Each product module is loaded with a dynamic import inside
// the test, so a missing module fails only the tests that use it, with "product module missing: <path>".
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import type {TileUpdate} from '../../../../../player/index.ts';

const SERVER = new URL('../../../', import.meta.url); // src/services/server/

/** Load a product module of src/services/server/ (for example 'preview/camera-message.ts'). */
export async function product<T>(rel: string): Promise<T> {
    try {
        return (await import(new URL(rel, SERVER).href)) as T;
    } catch (error) {
        if ((error as {code?: string}).code === 'ERR_MODULE_NOT_FOUND' && String(error).includes(rel.split('/').pop()!)) {
            assert.fail(`product module missing: src/services/server/${rel}`);
        }
        throw error;
    }
}

export type CameraMessageModule = typeof import('../../camera-message.ts');
export type PreviewTilesModule = typeof import('../../preview-tiles.ts');
export type ServerMessagesModule = typeof import('../../server-messages.ts');
export type FramerateStoreModule = typeof import('../../../server-helpers/framerate-store.ts');

export const cameraMessage = () => product<CameraMessageModule>('preview/camera-message.ts');
export const previewTiles = () => product<PreviewTilesModule>('preview/preview-tiles.ts');
export const serverMessages = () => product<ServerMessagesModule>('preview/server-messages.ts');
export const framerateStore = () => product<FramerateStoreModule>('server-helpers/framerate-store.ts');

export interface FixtureCase {
    name: string;
    input: {camera_id: string; result: string; flags: number; frame_number: string; arrival_ns: string; rotation_cw_deg: number; jpeg_hex: string};
    message_hex: string;
}

/** The shared fixture of T-PRV-25 (skellycam/tests/preview/write_camera_message_fixture.py). */
export function fixtureCases(): FixtureCase[] {
    return JSON.parse(readFileSync(new URL('../camera-messages.json', import.meta.url), 'utf8')).cases;
}

export function bufferOf(bytes: Uint8Array): ArrayBuffer {
    return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

export function hexBytes(hex: string): Uint8Array {
    return Uint8Array.from(hex.match(/../g) ?? [], h => parseInt(h, 16));
}

/** A camera message written at the offsets of table 3.2 of preview.md, independent of the product parser. */
export function message(o: {camera: string; frame: number | bigint; flags?: number; rotation?: number; jpeg?: Uint8Array; arrivalNs?: bigint}): ArrayBuffer {
    const flagged = ((o.flags ?? 0) & 0x0f) !== 0;
    const jpeg = flagged ? new Uint8Array(0) : (o.jpeg ?? Uint8Array.of(0xff, 0xd8, Number(o.frame) & 0xff, 0xff, 0xd9));
    const out = new Uint8Array(48 + jpeg.length);
    const view = new DataView(out.buffer);
    view.setUint8(0, 1);
    view.setUint32(4, o.flags ?? 0, true);
    view.setBigInt64(8, BigInt(o.frame), true);
    view.setBigInt64(16, o.arrivalNs ?? BigInt(o.frame) * 33_333_333n, true);
    view.setUint32(24, o.rotation ?? 0, true);
    view.setUint32(28, jpeg.length, true);
    for (let i = 0; i < o.camera.length; i++) out[32 + i] = o.camera.charCodeAt(i);
    out.set(jpeg, 48);
    return out.buffer;
}

type Result = 'drawn' | 'superseded';

/** A tile double: each update waits on a promise that the test resolves (`resolve`), unless `auto` is set. */
export class FakeTile {
    updates: TileUpdate[] = [];
    private waiting: ((r: Result) => void)[] = [];
    auto: Result | null;
    constructor(auto: Result | null = null) {
        this.auto = auto; // no parameter property: Node type stripping does not take one
    }

    update(u: TileUpdate): Promise<Result> {
        this.updates.push(u);
        if (this.auto) return Promise.resolve(this.auto);
        return new Promise(resolve => this.waiting.push(resolve));
    }

    /** Resolve the oldest update in flight. */
    async resolve(result: Result = 'drawn'): Promise<void> {
        const next = this.waiting.shift();
        assert.ok(next, 'no update in flight');
        next(result);
        await flush();
    }

    get inFlight(): number {
        return this.waiting.length;
    }

    get last(): TileUpdate | undefined {
        return this.updates.at(-1);
    }

    frames(): (number | null | undefined)[] {
        return this.updates.map(u => u.label?.frame);
    }
}

/** Let the resolved promises of the fake tiles run their callbacks (no timer of the product is waited for). */
export async function flush(): Promise<void> {
    for (let i = 0; i < 5; i++) await new Promise<void>(resolve => setImmediate(resolve));
}

/** A fake `sendReady`, a fake `onDrawn` and a fake `now`. */
export function fakes() {
    const ready: string[] = [];
    const drawn: [string, number][] = [];
    const clock = {ms: 1000};
    return {
        ready, drawn, clock,
        sendReady: (cameraId: string) => void ready.push(cameraId),
        onDrawn: (cameraId: string, atMs: number) => void drawn.push([cameraId, atMs]),
        now: () => clock.ms,
    };
}

/** `console.error`, recorded while `body` runs. */
export async function recordConsoleErrors(body: (errors: unknown[][]) => Promise<void> | void): Promise<unknown[][]> {
    const errors: unknown[][] = [];
    const original = console.error;
    console.error = (...args: unknown[]) => void errors.push(args);
    try {
        await body(errors);
    } finally {
        console.error = original;
    }
    return errors;
}
