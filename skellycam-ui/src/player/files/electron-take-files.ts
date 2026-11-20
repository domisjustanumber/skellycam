// The page client of the Electron take handler (specs/player.md sections 5.2 and 5.6).
import type {TakeFiles} from './take-files.ts';

interface TakeBridge {
    open(folderPath: string): Promise<{token: string; folderName: string; entries: {path: string; size: number}[]}>;
    close(token: string): Promise<void>;
}

export async function electronTakeFiles(folderPath: string): Promise<TakeFiles> {
    const bridge = (globalThis as {skellycamTake?: TakeBridge}).skellycamTake;
    if (!bridge) throw new Error('the take bridge is not exposed');
    const {token, folderName, entries} = await bridge.open(folderPath);
    const sizes = new Map(entries.map(e => [e.path, e.size]));
    const sizeOf = (path: string) => {
        const size = sizes.get(path);
        if (size === undefined) throw new Error(`not in the take: ${path}`);
        return size;
    };

    // 5.6: a 206 only with the asked start, a 200 only with the exact length; each other answer fails.
    const get = async (path: string, start: number, end: number, range: boolean, signal?: AbortSignal) => {
        const url = `skellycam-take://${token}/${path.split('/').map(encodeURIComponent).join('/')}`;
        const res = await fetch(url, {cache: 'no-store', signal, headers: range ? {Range: `bytes=${start}-${end - 1}`} : {}});
        const body = new Uint8Array(await res.arrayBuffer());
        const startOk = res.status === 200 || Number(/^bytes (\d+)-/.exec(res.headers.get('Content-Range') ?? '')?.[1]) === start;
        if ((res.status !== 200 && res.status !== 206) || !startOk || body.length !== end - start) {
            throw new Error(`read error: ${path} ${start}-${end}: status ${res.status}, ${body.length} bytes`);
        }
        return body;
    };

    return {
        folderName,
        entries,
        async readRange(path, start, end, signal) {
            if (start < 0 || end < start || end > sizeOf(path)) throw new Error(`range ${start}-${end} outside ${path}`);
            return end === start ? new Uint8Array(0) : get(path, start, end, true, signal);
        },
        async readWhole(path, maxBytes) {
            const size = sizeOf(path);
            if (size > maxBytes) throw new Error(`${path} has ${size} bytes, more than ${maxBytes}`);
            return get(path, 0, size, false);
        },
        close: () => bridge.close(token),
    };
}
