// The decode and draw timing of the shared tile (specs/capture-timings.md section 7; ADR-W3VD). The host makes one
// TileTimings, gives a handle to each tile, sets `on`, and reads the summaries with takeSummaries(). Nothing goes
// to a server. No import: the boundary rule of specs/player.md 4.2 holds.

export type StepKind = 'work' | 'wait';
export type StepCadence = 'frame' | 'second' | 'event';

// A copy of STEPS and DELAYS of skellycam/core/capture_timings.py (table 3.1, section 4); T-TIM-24 compares them.
export const STEPS: Record<string, [StepKind, StepCadence, string]> = {
    camera_wait: ['wait', 'frame', 'camera_loop'],
    gate_wait: ['wait', 'frame', 'camera_loop'],
    camera_sample_copy: ['work', 'frame', 'camera_callback'],
    opencv_retrieve: ['work', 'frame', 'camera_loop'],
    jpeg_encode: ['work', 'frame', 'camera_loop'],
    capture_check: ['work', 'frame', 'camera_loop'],
    frame_hash: ['work', 'frame', 'camera_loop'],
    recorder_give: ['wait', 'frame', 'camera_loop'],
    ring_write: ['work', 'frame', 'camera_loop'],
    exposure_search_brightness: ['work', 'event', 'camera_loop'],
    diagnostics_publish: ['work', 'second', 'camera_loop'],
    take_start: ['work', 'event', 'camera_loop'],
    take_end: ['wait', 'event', 'camera_loop'],
    bgr_decode: ['work', 'frame', 'decode_thread'],
    bgr_ring_write: ['work', 'frame', 'decode_thread'],
    mkv_mux: ['work', 'frame', 'recorder_thread'],
    csv_row: ['work', 'frame', 'recorder_thread'],
    fsync: ['work', 'second', 'recorder_thread'],
    mkv_close: ['work', 'event', 'recorder_thread'],
    preview_ring_read: ['work', 'frame', 'main_process'],
    preview_pack: ['work', 'frame', 'main_process'],
    preview_send: ['work', 'frame', 'main_process'],
    ui_jpeg_decode: ['work', 'frame', 'ui_tile'],
    ui_draw: ['work', 'frame', 'ui_tile'],
};
export const DELAYS: Record<string, string> = {arrival_to_published: 'camera_loop', published_to_send: 'main_process', receive_to_draw: 'ui_tile'};

const CAPACITY = 512; // 5.1: the newest durations of a step
const TILE_IDS = ['ui_jpeg_decode', 'ui_draw', 'receive_to_draw'] as const;
export type TileTimingId = (typeof TILE_IDS)[number];

export interface Stats {
    n: number;
    p50_ms: number | null;
    p95_ms: number | null;
    max_ms: number | null;
}

export interface Summary {
    source: string;
    camera_group_id: string | null;
    camera_id: string | null;
    clock: string;
    seq: number;
    window_end_ns: number;
    window_s: number;
    steps: Record<string, {kind: StepKind; cadence: StepCadence; where: string} & Stats>;
    delays: Record<string, {where: string} & Stats>;
}

/** The input of the Python `build_summary`, with the same names; durations in integer nanoseconds. */
export interface SummaryInput {
    source: string;
    camera_group_id: string | null;
    camera_id: string | null;
    clock: string;
    seq: number;
    window_end_ns: number;
    window_ns: number;
    step_ids: readonly string[];
    windows: Record<string, [number, number[]]>;
}

/** 5.2 (Q840): milliseconds, rounded half up to 0.001 ms in integers, as the Python `to_ms`. */
const toMs = (ns: number) => Math.floor((ns + 500) / 1000) / 1000;

function stats(n: number, values: number[]): Stats {
    if (!n) return {n: 0, p50_ms: null, p95_ms: null, max_ms: null};
    const ordered = values.slice(-CAPACITY).sort((a, b) => a - b);
    const rank = (q: number) => toMs(ordered[Math.ceil(q * ordered.length) - 1]);
    return {n, p50_ms: rank(0.5), p95_ms: rank(0.95), max_ms: toMs(ordered[ordered.length - 1])};
}

/** The summary of 6.1, as `build_summary` of capture_timings.py: each id of `step_ids` and of `windows`. */
export function buildSummary(i: SummaryInput): Summary {
    const ids = new Set([...i.step_ids, ...Object.keys(i.windows)]);
    const steps: Summary['steps'] = {};
    const delays: Summary['delays'] = {};
    for (const [id, [kind, cadence, where]] of Object.entries(STEPS)) {
        if (ids.has(id)) steps[id] = {kind, cadence, where, ...stats(...(i.windows[id] ?? [0, []]))};
    }
    for (const [id, where] of Object.entries(DELAYS)) {
        if (ids.has(id)) delays[id] = {where, ...stats(...(i.windows[id] ?? [0, []]))};
    }
    return {source: i.source, camera_group_id: i.camera_group_id, camera_id: i.camera_id, clock: i.clock, seq: i.seq,
        window_end_ns: i.window_end_ns, window_s: Math.floor((i.window_ns + 500_000) / 1_000_000) / 1000, steps, delays};
}

/** The samples of one tile (7): 512 durations in milliseconds and a total for each id. One thread writes and reads. */
export class TileTimingHandle {
    readonly cameraId: string;
    cameraGroupId: string | null;
    #owner: TileTimings;
    #values = {ui_jpeg_decode: new Float64Array(CAPACITY), ui_draw: new Float64Array(CAPACITY), receive_to_draw: new Float64Array(CAPACITY)};
    #totals: Record<TileTimingId, number> = {ui_jpeg_decode: 0, ui_draw: 0, receive_to_draw: 0};
    #read: Record<TileTimingId, number> = {ui_jpeg_decode: 0, ui_draw: 0, receive_to_draw: 0};
    #seq = 0;
    #windowStart: number;

    constructor(owner: TileTimings, cameraId: string, cameraGroupId: string | null) {
        this.#owner = owner;
        this.cameraId = cameraId;
        this.cameraGroupId = cameraGroupId;
        this.#windowStart = owner.now();
    }

    /** `on` of the TileTimings: the one branch of a bracket when off. */
    get on(): boolean {
        return this.#owner.on;
    }

    now(): number {
        return this.#owner.now();
    }

    add(id: TileTimingId, ms: number): void {
        const total = this.#totals[id];
        this.#values[id][total % CAPACITY] = ms;
        this.#totals[id] = total + 1;
    }

    /** Close the window at `end`: the summary of the samples since the last call (5.2). */
    summary(end: number): Summary {
        const windows: SummaryInput['windows'] = {};
        for (const id of TILE_IDS) {
            const total = this.#totals[id];
            const values = this.#values[id];
            const newest: number[] = [];
            for (let k = Math.max(this.#read[id], total - CAPACITY); k < total; k++) newest.push(Math.round(values[k % CAPACITY] * 1_000_000));
            windows[id] = [total - this.#read[id], newest];
            this.#read[id] = total;
        }
        const start = this.#windowStart;
        this.#windowStart = end;
        return buildSummary({source: 'ui', camera_group_id: this.cameraGroupId, camera_id: this.cameraId, clock: 'performance.now',
            seq: this.#seq++, window_end_ns: Math.round(end * 1_000_000), window_ns: Math.round((end - start) * 1_000_000),
            step_ids: TILE_IDS, windows});
    }
}

/** One for each page (7). `on` is the switch; `now` defaults to performance.now. */
export class TileTimings {
    on = false;
    readonly now: () => number;
    #handles = new Map<string, TileTimingHandle>();

    constructor(now: () => number = () => performance.now()) {
        this.now = now;
    }

    /** One handle for each camera id; a second call gives the same handle and sets its group id (ADR-W3VD item 3). */
    handle(cameraId: string, cameraGroupId: string | null): TileTimingHandle {
        let h = this.#handles.get(cameraId);
        if (h) h.cameraGroupId = cameraGroupId;
        else this.#handles.set(cameraId, (h = new TileTimingHandle(this, cameraId, cameraGroupId)));
        return h;
    }

    /** Close the window of each handle: one summary for each handle, also when `on` is false. */
    takeSummaries(): Summary[] {
        const end = this.now();
        return [...this.#handles.values()].map(h => h.summary(end));
    }
}
