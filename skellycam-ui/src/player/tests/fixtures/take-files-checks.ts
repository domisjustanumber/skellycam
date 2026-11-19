// The shared TakeFiles check suite of specs/player.md section 5.1 [L8]. It uses only the web platform,
// so the unit tests run it on the Node implementation (T-PLAY-39) and the harness page runs it on the
// Electron implementation (T-PLAY-64).
import type {TakeFiles} from '../../files/take-files.ts';

export const SUITE_FOLDER = 'take_files_suite';
export const SUITE_FILES = [
    {path: 'recording_manifest.json', size: 500, seed: 1},
    {path: 'synchronized_videos/a.csv', size: 1000, seed: 3},
    {path: 'synchronized_videos/a.mkv', size: 300_000, seed: 2},
];
/** A file in another subfolder: the folder holds it, but it is not in the entries (SFF-721). */
export const SUITE_HIDDEN = 'annotated_videos/x.mp4';

export function patternBytes(seed: number, start: number, end: number): Uint8Array<ArrayBuffer> {
    const out = new Uint8Array(end - start);
    for (let i = start; i < end; i++) out[i - start] = (i * 31 + seed * 17) & 255;
    return out;
}

export interface CheckResult {
    name: string;
    ok: boolean;
    detail: string;
}

const same = (a: Uint8Array, b: Uint8Array) => a.length === b.length && a.every((v, i) => v === b[i]);

async function rejects(p: Promise<unknown>): Promise<boolean> {
    try {
        await p;
        return false;
    } catch {
        return true;
    }
}

export async function runTakeFilesChecks(files: TakeFiles): Promise<CheckResult[]> {
    const results: CheckResult[] = [];
    const check = async (name: string, f: () => Promise<boolean | string>) => {
        try {
            const r = await f();
            results.push({name, ok: r === true, detail: r === true ? '' : String(r)});
        } catch (e) {
            results.push({name, ok: false, detail: String(e)});
        }
    };
    const mkv = SUITE_FILES[2];
    await check('folderName', async () => files.folderName === SUITE_FOLDER || `folderName ${files.folderName}`);
    await check('entries', async () => {
        const got = [...files.entries].map(e => `${e.path}:${e.size}`).sort();
        const want = SUITE_FILES.map(e => `${e.path}:${e.size}`).sort();
        return JSON.stringify(got) === JSON.stringify(want) || `entries ${JSON.stringify(got)}`;
    });
    for (const [label, start, end] of [['start', 0, 100], ['middle', 150_000, 150_137], ['end', mkv.size - 100, mkv.size]] as const) {
        await check(`readRange ${label}`, async () => same(await files.readRange(mkv.path, start, end), patternBytes(mkv.seed, start, end)));
    }
    await check('readRange past the snapshot fails', () => rejects(files.readRange(mkv.path, mkv.size - 10, mkv.size + 10)));
    await check('readWhole within the limit', async () => {
        const m = SUITE_FILES[0];
        return same(await files.readWhole(m.path, 16 * 1024 * 1024), patternBytes(m.seed, 0, m.size));
    });
    await check('readWhole above the limit fails', () => rejects(files.readWhole(mkv.path, 1000)));
    await check('readRange of a path not in the entries fails', () => rejects(files.readRange(SUITE_HIDDEN, 0, 10)));
    await check('readWhole of a path not in the entries fails', () => rejects(files.readWhole('nope.txt', 1000)));
    return results;
}
