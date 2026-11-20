// Electron tests of the findings of the 6a code review: T-PLAY-77 to T-PLAY-79 (ADR-5FBS).
import {expect} from '@playwright/test';
import type {Page} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {closeSync, ftruncateSync, linkSync, mkdirSync, openSync, writeFileSync} from 'node:fs';
import path from 'node:path';
import {patternBytes} from '../fixtures/take-files-checks.ts';
import {harnessTest} from './harness.ts';

const test = harnessTest('harness');
const open = (page: Page, folder: string) =>
    page.evaluate(f => (window as never as {skellycamTake: {open(f: string): Promise<{token: string; entries: {path: string}[]}>}}).skellycamTake.open(f), folder);
const status = (page: Page, url: string) => page.evaluate(async u => (await fetch(u, {cache: 'no-store', headers: {Range: 'bytes=0-9'}})).status, url);

test('T-PLAY-77 a hard link is not served, in the snapshot and at the first read', async ({harness: h}) => {
    await h.requireProduct();
    const folder = path.join(h.recordings, 'links');
    const media = path.join(folder, 'synchronized_videos');
    mkdirSync(media, {recursive: true});
    const outside = path.join(h.root, 'outside');
    mkdirSync(outside, {recursive: true});
    writeFileSync(path.join(outside, 'secret.bin'), 'SECRET-OUTSIDE');
    linkSync(path.join(outside, 'secret.bin'), path.join(media, 'h.mkv'));
    writeFileSync(path.join(media, 'a.mkv'), patternBytes(1, 0, 4096));
    const opened = await open(h.page, folder);
    expect(opened.entries.map(e => e.path)).toEqual(['synchronized_videos/a.mkv']);
    // a hard link made after the open: the first read refuses the file
    linkSync(path.join(media, 'a.mkv'), path.join(outside, 'a_link.mkv'));
    expect(await status(h.page, `skellycam-take://${opened.token}/synchronized_videos/a.mkv`)).toBe(404);
});

test('T-PLAY-78 UNC, device and relative paths are refused', async ({harness: h}) => {
    await h.requireProduct();
    const inside = path.join(h.recordings, 'inside');
    mkdirSync(path.join(inside, 'synchronized_videos'), {recursive: true});
    for (const p of ['\\\\nonexistent.invalid\\share\\take', '//nonexistent.invalid/share/take', `\\\\?\\${inside}`, `\\\\.\\${inside}`, 'relative/take']) {
        await expect(open(h.page, p), p).rejects.toThrow(/folder not allowed/);
    }
});

test('T-PLAY-79 a whole-file request does not hold the file in one main-process buffer', async ({harness: h}) => {
    test.setTimeout(180_000);
    await h.requireProduct();
    const folder = path.join(h.recordings, 'large');
    const file = path.join(folder, 'synchronized_videos', 'big.mkv');
    mkdirSync(path.dirname(file), {recursive: true});
    writeFileSync(file, new Uint8Array(0));
    if (process.platform === 'win32') execFileSync('fsutil', ['sparse', 'setflag', file]);
    const size = 512 * 1024 * 1024;
    const fd = openSync(file, 'r+');
    ftruncateSync(fd, size);
    closeSync(fd);
    const {token} = await open(h.page, folder);
    const mainMB = () => h.app.evaluate(({app}) => app.getAppMetrics().filter(m => m.type === 'Browser').reduce((a, m) => a + m.memory.workingSetSize, 0) / 1024);
    const before = await mainMB();
    let peak = before;
    const timer = setInterval(() => void mainMB().then(v => (peak = Math.max(peak, v))).catch(() => undefined), 100);
    const got = await h.page.evaluate(async u => {
        const res = await fetch(u, {cache: 'no-store'});
        const reader = res.body!.getReader();
        let n = 0;
        for (let r = await reader.read(); !r.done; r = await reader.read()) n += r.value.length;
        return {status: res.status, n};
    }, `skellycam-take://${token}/synchronized_videos/big.mkv`);
    clearInterval(timer);
    peak = Math.max(peak, await mainMB());
    expect(got).toEqual({status: 200, n: size});
    expect(peak - before, `main process grew from ${Math.round(before)} to ${Math.round(peak)} MB`).toBeLessThan(200);
});
