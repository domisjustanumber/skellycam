// The master clock and the player (specs/player.md sections 4.4, 7 and 9). One clock holds the take
// time t for all cameras; each camera has a prefetch queue of decoded images and one read in flight.
import type {TakeFiles} from '../files/take-files.ts';
import {BlockMismatch, walkBlocks} from '../reader/matroska.ts';
import {readTake} from '../reader/take.ts';
import type {Camera, CameraState, TakeState} from '../reader/take.ts';
import {decodeJpeg} from '../tile/tile.ts';
import type {DecodedImage, JpegDecoder, Tile, TileMark} from '../tile/tile.ts';
import {chooseMark, frameAt, imageChooser} from './choose.ts';

export interface FrameLoop {
    now(): number;
    request(cb: (now: number) => void): number;
    cancel(id: number): void;
}

export interface OpenTakeOptions {
    initialFrame?: number;
    decode?: JpegDecoder;
    frameLoop?: FrameLoop;
}

export interface PlayerState {
    playing: boolean;
    speed: number;
    loop: boolean;
    frame: number;
    frameCount: number;
    time: number;
    firstTime: number;
    lastTime: number;
    nominalFps: number;
    take: TakeState;
    cameras: CameraState[];
}

export interface PlayerEvent {
    type: 'state' | 'frame' | 'error';
    state: PlayerState;
    error?: {camera: number | null; message: string};
}

export interface TakePlayer {
    readonly state: PlayerState;
    play(): void;
    pause(): void;
    step(frames: number): void;
    seekFrame(k: number): void;
    setSpeed(rate: number): void;
    setLoop(on: boolean): void;
    setTileOptions(o: {showLabel: boolean; timeFormat: 'seconds' | 'timecode'}): void;
    attachTile(cameraIndex: number, tile: Tile): () => void;
    on(event: 'state' | 'frame' | 'error', listener: (e: PlayerEvent) => void): () => void;
    close(): Promise<void>;
}

const EVENT_MS = 200;               // events at most 5 times per second during play (4.4)
const READ_LIMIT = 4 * 1024 * 1024; // one read holds at most 4 MiB (9.1)
// shortcut: the prefetch assumes a 60 Hz display; use the measured refresh if a test shows a need
const REFRESH_NS = 1e9 / 60;
const LOOK_AHEAD = 600;             // the most display refreshes that the prefetch looks ahead

interface Queued {
    row: number;
    jpeg: Uint8Array;
    image: DecodedImage;
}

interface Slot {
    cam: Camera;
    choose: (t: number, frameCount: number) => number | null;
    starts: number[];               // the start of the range of each row: the end of the block before it
    tile: Tile | null;
    queue: Queued[];
    shownRow: number | null | undefined;   // undefined: the tile has nothing from the player
    shownKey: string;
    shownGen: number;              // the request (seek) whose image is on the tile
    gen: number;
    pump: Promise<void> | null;    // the running read and decode loop, for close()
    busy: boolean;
    readError: boolean;
}

const refused = (s: string) => s === 'invalid' || s === 'unsupported_version';
const defaultLoop: FrameLoop = {
    now: () => performance.now(),
    request: cb => requestAnimationFrame(cb),
    cancel: id => cancelAnimationFrame(id),
};

export async function openTake(files: TakeFiles, options: OpenTakeOptions = {}): Promise<TakePlayer> {
    const take = await readTake(files);
    return new Player(files, take, options);
}

class Player implements TakePlayer {
    state: PlayerState;
    #files: TakeFiles;
    #take: Awaited<ReturnType<typeof readTake>>;
    #decode: JpegDecoder;
    #loop: FrameLoop;
    #slots: Slot[];
    #listeners = {state: new Set<(e: PlayerEvent) => void>(), frame: new Set<(e: PlayerEvent) => void>(), error: new Set<(e: PlayerEvent) => void>()};
    #playing = false;
    #speed = 1;
    #looping = false;
    #frame = 0;
    #time = 0;
    #last = 0;
    #raf: number | null = null;
    #eventAt = 0;
    #frameSent = -1;
    #tileOptions: {showLabel: boolean; timeFormat: 'seconds' | 'timecode'} | null = null;
    #closed = false;
    #closing: Promise<void> | null = null;

    constructor(files: TakeFiles, take: Awaited<ReturnType<typeof readTake>>, options: OpenTakeOptions) {
        this.#files = files;
        this.#take = take;
        this.#decode = options.decode ?? decodeJpeg;
        this.#loop = options.frameLoop ?? defaultLoop;
        this.#slots = take.cameras.map(cam => {
            const starts: number[] = [];
            let end = cam.firstCluster;
            cam.offset.forEach((o, k) => {
                starts.push(end);
                if (o !== null) end = o + cam.size[k]!;
            });
            return {cam, choose: imageChooser(cam.times, cam.missing), starts, tile: null, queue: [], shownRow: undefined, shownKey: '', shownGen: -1, gen: 0, pump: null, busy: false, readError: false};
        });
        const K = take.frameCount;
        this.#frame = K ? Math.max(0, Math.min(K - 1, options.initialFrame ?? 0)) : 0;
        this.#time = K ? take.frameTimes[this.#frame] : 0;
        this.state = this.#snapshot();
    }

    get #K(): number {
        return this.#take.frameCount;
    }

    play(): void {
        if (this.#closed || this.#playing || !this.#K) return;
        if (this.#frame === this.#K - 1) this.#moveTo(0);
        this.#playing = true;
        this.#last = this.#eventAt = this.#loop.now();
        this.#raf = this.#loop.request(this.#tick);
        this.#changed(true, false);
    }

    pause(): void {
        if (!this.#playing) return;
        this.#stop();
        this.#time = this.#take.frameTimes[this.#frame];
        this.#all();
        this.#changed(true, this.#frame !== this.#frameSent);
    }

    step(frames: number): void {
        this.#stop();
        this.seekFrame(this.#frame + frames);
    }

    seekFrame(k: number): void {
        if (this.#closed || !this.#K) return;
        this.#moveTo(Math.max(0, Math.min(this.#K - 1, Math.round(k))));
        this.#all();
        this.#changed(true, true);
    }

    setSpeed(rate: number): void {
        this.#speed = rate;
        this.#changed(true, false);
    }

    setLoop(on: boolean): void {
        this.#looping = on;
        this.#changed(true, false);
    }

    setTileOptions(o: {showLabel: boolean; timeFormat: 'seconds' | 'timecode'}): void {
        this.#tileOptions = o;
        for (const s of this.#slots) s.tile?.setOptions(o);
    }

    attachTile(cameraIndex: number, tile: Tile): () => void {
        const s = this.#slots[cameraIndex];
        s.tile = tile;
        s.shownRow = undefined;
        s.shownKey = '';
        if (this.#tileOptions) tile.setOptions(this.#tileOptions);
        this.#present(s);
        this.#pump(s);
        return () => {
            if (s.tile === tile) s.tile = null;
        };
    }

    on(event: 'state' | 'frame' | 'error', listener: (e: PlayerEvent) => void): () => void {
        this.#listeners[event].add(listener);
        return () => void this.#listeners[event].delete(listener);
    }

    close(): Promise<void> {
        this.#closing ??= (async () => {
            this.#closed = true;
            this.#stop();
            await Promise.allSettled(this.#slots.map(s => s.pump));
            for (const s of this.#slots) this.#clearQueue(s);
            await this.#files.close();
        })();
        return this.#closing;
    }

    // ---- the clock ----

    #tick = (now: number): void => {
        this.#raf = null;
        if (!this.#playing || this.#closed) return;
        const T = this.#take.frameTimes;
        this.#time = Math.round(this.#time + this.#speed * (now - this.#last) * 1e6);
        this.#last = now;
        if (this.#time >= T[this.#K - 1]) {
            if (this.#looping) this.#moveTo(0);
            else {
                this.#stop();
                this.#time = T[this.#K - 1];
                this.#frame = this.#K - 1;
            }
        } else {
            this.#frame = Math.max(this.#frame, frameAt(T, this.#time));
        }
        this.#all();
        const due = !this.#playing || now - this.#eventAt >= EVENT_MS;
        if (due) this.#eventAt = now;
        this.#changed(due, due && this.#frame !== this.#frameSent);
        if (this.#playing) this.#raf = this.#loop.request(this.#tick);
    };

    #stop(): void {
        this.#playing = false;
        if (this.#raf !== null) this.#loop.cancel(this.#raf);
        this.#raf = null;
    }

    /** k* and t for a seek or a loop: the queues empty, the newest target wins (7.5). */
    #moveTo(k: number): void {
        this.#frame = k;
        this.#time = this.#take.frameTimes[k];
        for (const s of this.#slots) {
            s.gen++;
            this.#clearQueue(s);
        }
    }

    #all(): void {
        for (const s of this.#slots) {
            this.#present(s);
            this.#pump(s);
        }
    }

    #snapshot(): PlayerState {
        const T = this.#take.frameTimes;
        return {
            playing: this.#playing, speed: this.#speed, loop: this.#looping, frame: this.#frame, frameCount: this.#K,
            time: this.#time, firstTime: T[0] ?? 0, lastTime: T[this.#K - 1] ?? 0, nominalFps: this.#take.nominalFps,
            take: {...this.#take.take, warnings: [...this.#take.take.warnings]},
            cameras: this.#slots.map(s => ({...s.cam.info, warnings: [...s.cam.info.warnings]})),
        };
    }

    #changed(stateEvent: boolean, frameEvent: boolean): void {
        this.state = this.#snapshot();
        if (stateEvent) this.#emit({type: 'state', state: this.state});
        if (frameEvent) {
            this.#frameSent = this.#frame;
            this.#emit({type: 'frame', state: this.state});
        }
    }

    #emit(e: PlayerEvent): void {
        for (const l of this.#listeners[e.type]) l(e);
    }

    // ---- the tiles ----

    #mark(s: Slot): TileMark | null {
        const info = s.cam.info;
        if (refused(info.state)) return {kind: 'not_readable', reason: info.reason ?? info.state};
        if (s.readError) return {kind: 'read_error'};
        if (info.state === 'damaged') return {kind: 'damaged', frame: info.damagedAt!};
        const m = chooseMark(s.cam.missing, info.deadFrom, this.#frame);
        if (m) return m;
        return info.state === 'unfinished' || this.#take.recording ? {kind: 'unfinished'} : null;
    }

    /** Give the tile the image that the rule of 7.3 gives for t, when it is decoded, and the mark of k*. */
    #present(s: Slot): void {
        if (!s.tile || this.#closed) return;
        const mark = this.#mark(s);
        const playable = !refused(s.cam.info.state) && !s.readError && this.#K > 0;
        const target = playable ? s.choose(this.#time, this.#K) : s.shownRow ?? null;
        let entry: Queued | undefined;
        if (target !== null && target !== s.shownRow) {
            entry = s.queue.find(q => q.row === target);
            // during play, an older image of the queue is better than none (9.2)
            if (!entry && this.#playing) entry = s.queue.filter(q => q.row < target && q.row > (s.shownRow ?? -1)).at(-1);
            if (!entry) return;
            s.queue = s.queue.filter(q => {
                if (q.row < entry!.row) q.image.close();
                return q.row > entry!.row;
            });
        }
        this.#send(s, entry ? entry.row : target, entry, mark, s.gen);
    }

    #send(s: Slot, row: number | null, entry: Queued | undefined, mark: TileMark | null, gen: number): void {
        const key = `${row}|${this.#frame}|${JSON.stringify(mark)}`;
        if (!entry && key === s.shownKey) return;
        s.shownKey = key;
        s.shownGen = gen;
        const blank = row === null && s.shownRow !== null;
        s.shownRow = row;
        void s.tile!.update({
            jpeg: entry ? entry.jpeg : null, image: entry?.image, blank: blank || undefined,
            rotationCwDeg: s.cam.info.rotation, rateText: null, cameraState: null, mark,
            label: {
                frame: this.#frame, frameDigits: String(this.#K).length, camera: s.cam.info.label,
                timeNs: row === null ? null : s.cam.times[row], nominalFps: s.cam.nominalFps,
            },
        });
    }

    #clearQueue(s: Slot): void {
        for (const q of s.queue) q.image.close();
        s.queue = [];
    }

    // ---- the prefetch ----

    /** The rows to read next: the target, then during play the rows of the next refreshes (9.1, 9.3). */
    #plan(s: Slot): number[] {
        const K = this.#K;
        if (refused(s.cam.info.state) || s.readError || !K) return [];
        const target = s.choose(this.#time, K);
        // images older than the target are never shown, except the newest one as a fallback during play
        const drop = target === null ? [] : s.queue.filter(q => q.row < target).slice(0, this.#playing ? -1 : undefined);
        for (const q of drop) q.image.close();
        s.queue = s.queue.filter(q => !drop.includes(q));
        const space = Math.min(8, Math.max(2, Math.floor(64 / this.#slots.length))) - s.queue.length;
        if (space <= 0) return [];
        const have = (r: number) => r === s.shownRow || s.queue.some(q => q.row === r);
        const rows: number[] = [];
        if (target !== null && !have(target)) rows.push(target);
        const end = this.#take.frameTimes[K - 1];
        for (let i = 1; this.#playing && rows.length < space && i <= LOOK_AHEAD; i++) {
            const t = this.#time + i * this.#speed * REFRESH_NS;
            const r = s.choose(t, K);
            if (r !== null && r > (rows.at(-1) ?? target ?? -1) && !have(r)) rows.push(r);
            if (t > end) break;
        }
        // one read: from the first row, up to 4 MiB
        const from = s.starts[rows[0]];
        return rows.filter((r, i) => i === 0 || s.cam.offset[r]! + s.cam.size[r]! - from <= READ_LIMIT);
    }

    #pump(s: Slot): void {
        if (s.busy || this.#closed) return;
        s.busy = true;
        s.pump = (async () => {
            try {
                for (let rows = this.#plan(s); rows.length && !this.#closed; rows = this.#plan(s)) {
                    const gen = s.gen;
                    const payloads = await this.#read(s, rows[0], rows.at(-1)!);
                    for (const row of rows) {
                        // a newer seek ends the prefetch of an older one, but not the read of its target
                        if (this.#closed || (gen !== s.gen && row !== rows[0])) break;
                        const jpeg = payloads.get(row)!;
                        const image = await this.#decode(jpeg);
                        if (gen !== s.gen || this.#closed) {
                            // 7.5: a finished decode of an older request is drawn when no newer image is on the tile
                            if (!this.#closed && s.tile && gen > s.shownGen) this.#send(s, row, {row, jpeg, image}, this.#mark(s), gen);
                            else image.close();
                            break;
                        }
                        s.queue.push({row, jpeg, image});
                        s.queue.sort((a, b) => a.row - b.row);
                        this.#present(s);
                    }
                }
            } catch (e) {
                if (this.#closed) return;
                if (e instanceof BlockMismatch) Object.assign(s.cam.info, {state: 'invalid', reason: 'bad_metadata'});
                else s.readError = true;
                this.#clearQueue(s);
                this.#present(s);
                this.#changed(false, false);
                this.#emit({type: 'error', state: this.state, error: {camera: this.#slots.indexOf(s), message: String(e)}});
            } finally {
                s.busy = false;
            }
        })();
    }

    /** One range read with the block check of 6.10; the payload of each row with byte fields. */
    async #read(s: Slot, from: number, to: number): Promise<Map<number, Uint8Array>> {
        const {cam} = s;
        const start = s.starts[from];
        const bytes = await this.#files.readRange(cam.info.name, start, cam.offset[to]! + cam.size[to]!);
        const rows: number[] = [];
        for (let r = from; r <= to; r++) if (cam.offset[r] !== null) rows.push(r);
        const payloads = walkBlocks(bytes, start, cam.videoTrack, rows.map(r => ({offset: cam.offset[r]!, size: cam.size[r]!})));
        return new Map(rows.map((r, i) => [r, payloads[i]]));
    }
}
