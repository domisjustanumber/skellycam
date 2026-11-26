// src/services/server/server-helpers/framerate-store.ts

const MAX_DURATION_HISTORY = 1000;

/** Matches the shape sent by the Python backend's CurrentFramerate.model_dump() */
export type DetailedFramerate = {
    mean_frame_duration_ms: number;
    mean_frames_per_second: number;
    frame_duration_max: number;
    frame_duration_min: number;
    frame_duration_mean: number;
    frame_duration_stddev: number;
    frame_duration_median: number;
    frame_duration_coefficient_of_variation: number;
    calculation_window_size: number;
    framerate_source: string;
};

/** A single data point with the real timestamp of when it was recorded. */
export type TimestampedSample = {
    timestamp: number;
    value: number;
};

/**
 * Fixed-capacity ring buffer for timestamped numeric samples.
 * O(1) push. toArray() reuses its output array when possible to reduce GC pressure.
 */
class TimestampedRingBuffer {
    private readonly timestamps: Float64Array;
    private readonly values: Float64Array;
    private writeIndex: number = 0;
    private count: number = 0;

    /** Cached array from the last toArray() call — reused if count hasn't changed. */
    private _cachedArray: TimestampedSample[] | null = null;
    private _cachedVersion: number = 0;
    private _version: number = 0;

    constructor(capacity: number) {
        this.timestamps = new Float64Array(capacity);
        this.values = new Float64Array(capacity);
    }

    push(timestamp: number, value: number): void {
        this.timestamps[this.writeIndex] = timestamp;
        this.values[this.writeIndex] = value;
        this.writeIndex = (this.writeIndex + 1) % this.timestamps.length;
        if (this.count < this.timestamps.length) {
            this.count++;
        }
        this._version++;
    }

    /** Return contents in chronological order (oldest → newest). */
    toArray(): TimestampedSample[] {
        // Return cached array if no writes since last call
        if (this._cachedArray !== null && this._cachedVersion === this._version) {
            return this._cachedArray;
        }

        const result = new Array<TimestampedSample>(this.count);
        if (this.count < this.timestamps.length) {
            for (let i = 0; i < this.count; i++) {
                result[i] = {timestamp: this.timestamps[i], value: this.values[i]};
            }
        } else {
            for (let i = 0; i < this.count; i++) {
                const idx = (this.writeIndex + i) % this.timestamps.length;
                result[i] = {timestamp: this.timestamps[idx], value: this.values[idx]};
            }
        }

        this._cachedArray = result;
        this._cachedVersion = this._version;
        return result;
    }

    /** Copy current values into a Float64Array in chronological order (for stats computation). */
    valuesToFloat64Array(): Float64Array {
        const result = new Float64Array(this.count);
        this.copyValuesInto(result);
        return result;
    }

    /** Copy current values in chronological order into the provided array.
     *  The target must have at least `count` elements. */
    copyValuesInto(target: Float64Array): void {
        if (this.count < this.values.length) {
            for (let i = 0; i < this.count; i++) {
                target[i] = this.values[i];
            }
        } else {
            for (let i = 0; i < this.count; i++) {
                target[i] = this.values[(this.writeIndex + i) % this.values.length];
            }
        }
    }

    getCount(): number {
        return this.count;
    }

    clear(): void {
        this.writeIndex = 0;
        this.count = 0;
        this._cachedArray = null;
        this._version++;
    }
}

/** The statistics of a set of frame durations (ms), as `CurrentFramerate` of the server. */
function statsOf(values: Float64Array, source: string): DetailedFramerate | null {
    const count = values.length;
    if (count === 0) return null;
    let sum = 0;
    let min = Infinity;
    let max = -Infinity;
    for (let i = 0; i < count; i++) {
        const v = values[i];
        sum += v;
        if (v < min) min = v;
        if (v > max) max = v;
    }
    const mean = sum / count;
    let m2 = 0;
    for (let i = 0; i < count; i++) {
        const d = values[i] - mean;
        m2 += d * d;
    }
    const stddev = Math.sqrt(count > 1 ? m2 / count : 0);
    values.sort();
    const median = count % 2 === 0 ? (values[count / 2 - 1] + values[count / 2]) / 2 : values[Math.floor(count / 2)];
    return {
        mean_frame_duration_ms: mean,
        mean_frames_per_second: mean > 0 ? 1000 / mean : 0,
        frame_duration_mean: mean,
        frame_duration_median: median,
        frame_duration_min: min,
        frame_duration_max: max,
        frame_duration_stddev: stddev,
        frame_duration_coefficient_of_variation: mean > 0 ? stddev / mean : 0,
        calculation_window_size: count,
        framerate_source: source,
    };
}

/** One series of one camera: the windowed durations, and the current value. */
export interface SeriesValues {
    current: DetailedFramerate | null;
    aggregate: DetailedFramerate | null;
}

/** The values of one camera (specs/preview-4b.md 5.8). Captured and Displayed are two series; the four counts are
 * four numbers, never added [A7]. */
export interface CameraFramerate {
    captured: SeriesValues;
    displayed: SeriesValues;
    notShown: number;
    ringSkipped: number;
    oversize: number;
    replaced: number;
}

export interface FramerateUpdateLike {
    cameras: Record<string, {
        delivered_framerate: DetailedFramerate | null;
        not_shown_count: number;
        ring_skipped_count: number;
        oversize_count: number;
    }>;
}

export interface AppStateWithReplaced {
    state?: {camera_groups?: Record<string, {cameras?: Record<string, {status?: {replaced_count?: number} | null} | null>} | null>};
}

const DISPLAYED_GAP_MS = 1000;   // a longer time is a pause or a hidden page: not added (5.8)
const DISPLAYED_WINDOW_MS = 1000;   // the Displayed rate is over the frames drawn in the last 1 s [Q826]

class CameraRecord {
    capturedCurrent: DetailedFramerate | null = null;
    readonly capturedDurations = new TimestampedRingBuffer(MAX_DURATION_HISTORY);
    readonly displayedDurations = new TimestampedRingBuffer(MAX_DURATION_HISTORY);
    lastDrawnMs: number | null = null;
    recentDrawnMs: number[] = [];
    notShown = 0;
    ringSkipped = 0;
    oversize = 0;
    replaced = 0;
}

/**
 * Mutable store of the frame rates of each camera. It lives in a ref: no Redux, no re-render for an update.
 * The viewer reads it on its own schedule. Captured: each `delivered_framerate` of `framerate_update`. Displayed:
 * the times between the frames that this window drew (`recordDrawn`). The times are `performance.now()` values.
 */
export class FramerateStore {
    private readonly cameras = new Map<string, CameraRecord>();

    private record(cameraId: string): CameraRecord {
        let r = this.cameras.get(cameraId);
        if (!r) {
            r = new CameraRecord();
            this.cameras.set(cameraId, r);
        }
        return r;
    }

    recordFramerateUpdate(message: FramerateUpdateLike): void {
        for (const [cameraId, c] of Object.entries(message.cameras)) {
            const r = this.record(cameraId);
            r.capturedCurrent = c.delivered_framerate;
            if (c.delivered_framerate && c.delivered_framerate.mean_frame_duration_ms > 0) {
                r.capturedDurations.push(performance.now(), c.delivered_framerate.mean_frame_duration_ms);
            }
            r.notShown = c.not_shown_count;
            r.ringSkipped = c.ring_skipped_count;
            r.oversize = c.oversize_count;
        }
    }

    recordAppState(message: AppStateWithReplaced): void {
        for (const group of Object.values(message.state?.camera_groups ?? {})) {
            for (const [cameraId, camera] of Object.entries(group?.cameras ?? {})) {
                const n = camera?.status?.replaced_count;
                if (typeof n === 'number') this.record(cameraId).replaced = n;
            }
        }
    }

    /** A frame of the camera drawn at `atMs` (`onDrawn` of PreviewTiles). */
    recordDrawn(cameraId: string, atMs: number): void {
        const r = this.record(cameraId);
        if (r.lastDrawnMs !== null && atMs - r.lastDrawnMs <= DISPLAYED_GAP_MS) {
            r.displayedDurations.push(atMs, atMs - r.lastDrawnMs);
        }
        r.lastDrawnMs = atMs;
        r.recentDrawnMs.push(atMs);
        while (r.recentDrawnMs.length > 0 && r.recentDrawnMs[0] < atMs - DISPLAYED_WINDOW_MS) r.recentDrawnMs.shift();
    }

    cameraIds(): string[] {
        return [...this.cameras.keys()];
    }

    getCamera(cameraId: string): CameraFramerate | null {
        const r = this.cameras.get(cameraId);
        if (!r) return null;
        const drawn = r.recentDrawnMs;
        const recent = new Float64Array(Math.max(0, drawn.length - 1));
        for (let i = 1; i < drawn.length; i++) recent[i - 1] = drawn[i] - drawn[i - 1];
        return {
            captured: {current: r.capturedCurrent, aggregate: statsOf(r.capturedDurations.valuesToFloat64Array(), 'Captured')},
            displayed: {current: statsOf(recent, 'Displayed'), aggregate: statsOf(r.displayedDurations.valuesToFloat64Array(), 'Displayed')},
            notShown: r.notShown,
            ringSkipped: r.ringSkipped,
            oversize: r.oversize,
            replaced: r.replaced,
        };
    }

    /** The timestamped durations of one series of a camera, oldest first (for the timeline and the histogram). */
    recentDurations(cameraId: string, series: 'captured' | 'displayed'): TimestampedSample[] {
        const r = this.cameras.get(cameraId);
        if (!r) return [];
        return (series === 'captured' ? r.capturedDurations : r.displayedDurations).toArray();
    }

    clear(): void {
        this.cameras.clear();
    }
}
