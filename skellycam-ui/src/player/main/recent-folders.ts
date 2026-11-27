// The rules of the recently opened folders (specs/player.md 5.10; ADR-8J08, ADR-FHP6): the list, its file, and
// the check at a click. Node only, so the unit tests load it with no Electron.
import {readFile, realpath, stat} from 'node:fs/promises';
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

/** The list of the file; a missing, unreadable or too large file gives an empty list. */
export async function readRecent(file: string): Promise<string[]> {
    try {
        if ((await stat(file)).size > FILE_LIMIT) return [];
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
        // missing or unreadable: gone
    }
    return {ok: false, reason: 'gone'};
}
