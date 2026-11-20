// The recording manifest (specs/player.md sections 6.2 and 6.3). The reader uses only `take_uuid`,
// `state`, `cameras[].timing` and `warnings`.
import type {TakeFiles} from '../files/take-files.ts';

export const MANIFEST = 'recording_manifest.json';
const MAX_BYTES = 16 * 1024 * 1024;

export interface Manifest {
    takeUuid: string;
    recording: boolean;
    timings: Set<string>;
    warnings: {code: string; cameraKey: string | null; detail: string | null}[];
}

/** The manifest, or null when it is not valid JSON or not a manifest of this format. */
export async function readManifest(files: TakeFiles): Promise<Manifest | null> {
    try {
        const m = JSON.parse(new TextDecoder().decode(await files.readWhole(MANIFEST, MAX_BYTES)));
        if (m?.skellyfileformat !== 'recording_manifest' || typeof m.take_uuid !== 'string') return null;
        const list = (v: unknown): Record<string, unknown>[] => (Array.isArray(v) ? v.filter(x => x && typeof x === 'object') : []);
        const text = (v: unknown) => (typeof v === 'string' ? v : null);
        return {
            takeUuid: m.take_uuid,
            recording: m.state === 'recording',
            timings: new Set(list(m.cameras).map(c => text(c.timing)).filter(t => t !== null)),
            warnings: list(m.warnings).filter(w => typeof w.code === 'string')
                .map(w => ({code: w.code as string, cameraKey: text(w.camera_key), detail: text(w.detail)})),
        };
    } catch {
        return null;
    }
}

/** N of "camera lost at frame N" from the `detail` of `camera_dead` (F-5), or null when it does not parse. */
export function deadFromDetail(detail: string | null): number | null {
    const m = /^last_frame=(none|0|[1-9][0-9]*) reason=/.exec(detail ?? '');
    if (!m) return null;
    return m[1] === 'none' ? 0 : Number(m[1]) + 1;
}
