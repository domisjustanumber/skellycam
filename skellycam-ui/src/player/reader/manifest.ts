// The recording manifest (specs/player.md sections 6.2 and 6.3). The reader uses only `take_uuid`,
// `state`, `cameras[].timing`, `warnings` and `recording_name`, which names the capture info of the labels (8.4).
import type {TakeFiles} from '../files/take-files.ts';

export const MANIFEST = 'recording_manifest.json';
const MAX_BYTES = 16 * 1024 * 1024;

export interface Manifest {
    takeUuid: string;
    recordingName: string | null;
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
            recordingName: text(m.recording_name),
            recording: m.state === 'recording',
            timings: new Set(list(m.cameras).map(c => text(c.timing)).filter(t => t !== null)),
            warnings: list(m.warnings).filter(w => typeof w.code === 'string')
                .map(w => ({code: w.code as string, cameraKey: text(w.camera_key), detail: text(w.detail)})),
        };
    } catch {
        return null;
    }
}

/** The camera labels of 8.4 by `camera_key`, from `<recording_name>_info.json` of the used manifest. A camera
 * with no label here shows `camera_label`; no failure gives an error or a warning. */
export async function readLabels(files: TakeFiles, manifest: Manifest | null): Promise<Map<string, string>> {
    const labels = new Map<string, string>();
    const name = manifest?.recordingName;
    const file = `${name}_info.json`;
    if (!manifest || !name || /[/\\]/.test(name) || !files.entries.some(e => e.path === file)) return labels;
    try {
        const info = JSON.parse(new TextDecoder().decode(await files.readWhole(file, MAX_BYTES)));
        const configs = info?.camera_configs;
        if (info?.skellyfileformat !== 'capture_info' || info.take_uuid !== manifest.takeUuid || !configs || typeof configs !== 'object' || Array.isArray(configs)) return labels;
        for (const [key, config] of Object.entries(configs)) {
            const d = (config as {device?: {os_index?: unknown; os_name?: unknown}} | null)?.device;
            const index = d?.os_index;
            if (typeof index === 'number' && Number.isSafeInteger(index) && index >= 0 && typeof d?.os_name === 'string' && d.os_name.trim()) {
                labels.set(key, `Camera ${index} · ${d.os_name}`);
            }
        }
    } catch {
        // a capture info that does not read gives no label (8.4)
    }
    return labels;
}

/** N of "camera lost at frame N" from the `detail` of `camera_dead` (F-5), or null when it does not parse. */
export function deadFromDetail(detail: string | null): number | null {
    const m = /^last_frame=(none|0|[1-9][0-9]*) reason=/.exec(detail ?? '');
    if (!m) return null;
    return m[1] === 'none' ? 0 : Number(m[1]) + 1;
}
