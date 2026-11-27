// The take handler in the Electron main process (specs/player.md sections 5.2 to 5.7). It serves only
// the regular files of the opened take folder from the allow-list of a token, and it opens a folder
// only inside the recordings folder or a folder that the user picked in the system dialog [Y2, L7, U1].
import {app, ipcMain, protocol} from 'electron';
import type {WebContents} from 'electron';
import {randomBytes} from 'node:crypto';
import {lstat, mkdir, open, readdir, realpath, rename, stat, writeFile} from 'node:fs/promises';
import type {FileHandle} from 'node:fs/promises';
import path from 'node:path';
import {TAKE_CHANNELS} from './bridge.ts';
import {RECENT_FILE, addRecent, checkRecent, readRecent, recentText, same} from './recent-folders.ts';

const SCHEME = 'skellycam-take';
const MEDIA = 'synchronized_videos';
const PIECE = 1024 * 1024;   // a response is read from the file in pieces of at most 1 MiB
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
}

export interface TakeHandler {
    /** Call it after each folder pick of the system dialog, in the main process; `recent` for the dialog of the player (5.10). */
    recordPick(folder: string, options?: {recent?: boolean}): Promise<void>;
    /** The recently opened folders, most recent first; the dialog of the player opens at the first (5.10). */
    recent(): readonly string[];
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

const respond = (status: number, body: BodyInit | null = null, headers: Record<string, string> = {}) =>
    new Response(body, {status, headers: {...COMMON, ...headers}});

/** Call after `app` is ready. */
export async function installTakeHandler(options: TakeHandlerOptions): Promise<TakeHandler> {
    const tokens = new Map<string, Token>();
    const watched = new Set<number>();
    const navigations = new Map<number, number>();   // the count of navigations of each window
    let readFault: string | null = null;
    // the real paths of the dialog picks, for the run of the app only: no file of this list (5.3, ADR-70J6)
    const picked: string[] = [];
    const pick = (real: string) => {
        if (!picked.some(p => same(p, real))) picked.push(real);
    };
    // the recently opened folders of the player dialog, the one saved list; an entry is no pick until a click (5.10)
    const recentFile = path.join(app.getPath('userData'), RECENT_FILE);
    let recent = await readRecent(recentFile);
    let saving = Promise.resolve();
    const setRecent = (list: string[]) => {
        recent = list;
        const text = recentText(list);
        saving = saving.then(async () => {
            await mkdir(path.dirname(recentFile), {recursive: true});
            await writeFile(`${recentFile}.tmp`, text);
            await rename(`${recentFile}.tmp`, recentFile);
        }).catch(() => console.error('the recently opened folders were not saved'));
        return saving;
    };

    const inside = (folder: string, root: string) => {
        const rel = path.relative(process.platform === 'win32' ? root.toLowerCase() : root, process.platform === 'win32' ? folder.toLowerCase() : folder);
        return same(folder, root) || (rel !== '' && rel !== '..' && !rel.startsWith('..' + path.sep) && !path.isAbsolute(rel));
    };
    // the recordings folder is resolved at each open; a pick keeps the real path of its pick time, so a link put in
    // its place later is not followed (5.3)
    const allowed = async (real: string) => {
        const recordings = await realpath(options.recordingsFolder).catch(() => null);
        return [...(recordings ? [recordings] : []), ...picked].some(root => inside(real, root));
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
        wc.on('did-navigate', () => {
            navigations.set(id, (navigations.get(id) ?? 0) + 1);
            closeSender(id);
        });
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
                // a hard link can name a file outside the take: only a file with one link is served
                if (st.isFile() && st.nlink === 1n) entries.set(relPath, {size: Number(st.size), dev: st.dev, ino: st.ino});
                else if (!rel && name === MEDIA && st.isDirectory()) await list(MEDIA);
            }
        };
        await list('');
        return new Map([...entries].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));
    };

    ipcMain.handle(TAKE_CHANNELS[0], async (event, folderPath: unknown) => {
        // no file system call for a relative, UNC or device path: a UNC path opens a network connection
        if (typeof folderPath !== 'string' || !path.isAbsolute(folderPath) || /^[\\/]{2}/.test(folderPath)) throw new Error('folder not allowed');
        const sender = event.sender;
        watch(sender);
        const navigation = navigations.get(sender.id);
        const real = await realpath(folderPath).catch(() => null);
        if (!real || !(await allowed(real))) throw new Error('folder not allowed');
        if (!(await stat(real)).isDirectory()) throw new Error('not a folder');
        const entries = await snapshot(real);
        if (sender.isDestroyed() || navigations.get(sender.id) !== navigation) throw new Error('the window changed during the open');
        const token = randomBytes(16).toString('hex');
        // another take of the same window ends the earlier tokens of that window
        closeSender(sender.id, real);
        tokens.set(token, {sender: sender.id, folder: real, entries, handles: new Map()});
        return {token, folderName: path.basename(real), entries: [...entries].map(([p, e]) => ({path: p, size: e.size}))};
    });

    ipcMain.handle(TAKE_CHANNELS[1], (event, token: unknown) => {
        if (typeof token === 'string' && tokens.get(token)?.sender === event.sender.id) closeToken(token);
    });

    // 5.10: the page reads the list, asks to open an entry, or clears it; no call adds a path
    ipcMain.handle(TAKE_CHANNELS[2], () => [...recent]);
    ipcMain.handle(TAKE_CHANNELS[3], async (_event, folder: unknown) => {
        const check = await checkRecent(recent, folder);
        if (!check.ok && check.reason === 'not listed') throw new Error('folder not allowed');
        if (!check.ok) {
            await setRecent(recent.filter(p => !same(p, folder as string)));
            throw new Error('folder gone');
        }
        // the stored path, not a new realpath: a link put in its place after the check is not followed
        pick(check.folder);
        await setRecent(addRecent(recent, check.folder));
        return check.folder;
    });
    ipcMain.handle(TAKE_CHANNELS[4], async () => {
        await setRecent([]);
    });

    /** Open a file and check that it is the file of the snapshot. */
    const openChecked = async (t: Token, rel: string, entry: Entry) => {
        const fh = await open(path.join(t.folder, ...rel.split('/')), 'r');
        const st = await fh.stat({bigint: true});
        if (st.dev !== entry.dev || st.ino !== entry.ino || st.nlink !== 1n) {
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
        // the body is read in pieces, so a large request does not hold the file in one buffer
        let pos = start;
        const done = async () => {
            if (!keep) await fh.close().catch(() => undefined);
        };
        return new ReadableStream<Uint8Array>({
            async pull(c) {
                try {
                    if (pos >= end) {
                        c.close();
                        return done();
                    }
                    const buf = new Uint8Array(Math.min(PIECE, end - pos));
                    const {bytesRead} = await fh.read(buf, 0, buf.length, pos);
                    if (bytesRead === 0) throw new Error('short read');
                    pos += bytesRead;
                    c.enqueue(buf.subarray(0, bytesRead));
                } catch (e) {
                    c.error(e);
                    await done();
                }
            },
            cancel: done,
        });
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
        async recordPick(folder: string, options: {recent?: boolean} = {}) {
            const real = await realpath(folder);
            pick(real);
            if (options.recent) await setRecent(addRecent(recent, real));
        },
        recent: () => recent,
        setReadFault(relativePath: string | null) {
            readFault = relativePath;
        },
    };
}
