// The Node implementation of TakeFiles for the unit tests (specs/player.md section 12.2). It takes the
// snapshot of section 5.4 at the open: the root and the media folder, regular files only.
import {lstat, mkdir, open, readdir, writeFile} from 'node:fs/promises';
import path from 'node:path';
import type {TakeFiles} from '../../files/take-files.ts';
import {patternBytes, SUITE_FILES, SUITE_FOLDER, SUITE_HIDDEN} from './take-files-checks.ts';

export interface NodeTakeFilesOptions {
    sizes?: Record<string, number>;   // smaller snapshot sizes (T-PLAY-24)
}

export async function nodeTakeFiles(folder: string, options: NodeTakeFilesOptions = {}): Promise<TakeFiles> {
    const entries: {path: string; size: number}[] = [];
    const list = async (rel: string) => {
        for (const d of await readdir(path.join(folder, rel))) {
            const relPath = rel ? `${rel}/${d}` : d;
            const st = await lstat(path.join(folder, relPath));
            if (st.isFile()) entries.push({path: relPath, size: options.sizes?.[relPath] ?? st.size});
            else if (!rel && d === 'synchronized_videos' && st.isDirectory()) await list(d);
        }
    };
    await list('');
    entries.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
    const sizes = new Map(entries.map(e => [e.path, e.size]));
    let closed = false;
    const read = async (rel: string, start: number, end: number) => {
        if (closed) throw new Error('closed');
        const size = sizes.get(rel);
        if (size === undefined) throw new Error(`not in the entries: ${rel}`);
        if (start < 0 || end < start || end > size) throw new Error(`range ${start}-${end} outside the snapshot ${size}`);
        const fh = await open(path.join(folder, ...rel.split('/')), 'r');
        try {
            const buf = new Uint8Array(end - start);
            let got = 0;
            while (got < buf.length) {
                const {bytesRead} = await fh.read(buf, got, buf.length - got, start + got);
                if (bytesRead === 0) throw new Error(`short read: ${got} of ${buf.length}`);
                got += bytesRead;
            }
            return buf;
        } finally {
            await fh.close();
        }
    };
    return {
        folderName: path.basename(folder),
        entries,
        readRange: (rel, start, end) => read(rel, start, end),
        readWhole: async (rel, maxBytes) => {
            const size = sizes.get(rel);
            if (size === undefined) throw new Error(`not in the entries: ${rel}`);
            if (size > maxBytes) throw new Error(`${rel} has ${size} bytes, more than ${maxBytes}`);
            return read(rel, 0, size);
        },
        close: async () => {
            closed = true;
        },
    };
}

/** The folder of the shared check suite, with the pattern bytes of `take-files-checks.ts`. */
export async function writeSuiteFolder(root: string): Promise<string> {
    const dir = path.join(root, SUITE_FOLDER);
    for (const f of [...SUITE_FILES, {path: SUITE_HIDDEN, size: 64, seed: 9}]) {
        const full = path.join(dir, ...f.path.split('/'));
        await mkdir(path.dirname(full), {recursive: true});
        await writeFile(full, patternBytes(f.seed, 0, f.size));
    }
    return dir;
}
