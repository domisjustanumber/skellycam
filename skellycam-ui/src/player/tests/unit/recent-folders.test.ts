// Unit tests of the recently opened folders (specs/player.md 5.10; ADR-8J08, ADR-FHP6): T-PLAY-87, T-PLAY-88,
// T-PLAY-90 and T-PLAY-91.
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {RECENT_FILE, addRecent, checkRecent, dialogFolder, parseRecent, readRecent, recentStore, recentText} from '../../main/recent-folders.ts';

const win = process.platform === 'win32';
const abs = (name: string) => path.resolve(os.tmpdir(), 'recent-test', name);
const fileOf = (folders: unknown, version: unknown = 1) => JSON.stringify({version, folders});

function tempDir(t: {after(fn: () => void): void}): string {
    const dir = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'skellycam-recent-')));
    t.after(() => rmSync(dir, {recursive: true, force: true}));
    return dir;
}

test('T-PLAY-87 the list: most recent first, a repeat to the top, 5 at most, only valid paths', () => {
    const [a, b] = [abs('A'), abs('B')];
    assert.equal(RECENT_FILE, 'recent-take-folders.json');
    assert.deepEqual(addRecent([], a), [a]);
    assert.deepEqual(addRecent([a], b), [b, a]);
    assert.deepEqual(addRecent([b, a], a), [a, b], 'a repeat pick moves to the top');
    let list: string[] = [];
    for (const n of ['1', '2', '3', '4', '5', '6']) list = addRecent(list, abs(n));
    assert.deepEqual(list, ['6', '5', '4', '3', '2'].map(abs), 'the sixth pick drops the first');
    const upper = addRecent([a], a.toUpperCase());
    assert.deepEqual(upper, win ? [a.toUpperCase()] : [a.toUpperCase(), a], 'another case is the same entry on Windows only');
    assert.deepEqual(addRecent([a], 'relative/take'), [a], 'a relative pick adds no entry');
    assert.deepEqual(addRecent([a], '\\\\host\\share\\take'), [a], 'a UNC pick adds no entry');
    assert.deepEqual(addRecent([a], '//host/share/take'), [a]);
});

test('T-PLAY-87 the file text: version 1, a 2-space indent, a final LF; it reads back', () => {
    const list = [abs('B'), abs('A')];
    assert.equal(recentText(list), `{\n  "version": 1,\n  "folders": [\n    ${list.map(p => JSON.stringify(p)).join(',\n    ')}\n  ]\n}\n`);
    assert.equal(recentText([]), '{\n  "version": 1,\n  "folders": []\n}\n', 'the file of a cleared list');
    assert.deepEqual(parseRecent(recentText(list)), list);
    assert.deepEqual(parseRecent(recentText([])), []);
});

test('T-PLAY-87 the read of a wrong file gives an empty list', () => {
    const a = abs('A');
    for (const [why, text] of [
        ['not JSON', '{"version": 1, "folders": ['],
        ['empty', ''],
        ['an array', JSON.stringify([a])],
        ['null', 'null'],
        ['a string', JSON.stringify(a)],
        ['version 2', fileOf([a], 2)],
        ['version "1"', fileOf([a], '1')],
        ['no version', JSON.stringify({folders: [a]})],
        ['folders not an array', fileOf({0: a})],
        ['no folders', JSON.stringify({version: 1})],
    ] as const) assert.deepEqual(parseRecent(text), [], why);
});

test('T-PLAY-87 the read leaves out each wrong item, and keeps the first 5', () => {
    const [a, b] = [abs('A'), abs('B')];
    const wrong = [3, null, true, {path: a}, [a], '', 'x'.repeat(10), `${a}\u0000x`, 'relative/take', '.\\take',
        '\\\\host\\share\\take', '//host/share/take', '\\\\?\\C:\\take', '\\\\.\\C:\\take',
        path.resolve(os.tmpdir(), 'x'.repeat(32_768))];
    assert.deepEqual(parseRecent(fileOf([...wrong, a, b])), [a, b]);
    assert.deepEqual(parseRecent(fileOf([a, b, win ? a.toUpperCase() : a])), [a, b], 'a repeat is left out');
    const seven = ['1', '2', '3', '4', '5', '6', '7'].map(abs);
    assert.deepEqual(parseRecent(fileOf(seven)), seven.slice(0, 5));
    assert.deepEqual(parseRecent(fileOf([...wrong.slice(0, 4), ...seven])), seven.slice(0, 5), 'wrong items do not count');
});

test('T-PLAY-87 the file: missing, larger than 1 MiB, or valid', async t => {
    const dir = tempDir(t);
    const file = path.join(dir, RECENT_FILE);
    assert.deepEqual(await readRecent(file), [], 'no file');
    const a = abs('A');
    writeFileSync(file, recentText([a]));
    assert.deepEqual(await readRecent(file), [a]);
    // valid JSON, but past the limit
    writeFileSync(file, recentText([a]).replace('{', '{' + ' '.repeat(1024 * 1024)));
    assert.deepEqual(await readRecent(file), [], 'a file larger than 1 MiB');
    rmSync(file);
    mkdirSync(file);
    assert.deepEqual(await readRecent(file), [], 'a folder in place of the file');
});

test('T-PLAY-87 a FIFO in place of the file gives an empty list and does not block', {skip: win ? 'no FIFO on Windows' : false}, async t => {
    const file = path.join(tempDir(t), RECENT_FILE);
    execFileSync('mkfifo', [file]);
    const result = await Promise.race([readRecent(file), new Promise(resolve => setTimeout(() => resolve('blocked'), 2000))]);
    assert.deepEqual(result, []);
});

test('T-PLAY-88 the check at the click: a listed real folder passes with its stored path', async t => {
    const dir = tempDir(t);
    const a = path.join(dir, 'take_a');
    mkdirSync(a);
    assert.deepEqual(await checkRecent([a], a), {ok: true, folder: a});
    assert.deepEqual(await checkRecent([a], path.join(dir, 'take_b')), {ok: false, reason: 'not listed'});
    assert.deepEqual(await checkRecent([a], 7), {ok: false, reason: 'not listed'});
    assert.deepEqual(await checkRecent([], a), {ok: false, reason: 'not listed'});
    assert.deepEqual(await checkRecent([a], a.toUpperCase()), win ? {ok: true, folder: a} : {ok: false, reason: 'not listed'},
        'another case finds the stored entry on Windows only');
});

test('T-PLAY-88 the check at the click: deleted, replaced by a link, a file, a link path are gone', async t => {
    const dir = tempDir(t);
    const linkKind = win ? 'junction' : 'dir';
    const a = path.join(dir, 'take_a');
    const other = path.join(dir, 'other');
    mkdirSync(other);
    assert.deepEqual(await checkRecent([a], a), {ok: false, reason: 'gone'}, 'never made');
    mkdirSync(a);
    rmSync(a, {recursive: true});
    assert.deepEqual(await checkRecent([a], a), {ok: false, reason: 'gone'}, 'deleted');
    symlinkSync(other, a, linkKind);
    assert.deepEqual(await checkRecent([a], a), {ok: false, reason: 'gone'}, 'replaced by a link to another folder');
    rmSync(a, {recursive: true, force: true});
    writeFileSync(a, 'x');
    assert.deepEqual(await checkRecent([a], a), {ok: false, reason: 'gone'}, 'a file in its place');
    const link = path.join(dir, 'link_to_other');
    symlinkSync(other, link, linkKind);
    assert.deepEqual(await checkRecent([link], link), {ok: false, reason: 'gone'}, 'an entry that is the path of a link');
    const dotted = [other, '..', 'other'].join(path.sep);   // not path.join: it would remove the ..
    assert.deepEqual(await checkRecent([dotted], dotted), {ok: false, reason: 'gone'}, 'an entry with ..');
});

test('T-PLAY-90 the store: a click opens a listed folder, moves it to the top and writes the file', async t => {
    const dir = tempDir(t);
    const [a, b] = ['take_a', 'take_b'].map(n => path.join(dir, n));
    mkdirSync(a);
    mkdirSync(b);
    const file = path.join(dir, 'data', RECENT_FILE);
    const store = await recentStore(file);
    assert.deepEqual(store.list(), [], 'no file');
    await store.add(a);
    await store.add(b);
    assert.deepEqual(store.list(), [b, a]);
    const opened: string[] = [];
    assert.equal(await store.open(a, f => opened.push(f)), a);
    assert.deepEqual(opened, [a], 'the stored path becomes the pick');
    assert.deepEqual(store.list(), [a, b]);
    assert.deepEqual(parseRecent(readFileSync(file, 'utf8')), [a, b]);
    await assert.rejects(store.open(path.join(dir, 'other'), f => opened.push(f)), /folder not allowed/);
    rmSync(b, {recursive: true});
    await assert.rejects(store.open(b, f => opened.push(f)), /folder gone/);
    assert.deepEqual(store.list(), [a], 'a gone entry leaves the list');
    assert.deepEqual(parseRecent(readFileSync(file, 'utf8')), [a]);
    assert.deepEqual(opened, [a]);
    await store.clear();
    assert.deepEqual(parseRecent(readFileSync(file, 'utf8')), []);
});

test('T-PLAY-90 the store: a clear during the check of a click opens nothing and is not undone', async t => {
    const dir = tempDir(t);
    const a = path.join(dir, 'take_a');
    mkdirSync(a);
    const file = path.join(dir, RECENT_FILE);
    const store = await recentStore(file);
    await store.add(a);
    const opened: string[] = [];
    const click = store.open(a, f => opened.push(f));
    const cleared = store.clear();   // runs while the click waits for its realpath
    await assert.rejects(click, /folder not allowed/);
    await cleared;
    assert.deepEqual(opened, [], 'no pick');
    assert.deepEqual(store.list(), [], 'the clear stays');
    assert.deepEqual(parseRecent(readFileSync(file, 'utf8')), []);
});

test('T-PLAY-91 the dialog folder: the top entry; with an empty list the recordings folder, else the home folder', async t => {
    const dir = tempDir(t);
    const recordings = path.join(dir, 'recordings');
    const home = path.join(dir, 'home');
    assert.equal(await dialogFolder([abs('B'), abs('A')], recordings, home), abs('B'));
    assert.equal(await dialogFolder([], recordings, home), home, 'no recordings folder');
    writeFileSync(recordings, 'x');
    assert.equal(await dialogFolder([], recordings, home), home, 'a file in place of the recordings folder');
    rmSync(recordings);
    mkdirSync(recordings);
    assert.equal(await dialogFolder([], recordings, home), recordings);
});
