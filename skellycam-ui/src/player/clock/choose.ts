// The frame choice (specs/player.md sections 7.2 and 7.3). Times are integer nanoseconds; null is a row
// with no player time.
import type {TileMark} from '../tile/tile.ts';

/** T_k: the running maximum of the latest player time of each row; T_(k-1) when no camera has one. */
export function frameTimes(times: (number | null)[][], frameCount: number): number[] {
    let first = Infinity;
    for (const c of times) for (const v of c) if (v !== null && v < first) first = v;
    const out: number[] = [];
    let prev = -Infinity;
    for (let k = 0; k < frameCount; k++) {
        let best = prev;
        for (const c of times) if (c[k] !== null && c[k] !== undefined && c[k]! > best) best = c[k]!;
        // M7: row 0 has a time in a camera; else T_0 is the smallest time of the take
        out.push((prev = best === -Infinity ? first : best));
    }
    return out;
}

/** The largest k with T_k ≤ t, else 0. */
export function frameAt(frameTimes: number[], t: number): number {
    let lo = 0;
    let hi = frameTimes.length - 1;
    while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (frameTimes[mid] <= t) lo = mid;
        else hi = mid - 1;
    }
    return lo;
}

/** A chooser for one camera: the largest real row below K whose running-maximum time is at or before t. */
export function imageChooser(times: (number | null)[], missing: boolean[]): (t: number, frameCount: number) => number | null {
    const run: number[] = [];
    const lastReal: number[] = [];
    let max = -Infinity;
    let real = -1;
    times.forEach((v, k) => {
        if (v !== null) max = Math.max(max, v);
        if (v !== null && !missing[k]) real = k;
        run.push(max);
        lastReal.push(real);
    });
    return (t, frameCount) => {
        let lo = -1;
        let hi = Math.min(frameCount, times.length) - 1;
        while (lo < hi) {
            const mid = (lo + hi + 1) >> 1;
            if (run[mid] <= t) lo = mid;
            else hi = mid - 1;
        }
        return lo < 0 || lastReal[lo] < 0 ? null : lastReal[lo];
    };
}

export function chooseImage(times: (number | null)[], missing: boolean[], t: number, frameCount: number): number | null {
    return imageChooser(times, missing)(t, frameCount);
}

export function chooseMark(missing: boolean[], deadFrom: number | null, k: number): TileMark | null {
    if (!missing[k]) return null;
    return deadFrom !== null && k >= deadFrom ? {kind: 'camera_lost', frame: deadFrom} : {kind: 'no_frame'};
}
