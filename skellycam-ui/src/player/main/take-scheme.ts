// The take handler in the Electron main process (specs/player.md sections 5.2 to 5.7). It serves only
// the regular files of the opened take folder from the allow-list of a token, and it opens a folder
// only inside the recordings folder or a folder that the user picked in the system dialog [Y2, L7, U1].
import {ipcMain, protocol} from 'electron';
import type {WebContents} from 'electron';
import {randomBytes} from 'node:crypto';
import {lstat, mkdir, open, readdir, readFile, realpath, stat, writeFile} from 'node:fs/promises';
import type {FileHandle} from 'node:fs/promises';
import path from 'node:path';
import {TAKE_CHANNELS} from './bridge.ts';

const SCHEME = 'skellycam-take';
const MEDIA = 'synchronized_videos';
const COMMON = {
    'Content-Type': 'application/octet-stream', 'Cache-Control': 'no-store', 'Access-Control-Allow-Origin': '*',
    'Access-Control-Expose-Headers': 'Content-Range, Content-Length, Accept-Ranges',
};

interface Entry {
    size: number;
    dev: bigint;
    ino: bigint;
}

interface Token {
    sender: number;
    folder: string;
    entries: Map<string, Entry>;
    handles: Map<string, Promise<FileHandle>>;
}

export interface TakeHandlerOptions {
    recordingsFolder: string;
    pickedFoldersFile: string;
}

export interface TakeHandler {
    /** Call it after each folder pick of the system dialog, in the main process. */
    recordPick(folder: string): Promise<void>;
    /** Test hook: make the reads of one relative path fail. */
    setReadFault(relativePath: string | null): void;
}

/** Call before `app` is ready. */
export function registerTakeScheme(): void {
    protocol.registerSchemesAsPrivileged([
        {scheme: SCHEME, privileges: {standard: true, secure: true, supportFetchAPI: true, stream: true, corsEnabled: true}},
    ]);
}

class Refused extends Error {}

const respond = (status: number, body: Uint8Array | null = null, headers: Record<string, string> = {}) =>
    new Response(body as BodyInit | null, {status, headers: {...COMMON, ...headers}});

/** Call after `app` is ready. */
export async function installTakeHandler(options: TakeHandlerOptions): Promise<TakeHandler> {
    const tokens = new Map<string, Token>();
    const watched = new Set<number>();
    let readFault: string | null = null;
    let picked: string[] = [];
    try {
        const list = JSON.parse(await readFile(options.pickedFoldersFile, 'utf8'));
        if (Array.isArray(list)) picked = list.filter(p => typeof p === 'string');
    } catch {
        // no list yet
    }

    const same = (a: string, b: string) => (process.platform === 'win32' ? a.toLowerCase() === b.toLowerCase() : a === b);
    const inside = (folder: string, root: string) => {
        const rel = path.relative(process.platform === 'win32' ? root.toLowerCase() : root, process.platform === 'win32' ? folder.toLowerCase() : folder);
        return same(folder, root) || (rel !== '' && rel !== '..' && !rel.startsWith('..' + path.sep) && !path.isAbsolute(rel));
    };
    const allowed = async (real: string) => {
        for (const root of [options.recordingsFolder, ...picked]) {
            const rootReal = await realpath(root).catch(() => null);
            if (rootReal && inside(real, rootReal)) return true;
        }
        return false;
    };

    const closeToken = (token: string) => {
        const t = tokens.get(token);
        if (!t) return;
        tokens.delete(token);
        for (const h of t.handles.values()) void h.then(fh => fh.close()).catch(() => undefined);
    };
    const closeSender = (sender: number, keepFolder: string | null = null) => {
        for (const [token, t] of tokens) if (t.sender === sender && t.folder !== keepFolder) closeToken(token);
    };
    const watch = (wc: WebContents) => {
        if (watched.has(wc.id)) return;
        watched.add(wc.id);
        const id = wc.id;
        wc.on('did-navigate', () => closeSender(id));
        wc.on('render-process-gone', () => closeSender(id));
        wc.once('destroyed', () => {
            closeSender(id);
            watched.delete(id);
        });
    };

    /** The snapshot of 5.4: the root and the media folder, regular files only, no links. */
    const snapshot = async (folder: string) => {
        const entries = new Map<string, Entry>();
        const list = async (rel: string) => {
            for (const name of await readdir(path.join(folder, rel))) {
                const relPath = rel ? `${rel}/${name}` : name;
                const st = await lstat(path.join(folder, relPath), {bigint: true});
                if (st.isFile()) entries.set(relPath, {size: Number(st.size), dev: st.dev, ino: st.ino});
                else if (!rel && name === MEDIA && st.isDirectory()) await list(MEDIA);
            }
        };
        await list('');
        return new Map([...entries].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));
    };

    ipcMain.handle(TAKE_CHANNELS[0], async (event, folderPath: unknown) => {
        const real = typeof folderPath === 'string' ? await realpath(folderPath).catch(() => null) : null;
        if (!real || !(await allowed(real))) throw new Error('folder not allowed');
        if (!(await stat(real)).isDirectory()) throw new Error('not a folder');
        const entries = await snapshot(real);
        const token = randomBytes(16).toString('hex');
        const sender = event.sender;
        watch(sender);
        // another take of the same window ends the earlier tokens of that window
        closeSender(sender.id, real);
        tokens.set(token, {sender: sender.id, folder: real, entries, handles: new Map()});
        return {token, folderName: path.basename(real), entries: [...entries].map(([p, e]) => ({path: p, size: e.size}))};
    });

    ipcMain.handle(TAKE_CHANNELS[1], (event, token: unknown) => {
        if (typeof token === 'string' && tokens.get(token)?.sender === event.sender.id) closeToken(token);
    });

    /** Open a file and check that it is the file of the snapshot. */
    const openChecked = async (t: Token, rel: string, entry: Entry) => {
        const fh = await open(path.join(t.folder, ...rel.split('/')), 'r');
        const st = await fh.stat({bigint: true});
        if (st.dev !== entry.dev || st.ino !== entry.ino) {
            await fh.close();
            throw new Refused('the file changed');
        }
        return fh;
    };

    const readBytes = async (t: Token, rel: string, entry: Entry, start: number, end: number) => {
        // camera files keep their handle; each other file opens, reads and closes (5.5)
        const keep = rel.endsWith('.mkv');
        let pending = keep ? t.handles.get(rel) : undefined;
        if (!pending) {
            pending = openChecked(t, rel, entry);
            if (keep) {
                t.handles.set(rel, pending);
                pending.catch(() => t.handles.delete(rel));
            }
        }
        const fh = await pending;
        try {
            const buf = new Uint8Array(end - start);
            for (let got = 0; got < buf.length;) {
                const {bytesRead} = await fh.read(buf, got, buf.length - got, start + got);
                if (bytesRead === 0) throw new Error('short read');
                got += bytesRead;
            }
            return buf;
        } finally {
            if (!keep) await fh.close();
        }
    };

    protocol.handle(SCHEME, async req => {
        if (req.method !== 'GET') return respond(405);
        const url = new URL(req.url);
        let rel: string;
        try {
            rel = decodeURIComponent(url.pathname.slice(1));
        } catch {
            return respond(404);
        }
        const t = tokens.get(url.hostname);
        const entry = t?.entries.get(rel);
        if (!t || !entry) return respond(404);
        const size = entry.size;
        const range = req.headers.get('Range');
        let start = 0;
        let end = size;
        if (range !== null) {
            const m = /^bytes=(\d+)-(\d+)$/.exec(range);
            if (!m || Number(m[1]) > Number(m[2]) || Number(m[1]) >= size) return respond(416, null, {'Content-Range': `bytes */${size}`});
            start = Number(m[1]);
            end = Math.min(Number(m[2]), size - 1) + 1;
        }
        try {
            if (readFault === rel) throw new Error('test read fault');
            const body = await readBytes(t, rel, entry, start, end);
            const headers: Record<string, string> = {'Content-Length': String(end - start), 'Accept-Ranges': 'bytes'};
            if (range !== null) headers['Content-Range'] = `bytes ${start}-${end - 1}/${size}`;
            return respond(range === null ? 200 : 206, body, headers);
        } catch (e) {
            return respond(e instanceof Refused || (e as NodeJS.ErrnoException).code === 'ENOENT' ? 404 : 500);
        }
    });

    return {
        async recordPick(folder: string) {
            const real = await realpath(folder);
            if (picked.some(p => same(p, real))) return;
            picked.push(real);
            await mkdir(path.dirname(options.pickedFoldersFile), {recursive: true});
            await writeFile(options.pickedFoldersFile, JSON.stringify(picked, null, 2) + '\n');
        },
        setReadFault(relativePath: string | null) {
            readFault = relativePath;
        },
    };
}
