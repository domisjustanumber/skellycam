// The rules of the recently opened folders (specs/player.md 5.10; ADR-8J08, ADR-FHP6): the list, its file, and
// the check at a click. Node only, so the unit tests load it with no Electron.
import {mkdir, readFile, realpath, rename, stat, writeFile} from 'node:fs/promises';
import path from 'node:path';

export const RECENT_FILE = 'recent-take-folders.json';
const MAX = 5;
const FILE_LIMIT = 1024 * 1024;
const PATH_LIMIT = 32_767;

/** The same path: case ignored on Windows (5.3). */
export const same = (a: string, b: string) => (process.platform === 'win32' ? a.toLowerCase() === b.toLowerCase() : a === b);

/** An item that the file may hold: an absolute path that is not UNC or a device path, with no NUL. */
const valid = (p: unknown): p is string =>
    typeof p === 'string' && p !== '' && p.length <= PATH_LIMIT && !p.includes('\0') && path.isAbsolute(p) && !/^[\\/]{2}/.test(p);

/** The list after a pick or an open of `real`: at the top, once, 5 at most. A path that is not valid adds nothing. */
export function addRecent(list: readonly string[], real: string): string[] {
    if (!valid(real)) return [...list];
    return [real, ...list.filter(p => !same(p, real))].slice(0, MAX);
}

/** The list of the text of the file. Untrusted input: each wrong file is an empty list, each wrong item is left out. */
export function parseRecent(text: string): string[] {
    let data: unknown;
    try {
        data = JSON.parse(text);
    } catch {
        return [];
    }
    if (data === null || typeof data !== 'object') return [];
    const {version, folders} = data as {version?: unknown; folders?: unknown};
    if (version !== 1 || !Array.isArray(folders)) return [];
    const out: string[] = [];
    for (const p of folders) if (valid(p) && !out.some(q => same(q, p))) out.push(p);
    return out.slice(0, MAX);
}

export const recentText = (list: readonly string[]) => JSON.stringify({version: 1, folders: list}, null, 2) + '\n';

/** The list of the file; a missing, unreadable, too large or not regular file (a FIFO would block the read) gives an empty list. */
export async function readRecent(file: string): Promise<string[]> {
    try {
        const st = await stat(file);
        if (!st.isFile() || st.size > FILE_LIMIT) return [];
        return parseRecent(await readFile(file, 'utf8'));
    } catch {
        return [];
    }
}

/** The check at a click (Q965): `asked` must be an entry, and the stored path must still be the real path of a folder. */
export async function checkRecent(list: readonly string[], asked: unknown): Promise<{ok: true; folder: string} | {ok: false; reason: 'not listed' | 'gone'}> {
    const entry = typeof asked === 'string' ? list.find(p => same(p, asked)) : undefined;
    if (entry === undefined) return {ok: false, reason: 'not listed'};
    try {
        const real = await realpath(entry);
        if (same(real, entry) && (await stat(real)).isDirectory()) return {ok: true, folder: entry};
    } catch {
        // each realpath or stat error (missing, no access, busy) is gone (5.10)
    }
    return {ok: false, reason: 'gone'};
}

/** The folder that the player dialog opens at: the top entry; with an empty list, the recordings folder when it
 * is a folder, else the home folder. Never undefined: Windows would open its own last folder of the program. */
export async function dialogFolder(list: readonly string[], recordingsFolder: string, home: string): Promise<string> {
    if (list.length > 0) return list[0];
    return (await stat(recordingsFolder).then(st => st.isDirectory(), () => false)) ? recordingsFolder : home;
}

/** The list of the main process and its file (5.10). The writes run one after the other; a failed write keeps
 * the list in memory. */
export async function recentStore(file: string) {
    let recent = await readRecent(file);
    let saving = Promise.resolve();
    const set = (list: string[]) => {
        recent = list;
        const text = recentText(list);
        saving = saving.then(async () => {
            await mkdir(path.dirname(file), {recursive: true});
            await writeFile(`${file}.tmp`, text);
            await rename(`${file}.tmp`, file);
        }).catch(() => console.error('the recently opened folders were not saved'));
        return saving;
    };
    return {
        list: (): readonly string[] => recent,
        add: (real: string) => set(addRecent(recent, real)),
        clear: () => set([]),
        /** A click: `onOpen` gets the stored path, the entry moves to the top. Fails with "folder not allowed" for a
         * path that is no entry, also one that a clear removed during the check, and with "folder gone". */
        async open(asked: unknown, onOpen: (folder: string) => void): Promise<string> {
            const check = await checkRecent(recent, asked);
            if (!check.ok && check.reason === 'gone') {
                await set(recent.filter(p => !same(p, asked as string)));
                throw new Error('folder gone');
            }
            if (!check.ok || !recent.some(p => same(p, check.folder))) throw new Error('folder not allowed');
            onOpen(check.folder);
            await set(addRecent(recent, check.folder));
            return check.folder;
        },
    };
}
