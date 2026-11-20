// The time axis of a camera file (specs/player.md section 6.8; SFF-777, SFF-781).
import type {FitSegment} from './sidecar.ts';

const TWO_53 = 2n ** 53n;

/** True when the segments hold each position from 0 to rows - 1, in order, with no gap and no overlap. */
function holdsEachPosition(fit: FitSegment[], rows: number): boolean {
    let next = 0;
    for (const s of fit) {
        if (s.posFirst !== next || s.posLast < s.posFirst || s.periodPs <= 0n) return false;
        next = s.posLast + 1;
    }
    return next === rows;
}

/** ⌊x / 1000⌋ for a negative x too: BigInt division rounds toward zero. */
const floorDiv1000 = (x: bigint) => (x - (((x % 1000n) + 1000n) % 1000n)) / 1000n;

/**
 * The player time of each row: the fitted time when the fit holds each position, else `arrival_ns`.
 * A row with no `arrival_ns` (a `missing` row with no time) has none. `null` for the result means a
 * fitted time with a magnitude of 2^53 or more (`bad_time`).
 */
export function playerTimes(arrival: (bigint | null)[], sfn: (bigint | null)[], fit: FitSegment[] | null):
    {times: (number | null)[]; fitted: boolean} | null {
    const fitted = fit !== null && holdsEachPosition(fit, arrival.length);
    const times: (number | null)[] = [];
    let seg = 0;
    for (let p = 0; p < arrival.length; p++) {
        if (arrival[p] === null) {
            times.push(null);
            continue;
        }
        let t = arrival[p]!;
        if (fitted) {
            while (fit[seg].posLast < p) seg++;
            const s = fit[seg];
            const first = sfn[s.posFirst];
            const d = sfn[p] !== null && first !== null ? sfn[p]! - first : BigInt(p - s.posFirst);
            t = s.t0 + floorDiv1000(d * s.periodPs);
            if (t >= TWO_53 || t <= -TWO_53) return null;
        }
        times.push(Number(t));
    }
    return {times, fitted};
}
