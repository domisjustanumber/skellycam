// Electron tests of the take handler with real files: T-PLAY-55 to T-PLAY-64, T-PLAY-85, T-PLAY-86 and T-PLAY-89
// (specs/player.md section 5).
import {expect} from '@playwright/test';
import type {Page} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {appendFileSync, existsSync, mkdirSync, openSync, closeSync, readdirSync, readFileSync, realpathSync, renameSync, rmdirSync, rmSync, statSync, symlinkSync, writeFileSync, writeSync, ftruncateSync, unlinkSync} from 'node:fs';
import path from 'node:path';
import {writeSuiteFolder} from '../fixtures/node-take-files.ts';
import {patternBytes} from '../fixtures/take-files-checks.ts';
import {planOf} from '../fixtures/takes.ts';
import {harnessTest} from './harness.ts';
import type {Harness} from './harness.ts';

const test = harnessTest('harness');
const KiB = 1024;
const MiB = 1024 * KiB;
const GiB = 1024 * MiB;

interface Opened {
    token: string;
    folderName: string;
    entries: {path: string; size: number}[];
}

interface Fetched {
    status: number;
    headers: Record<string, string>;
    base64: string;
    error?: string;
}

const bridgeOpen = (page: Page, folder: string): Promise<Opened> =>
    page.evaluate(f => (window as never as {skellycamTake: {open(f: string): Promise<Opened>}}).skellycamTake.open(f), folder);

const bridgeClose = (page: Page, token: string): Promise<void> =>
    page.evaluate(t => (window as never as {skellycamTake: {close(t: string): Promise<void>}}).skellycamTake.close(t), token);

const urlOf = (token: string, rel: string) => `skellycam-take://${token}/${rel.split('/').map(encodeURIComponent).join('/')}`;

function fetchRaw(page: Page, url: string, init: {method?: string; range?: string} = {}): Promise<Fetched> {
    return page.evaluate(async ([u, method, range]) => {
        try {
            const res = await fetch(u as string, {method: (method as string) ?? 'GET', cache: 'no-store', headers: range ? {Range: range as string} : {}});
            const bytes = new Uint8Array(await res.arrayBuffer());
            return {status: res.status, headers: Object.fromEntries(res.headers.entries()), base64: btoa(Array.from(bytes, b => String.fromCharCode(b)).join(''))};
        } catch (e) {
            return {status: 0, headers: {}, base64: '', error: String(e)};
        }
    }, [url, init.method, init.range] as const);
}

const bytesOf = (f: Fetched) => new Uint8Array(Buffer.from(f.base64, 'base64'));

function patternFile(file: string, size: number, seed: number) {
    mkdirSync(path.dirname(file), {recursive: true});
    writeFileSync(file, patternBytes(seed, 0, size));
}

/** A dialog pick in the main process; `{recent: true}` is a pick of the folder dialog of the player (5.10). */
const recordPick = (h: Harness, folder: string, options?: {recent: boolean}) =>
    h.app.evaluate((_e, [f, o]) => (globalThis as never as {__harness: {recordPick(f: string, o?: {recent: boolean}): Promise<void>}}).__harness.recordPick(f, o),
        [folder, options] as const);

type RecentBridge = {recent(): Promise<string[]>; openRecent(f: string): Promise<string>; clearRecent(): Promise<void>};
const recentOf = (page: Page): Promise<string[]> =>
    page.evaluate(() => (window as never as {skellycamTake: RecentBridge}).skellycamTake.recent());
const openRecent = (page: Page, folder: string): Promise<string> =>
    page.evaluate(f => (window as never as {skellycamTake: RecentBridge}).skellycamTake.openRecent(f), folder);
const clearRecent = (page: Page): Promise<void> =>
    page.evaluate(() => (window as never as {skellycamTake: RecentBridge}).skellycamTake.clearRecent());

/** Each file below the test folder, with its size and modification time, outside the userData folder of the
 * harness, where Chromium writes its own files: a test of "no file is written" (5.3). */
function filesBelow(h: Harness): Record<string, string> {
    const out: Record<string, string> = {};
    for (const rel of readdirSync(h.root, {recursive: true}) as string[]) {
        const full = path.join(h.root, rel);
        if (full === h.userData || full.startsWith(h.userData + path.sep)) continue;
        const st = statSync(full, {throwIfNoEntry: false});
        if (st?.isFile()) out[rel] = `${st.size}:${st.mtimeMs}`;
    }
    return out;
}

/** The files below the test folder, the userData folder included, that hold a text in UTF-8 or UTF-16: the
 * path of a pick written anywhere, in any form that keeps the folder name (5.3). */
function filesHolding(h: Harness, text: string): string[] {
    const forms = [Buffer.from(text, 'utf8'), Buffer.from(text, 'utf16le')];
    const out: string[] = [];
    for (const rel of readdirSync(h.root, {recursive: true}) as string[]) {
        const full = path.join(h.root, rel);
        try {
            if (!statSync(full).isFile()) continue;
            const bytes = readFileSync(full);
            if (forms.some(f => bytes.includes(f))) out.push(rel);
        } catch {
            // a file that Chromium holds locked
        }
    }
    return out;
}

function assertCommonHeaders(f: Fetched) {
    expect(f.headers['content-type']).toBe('application/octet-stream');
    expect(f.headers['cache-control']).toBe('no-store');
    expect(f.headers['access-control-allow-origin']).toBe('*');
    expect(f.headers['access-control-expose-headers']?.replace(/\s/g, '')).toBe('Content-Range,Content-Length,Accept-Ranges');
}

test('T-PLAY-55 the range matrix of 5.6, with a snapshot of 512 KiB', async ({harness: h}) => {
    await h.requireProduct();
    const folder = path.join(h.recordings, 'range');
    const rel = 'synchronized_videos/r.mkv';
    const file = path.join(folder, ...rel.split('/'));
    patternFile(file, 512 * KiB, 4);
    const {token} = await bridgeOpen(h.page, folder);
    appendFileSync(file, new Uint8Array(512 * KiB).fill(0xee));
    const url = urlOf(token, rel);
    const snap = 512 * KiB;
    const want = patternBytes(4, 0, snap);

    const whole = await fetchRaw(h.page, url);
    expect(whole.status).toBe(200);
    expect(whole.headers['content-length']).toBe(String(snap));
    expect(whole.headers['accept-ranges']).toBe('bytes');
    expect(Buffer.compare(bytesOf(whole), want)).toBe(0);
    assertCommonHeaders(whole);

    const inside = await fetchRaw(h.page, url, {range: 'bytes=100-199'});
    expect(inside.status).toBe(206);
    expect(inside.headers['content-range']).toBe(`bytes 100-199/${snap}`);
    expect(inside.headers['content-length']).toBe('100');
    expect(Buffer.compare(bytesOf(inside), want.subarray(100, 200))).toBe(0);
    assertCommonHeaders(inside);

    const across = await fetchRaw(h.page, url, {range: `bytes=${snap - 100}-${snap + 1000}`});
    expect(across.status).toBe(206);
    expect(across.headers['content-range']).toBe(`bytes ${snap - 100}-${snap - 1}/${snap}`);
    expect(Buffer.compare(bytesOf(across), want.subarray(snap - 100))).toBe(0);

    for (const range of [`bytes=${snap}-${snap + 10}`, 'bytes=-500', 'bytes=100-', 'bytes=0-1,5-6', 'bytes=abc', 'bytes=200-100']) {
        const r = await fetchRaw(h.page, url, {range});
        expect(r.status, range).toBe(416);
        expect(r.headers['content-range'], range).toBe(`bytes */${snap}`);
        assertCommonHeaders(r);
    }
    const post = await fetchRaw(h.page, url, {method: 'POST'});
    expect(post.status).toBe(405);
});

test('T-PLAY-56 640 reads of 150 kB at concurrency 16', async ({harness: h}) => {
    await h.requireProduct();
    const folder = path.join(h.recordings, 'many');
    patternFile(path.join(folder, 'synchronized_videos', 'm.mkv'), 10 * MiB, 5);
    const {token} = await bridgeOpen(h.page, folder);
    const failed = await h.page.evaluate(async url => {
        let fails = 0;
        let next = 0;
        const size = 150_000;
        const worker = async () => {
            while (next < 640) {
                const i = next++;
                const start = (i * 7919 * 13) % (10 * 1024 * 1024 - size);
                try {
                    const res = await fetch(url, {cache: 'no-store', headers: {Range: `bytes=${start}-${start + size - 1}`}});
                    const body = await res.arrayBuffer();
                    if (res.status !== 206 || body.byteLength !== size) fails++;
                } catch {
                    fails++;
                }
            }
        };
        await Promise.all(Array.from({length: 16}, worker));
        return fails;
    }, urlOf(token, 'synchronized_videos/m.mkv'));
    expect(failed).toBe(0);
});

test('T-PLAY-57 no request leaves the folder', async ({harness: h}) => {
    await h.requireProduct();
    const folder = path.join(h.recordings, 'escape');
    patternFile(path.join(folder, 'synchronized_videos', 'a.mkv'), 4 * KiB, 6);
    patternFile(path.join(folder, 'annotated_videos', 'b.mp4'), 4 * KiB, 7);
    const outside = path.join(h.root, 'outside');
    const secret = new TextEncoder().encode('SECRET-OUTSIDE-THE-TAKE-'.repeat(20));
    mkdirSync(outside, {recursive: true});
    writeFileSync(path.join(outside, 'secret.bin'), secret);
    writeFileSync(path.join(h.recordings, 'secret.bin'), secret);
    if (process.platform === 'win32') symlinkSync(outside, path.join(folder, 'synchronized_videos', 'link'), 'junction');
    else symlinkSync(path.join(outside, 'secret.bin'), path.join(folder, 'synchronized_videos', 'link.mkv'));
    const opened = await bridgeOpen(h.page, folder);
    expect(opened.token).toMatch(/^[0-9a-f]{32}$/);
    expect(opened.entries.map(e => e.path).sort()).toEqual(['synchronized_videos/a.mkv']);
    const base = `skellycam-take://${opened.token}`;
    const attempts = [
        `${base}/..%2Fsecret.bin`, `${base}/../secret.bin`, `${base}/%2e%2e/%2e%2e/outside/secret.bin`,
        `${base}/synchronized_videos\\..\\..\\secret.bin`, `${base}/${encodeURIComponent(path.join(outside, 'secret.bin'))}`,
        `${base}/annotated_videos/b.mp4`, `${base}/synchronized_videos/nope.mkv`, `${base}/synchronized_videos/link/secret.bin`,
        `${base}/synchronized_videos/link.mkv`, `skellycam-take://${opened.token.toUpperCase()}/../secret.bin`,
    ];
    const allowed = patternBytes(6, 0, 4 * KiB);
    const check = async (url: string) => {
        const r = await fetchRaw(h.page, url);
        const body = bytesOf(r);
        expect(Buffer.from(body).includes(Buffer.from('SECRET-OUTSIDE')), url).toBe(false);
        if (r.status !== 404 && r.status !== 0) expect(Buffer.compare(body, allowed), `${url} reads an allowed file`).toBe(0);
    };
    for (const url of attempts) await check(url);
    await bridgeClose(h.page, opened.token);
    const closed = await fetchRaw(h.page, urlOf(opened.token, 'synchronized_videos/a.mkv'));
    expect(closed.status).toBe(404);
});

test('T-PLAY-58 changes during an open take', async ({harness: h}) => {
    await h.requireProduct();
    const built = h.build('normal');
    const files = await h.page.evaluate(f => window.harness.openFiles(f), built.dir);
    const [c0, c1, c2] = built.cameras;
    const first = await h.page.evaluate(([id, p]) => window.harness.readRange(id as number, p as string, 0, 4096), [files.id, c0.mkv] as const);
    expect(first.ok).toBe(true);
    // append 1 MiB: reads within the snapshot are unchanged
    appendFileSync(path.join(built.dir, c2.mkv), new Uint8Array(MiB).fill(0xee));
    const tail = await h.page.evaluate(([id, p, a, b]) => window.harness.readRange(id as number, p as string, a as number, b as number), [files.id, c2.mkv, c2.mkvSize - 100, c2.mkvSize] as const);
    expect(tail.ok).toBe(true);
    // replace the manifest by a rename, as os.replace does, while a player has the take open
    await h.page.evaluate(f => window.harness.openPlayer(f), built.dir);
    const manifest = path.join(built.dir, 'recording_manifest.json');
    writeFileSync(`${manifest}.tmp`, readFileSync(manifest));
    expect(() => renameSync(`${manifest}.tmp`, manifest)).not.toThrow();
    // delete a camera file after its first read: it stays readable
    rmSync(path.join(built.dir, c0.mkv));
    const after = await h.page.evaluate(([id, p]) => window.harness.readRange(id as number, p as string, 0, 4096), [files.id, c0.mkv] as const);
    expect(after).toEqual(first);
    // delete another camera file before its first read (in this TakeFiles): a read error
    rmSync(path.join(built.dir, c1.mkv));
    const gone = await h.page.evaluate(([id, p]) => window.harness.readRange(id as number, p as string, 0, 4096), [files.id, c1.mkv] as const);
    expect(gone.ok).toBe(false);
    await h.page.evaluate(id => window.harness.closeFiles(id), files.id);
    await h.page.evaluate(() => window.harness.closePlayer());
});

test('T-PLAY-59 the page client accepts only a 206 with the asked start or a 200 of the exact length', async ({harness: h}) => {
    await h.requireProduct();
    const folder = await writeSuiteFolder(h.recordings);
    const want = Buffer.from(patternBytes(2, 1000, 2000)).toString('base64');
    for (const [mode, ok] of [['ok-exact', true], ['ok-whole', false], ['bad-start', false]] as const) {
        await h.app.evaluate((_e, m) => (globalThis as never as {__harness: {installVariant(m: string): void}}).__harness.installVariant(m), mode);
        // Electron 45.3.4 keeps the scheme handler that a page loaded with: reload to get the variant
        await h.page.reload();
        await h.page.waitForFunction(() => 'harness' in window);
        const files = await h.page.evaluate(f => window.harness.openFiles(f), folder);
        const r = await h.page.evaluate(id => window.harness.readRange(id, 'synchronized_videos/a.mkv', 1000, 2000), files.id);
        expect(r.ok, mode).toBe(ok);
        if (r.ok) expect(r.base64).toBe(want);
        await h.page.evaluate(id => window.harness.closeFiles(id), files.id);
    }
});

test('T-PLAY-60 a sparse file of 5 GiB: ranges past 4 GiB', async ({harness: h}) => {
    await h.requireProduct();
    const folder = path.join(h.recordings, 'sparse');
    const file = path.join(folder, 'synchronized_videos', 'big.mkv');
    mkdirSync(path.dirname(file), {recursive: true});
    writeFileSync(file, new Uint8Array(0));
    if (process.platform === 'win32') execFileSync('fsutil', ['sparse', 'setflag', file]);
    const offsets = [4 * GiB + 1000, 4.5 * GiB, 5 * GiB - 4096];
    const fd = openSync(file, 'r+');
    try {
        ftruncateSync(fd, 5 * GiB);
        offsets.forEach((o, i) => writeSync(fd, patternBytes(10 + i, 0, 4096), 0, 4096, o));
    } finally {
        closeSync(fd);
    }
    const files = await h.page.evaluate(f => window.harness.openFiles(f), folder);
    for (const [i, o] of offsets.entries()) {
        const r = await h.page.evaluate(([id, a]) => window.harness.readRange(id as number, 'synchronized_videos/big.mkv', a as number, (a as number) + 4096), [files.id, o] as const);
        expect(r.ok, `offset ${o}`).toBe(true);
        if (r.ok) expect(r.base64).toBe(Buffer.from(patternBytes(10 + i, 0, 4096)).toString('base64'));
    }
    await h.page.evaluate(id => window.harness.closeFiles(id), files.id);
});

test('T-PLAY-61 the player changes no file', async ({harness: h}) => {
    await h.requireProduct();
    const built = h.build('normal');
    const snapshot = () => readdirSync(built.dir, {recursive: true}).map(String).sort().map(f => {
        const full = path.join(built.dir, f);
        const s = statSync(full);
        return s.isFile() ? `${f}:${s.mtimeMs}:${createHash('sha256').update(readFileSync(full)).digest('hex')}` : f;
    });
    const before = snapshot();
    await h.page.evaluate(f => window.harness.openPlayer(f), built.dir);
    await h.page.evaluate(() => window.harness.command('setSpeed', 8));
    await h.page.evaluate(() => window.harness.command('play'));
    await expect.poll(async () => (await h.page.evaluate(() => window.harness.state())).playing, {timeout: 30_000}).toBe(false);
    for (let i = 0; i < 50; i++) await h.page.evaluate(k => window.harness.command('seekFrame', k), (i * 37) % 120);
    await h.page.evaluate(() => window.harness.closePlayer());
    expect(snapshot()).toEqual(before);
});

test('T-PLAY-62 which folders open: recordings folder, dialog picks, links', async ({harness: h}) => {
    await h.requireProduct();
    const outside = path.join(h.root, 'outside_take');
    patternFile(path.join(outside, 'synchronized_videos', 'o.mkv'), 4 * KiB, 8);
    // nothing on disk changes from here, across the page calls, the pick and the restart (5.3, ADR-70J6)
    const filesBefore = filesBelow(h);
    await expect(bridgeOpen(h.page, outside)).rejects.toThrow(/folder not allowed/);
    // the page calls each bridge function and each IPC channel of the module with that folder
    await h.page.evaluate(async f => {
        const bridge = (window as never as {skellycamTake: Record<string, (...a: unknown[]) => unknown>}).skellycamTake;
        for (const fn of Object.values(bridge)) {
            try {
                await fn(f);
            } catch {
                // refused calls are expected
            }
        }
    }, outside);
    const channels: string[] = await h.app.evaluate(() => (globalThis as never as {__harness: {channels(): Promise<string[]>}}).__harness.channels());
    expect(channels.length).toBeGreaterThan(0);
    for (const ch of channels) {
        await h.page.evaluate(async ([c, f]) => {
            try {
                await window.harnessIpc.invoke(c as string, f);
            } catch {
                // refused
            }
            window.harnessIpc.send(c as string, f);
        }, [ch, outside] as const);
    }
    await expect(bridgeOpen(h.page, outside)).rejects.toThrow(/folder not allowed/);
    expect(await recentOf(h.page), 'the page calls add no entry to the recently opened list').toEqual([]);
    // a pick of the player dialog allows it for the run of the app; after a restart only a click opens it (5.10)
    await recordPick(h, outside, {recent: true});
    expect((await bridgeOpen(h.page, outside)).token).toMatch(/^[0-9a-f]{32}$/);
    await h.relaunch();
    await expect(bridgeOpen(h.page, outside), 'a pick ends with the run of the app').rejects.toThrow(/folder not allowed/);
    expect(await recentOf(h.page), 'the entry stays in the list').toEqual([realpathSync(outside)]);
    expect(filesBelow(h), 'no file is added or changed outside userData').toEqual(filesBefore);
    expect(filesHolding(h, 'outside_take'), 'only the recently opened list holds the path of the pick')
        .toEqual([path.relative(h.root, path.join(h.userData, 'recent-take-folders.json'))]);
    expect((readdirSync(h.root, {recursive: true}) as string[]).filter(f => path.basename(f) === 'picked-take-folders.json'),
        'no picked-take-folders.json').toEqual([]);
    // inside the recordings folder
    const inside = path.join(h.recordings, 'inside');
    patternFile(path.join(inside, 'synchronized_videos', 'i.mkv'), 4 * KiB, 9);
    expect((await bridgeOpen(h.page, inside)).token).toMatch(/^[0-9a-f]{32}$/);
    // a link inside the recordings folder to a folder outside
    const other = path.join(h.root, 'other_outside');
    patternFile(path.join(other, 'synchronized_videos', 'x.mkv'), 4 * KiB, 9);
    const link = path.join(h.recordings, 'link_to_outside');
    symlinkSync(other, link, process.platform === 'win32' ? 'junction' : 'dir');
    await expect(bridgeOpen(h.page, link)).rejects.toThrow(/folder not allowed/);
});

test('T-PLAY-85 a pick lasts for the run: reloads, windows, subfolders and links', async ({harness: h}) => {
    await h.requireProduct();
    const picked = path.join(h.root, 'picked_take');
    patternFile(path.join(picked, 'synchronized_videos', 'p.mkv'), 4 * KiB, 10);
    const link = path.join(h.root, 'link_to_picked');
    symlinkSync(picked, link, process.platform === 'win32' ? 'junction' : 'dir');
    const filesBefore = filesBelow(h);
    await recordPick(h, picked);
    const token = /^[0-9a-f]{32}$/;
    expect((await bridgeOpen(h.page, picked)).token).toMatch(token);
    expect((await bridgeOpen(h.page, path.join(picked, 'synchronized_videos'))).token, 'a folder below the pick').toMatch(token);
    await h.page.reload();
    await h.page.waitForFunction(() => 'harness' in window);
    expect((await bridgeOpen(h.page, picked)).token, 'after a reload').toMatch(token);
    const windowsBefore = h.app.windows().length;
    await h.app.evaluate(() => (globalThis as never as {__harness: {openWindow(): number}}).__harness.openWindow());
    await expect.poll(() => h.app.windows().length).toBe(windowsBefore + 1);
    const second = h.app.windows().at(-1)!;
    await second.waitForFunction(() => 'harness' in window);
    expect((await bridgeOpen(second, picked)).token, 'in a second window').toMatch(token);
    expect((await bridgeOpen(h.page, link)).token, 'a link outside to the picked folder: its real path is inside').toMatch(token);
    expect(filesBelow(h), 'the pick writes no file').toEqual(filesBefore);
    expect(filesHolding(h, 'picked_take'), 'no file holds the path of the pick, also in userData').toEqual([]);
});

test('T-PLAY-86 a pick keeps its real path: a link put in its place later is not followed', async ({harness: h}) => {
    await h.requireProduct();
    const picked = path.join(h.root, 'picked_swap');
    const target = path.join(h.root, 'swap_target');
    patternFile(path.join(picked, 'synchronized_videos', 'p.mkv'), 4 * KiB, 11);
    patternFile(path.join(target, 'synchronized_videos', 's.mkv'), 4 * KiB, 12);
    const linkKind = process.platform === 'win32' ? 'junction' : 'dir';
    await recordPick(h, picked);
    expect((await bridgeOpen(h.page, picked)).token).toMatch(/^[0-9a-f]{32}$/);
    patternFile(path.join(`${picked}-other`, 'synchronized_videos', 'o.mkv'), 4 * KiB, 13);
    await expect(bridgeOpen(h.page, `${picked}-other`), 'a sibling whose name starts with the pick').rejects.toThrow(/folder not allowed/);
    // the picked folder is replaced by a link to a folder outside every allowed folder
    rmSync(picked, {recursive: true, force: true});
    symlinkSync(target, picked, linkKind);
    await expect(bridgeOpen(h.page, picked), 'the pick does not follow the new link').rejects.toThrow(/folder not allowed/);
    await expect(bridgeOpen(h.page, target)).rejects.toThrow(/folder not allowed/);
    await expect(bridgeOpen(h.page, path.join(target, 'synchronized_videos'))).rejects.toThrow(/folder not allowed/);
    // a real folder again, with a link inside it to the outside folder: the real path of the request rules
    if (process.platform === 'win32') rmdirSync(picked);
    else unlinkSync(picked);
    mkdirSync(picked);
    symlinkSync(target, path.join(picked, 'inner_link'), linkKind);
    await expect(bridgeOpen(h.page, path.join(picked, 'inner_link'))).rejects.toThrow(/folder not allowed/);
    expect(existsSync(path.join(target, 'synchronized_videos', 's.mkv')), 'the outside folder is untouched').toBe(true);
});

test('T-PLAY-89 recently opened folders across a restart: the click, its check, clear, the file', async ({harness: h}) => {
    await h.requireProduct();
    const token = /^[0-9a-f]{32}$/;
    const linkKind = process.platform === 'win32' ? 'junction' : 'dir';
    const [a, b, s] = ['recent_a', 'recent_b', 'recent_target'].map(n => path.join(h.root, n));
    [a, b, s].forEach((f, i) => patternFile(path.join(f, 'synchronized_videos', 'c.mkv'), 4 * KiB, 20 + i));
    const [ra, rb, rs] = [a, b, s].map(f => realpathSync(f));
    const file = path.join(h.userData, 'recent-take-folders.json');
    const onDisk = () => JSON.parse(readFileSync(file, 'utf8'));
    await recordPick(h, a, {recent: true});
    await recordPick(h, b, {recent: true});
    expect(await recentOf(h.page)).toEqual([rb, ra]);
    expect(onDisk()).toEqual({version: 1, folders: [rb, ra]});
    await h.relaunch();
    await expect(bridgeOpen(h.page, a), 'an entry is no pick after a restart').rejects.toThrow(/folder not allowed/);
    const before = readFileSync(file);
    await expect(openRecent(h.page, path.join(h.root, 'not_listed')), 'a path that is no entry').rejects.toThrow(/folder not allowed/);
    await expect(openRecent(h.page, s), 'a real folder that is no entry').rejects.toThrow(/folder not allowed/);
    expect(await recentOf(h.page), 'nothing changes').toEqual([rb, ra]);
    expect(readFileSync(file)).toEqual(before);
    expect(await openRecent(h.page, ra), 'the click returns the stored path').toBe(ra);
    expect((await bridgeOpen(h.page, a)).token, 'readable after the click').toMatch(token);
    expect(await recentOf(h.page), 'the click moves the entry to the top').toEqual([ra, rb]);
    expect(onDisk().folders).toEqual([ra, rb]);
    // B is replaced by a link to S: the check at the click fails, and the entry leaves the list
    rmSync(b, {recursive: true, force: true});
    symlinkSync(s, b, linkKind);
    await expect(openRecent(h.page, rb)).rejects.toThrow(/folder gone/);
    expect(await recentOf(h.page)).toEqual([ra]);
    expect(onDisk().folders).toEqual([ra]);
    await expect(bridgeOpen(h.page, b)).rejects.toThrow(/folder not allowed/);
    await expect(bridgeOpen(h.page, s)).rejects.toThrow(/folder not allowed/);
    // A is deleted
    rmSync(a, {recursive: true, force: true});
    await expect(openRecent(h.page, ra)).rejects.toThrow(/folder gone/);
    expect(await recentOf(h.page)).toEqual([]);
    // clear
    await recordPick(h, s, {recent: true});
    expect(await recentOf(h.page)).toEqual([rs]);
    await clearRecent(h.page);
    expect(await recentOf(h.page)).toEqual([]);
    expect(onDisk()).toEqual({version: 1, folders: []});
    expect((await bridgeOpen(h.page, s)).token, 'clear ends no pick of the run').toMatch(token);
    // a hand-edited list file and an old picked-take-folders.json, before a restart
    const old = path.join(h.root, 'old_pick');
    patternFile(path.join(old, 'synchronized_videos', 'o.mkv'), 4 * KiB, 25);
    const oldFile = path.join(h.userData, 'picked-take-folders.json');
    writeFileSync(oldFile, JSON.stringify([realpathSync(old)]));
    const oldBytes = readFileSync(oldFile);
    const hand = (n: number) => path.join(h.root, `hand_${n}`);
    writeFileSync(file, JSON.stringify({version: 1, folders: [3, 'relative/x', '\\\\host\\share\\x', hand(1), hand(2), hand(1), hand(3), hand(4), hand(5), hand(6)]}));
    await h.relaunch();
    expect(await recentOf(h.page), 'the first 5 valid items').toEqual([1, 2, 3, 4, 5].map(hand));
    await expect(bridgeOpen(h.page, old), 'the old file is not read').rejects.toThrow(/folder not allowed/);
    expect(readFileSync(oldFile), 'the old file is not changed or deleted').toEqual(oldBytes);
});

test('T-PLAY-63 tokens end with their window', async ({harness: h}) => {
    await h.requireProduct();
    const takeA = h.build('normal');
    const takeB1 = h.build({...planOf('normal'), name: 'normal_b1'});
    const takeB2 = h.build({...planOf('normal'), name: 'normal_b2'});
    const rel = takeA.cameras[0].mkv;
    const pageA = h.page;
    const a = await bridgeOpen(pageA, takeA.dir);
    const windowsBefore = h.app.windows().length;
    await h.app.evaluate(() => (globalThis as never as {__harness: {openWindow(): number}}).__harness.openWindow());
    await expect.poll(() => h.app.windows().length).toBe(windowsBefore + 1);
    const pageB = h.app.windows().at(-1)!;
    await pageB.waitForFunction(() => 'harness' in window);
    await pageA.reload();
    await pageA.waitForFunction(() => 'harness' in window);
    expect((await fetchRaw(pageB, urlOf(a.token, rel))).status, 'A after its navigation').toBe(404);
    const b1 = await bridgeOpen(pageB, takeB1.dir);
    expect((await fetchRaw(pageA, urlOf(b1.token, rel), {range: 'bytes=0-9'})).status, "B's first token works before the second open").toBe(206);
    const b2 = await bridgeOpen(pageB, takeB2.dir);
    expect((await fetchRaw(pageA, urlOf(b1.token, rel))).status, "B's first token after the second open").toBe(404);
    expect((await fetchRaw(pageA, urlOf(b2.token, rel), {range: 'bytes=0-9'})).status).toBe(206);
    await pageB.close();
    await expect.poll(async () => (await fetchRaw(pageA, urlOf(b2.token, rel))).status, {message: "B's second token after the close"}).toBe(404);
});

test('T-PLAY-64 the shared TakeFiles check suite on the Electron implementation', async ({harness: h}) => {
    await h.requireProduct();
    const folder = await writeSuiteFolder(h.recordings);
    const results = await h.page.evaluate(f => window.harness.takeFilesChecks(f), folder);
    expect(results.filter(r => !r.ok)).toEqual([]);
    expect(results.length).toBe(10);
});
