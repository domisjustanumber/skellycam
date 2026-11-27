// Run: node --experimental-strip-types --test electron/main/services/tests/server-messages.test.ts
// specs/recorder.md 9.2: the "saving" message (Q925) and "port in use" (Q927) [ADR-9V4Y], choices ADR-590X
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test, { mock } from 'node:test';
import {
    SAVING_NOTICE_DELAY_MS,
    SERVER_MESSAGE_TEXTS,
    endedWithPortInUse,
    noticeWhileWaiting,
    processIsRunning,
    savingBoxPlace,
} from '../server-messages.ts';

const source = (path: string) => readFileSync(new URL(`../../../../${path}`, import.meta.url), 'utf8');

function deferred<T>() {
    let resolve!: (value: T) => void;
    let reject!: (error: unknown) => void;
    const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
    return { promise, resolve, reject };
}

test('T-APP-01: the "saving" box shows after 10 s of the wait, once, and closes at its end (9.2 item 1)', async () => {
    mock.timers.enable({ apis: ['setTimeout'] });
    try {
        assert.equal(SAVING_NOTICE_DELAY_MS, 10_000);
        let shown = 0;
        let closed = 0;
        const show = () => { shown += 1; return () => { closed += 1; }; };

        const quick = deferred<string>();
        const a = noticeWhileWaiting(quick.promise, SAVING_NOTICE_DELAY_MS, show);
        mock.timers.tick(9_999);
        quick.resolve('exited');
        assert.equal(await a, 'exited');
        mock.timers.tick(20_000);
        assert.deepEqual([shown, closed], [0, 0], 'a wait that ends before 10 s shows no box');

        const slow = deferred<void>();
        const b = noticeWhileWaiting(slow.promise, SAVING_NOTICE_DELAY_MS, show);
        mock.timers.tick(9_999);
        assert.equal(shown, 0);
        mock.timers.tick(1);
        assert.deepEqual([shown, closed], [1, 0], 'the box shows at 10 s and stays');
        mock.timers.tick(600_000);
        assert.deepEqual([shown, closed], [1, 0], 'no bound: the box stays and does not come again');
        slow.resolve();
        await b;
        assert.deepEqual([shown, closed], [1, 1], 'the box closes when the wait ends');

        const failing = deferred<void>();
        const c = noticeWhileWaiting(failing.promise, SAVING_NOTICE_DELAY_MS, show);
        mock.timers.tick(10_000);
        const error = new Error('Python was left running to protect active video saves');
        failing.reject(error);
        await assert.rejects(c, (e: unknown) => e === error);
        assert.deepEqual([shown, closed], [2, 2], 'the box closes when the wait fails');
    } finally {
        mock.timers.reset();
    }
});

test('T-APP-05: the "saving" box has the window as parent when one exists; on macOS with no window there is no box (9.2 item 1)', () => {
    for (const platform of ['win32', 'linux', 'darwin'] as const) {
        assert.equal(savingBoxPlace(platform, true), 'window', `${platform} with a window`);
    }
    assert.equal(savingBoxPlace('win32', false), 'alone');
    assert.equal(savingBoxPlace('linux', false), 'alone');
    // macOS runs a box with no parent synchronously: its `signal` cannot close it, and it holds the main process
    assert.equal(savingBoxPlace('darwin', false), 'none');
});

// The Windows line is from a real run on 2026-11-27; Linux and macOS follow `loop.create_server` of CPython 3.13
const WINDOWS = "ERROR:    [Errno 10048] error while attempting to bind on address ('127.0.0.1', 53117): [winerror 10048] only one usage of each socket address (protocol/network address/port) is normally permitted\n";
const LINUX = "ERROR:    [Errno 98] error while attempting to bind on address ('127.0.0.1', 53117): address already in use\n";
const MACOS = "ERROR:    [Errno 48] error while attempting to bind on address ('::1', 53117, 0, 0): address already in use\n";
const RESERVED = "ERROR:    [Errno 10013] error while attempting to bind on address ('127.0.0.1', 53117): [winerror 10013] an attempt was made to access a socket in a way forbidden by its access permissions\n";

test('T-APP-02: the port-in-use rule: a non-zero exit and the bind error of a port in use (9.2 item 2)', () => {
    for (const line of [WINDOWS, LINUX, MACOS]) {
        assert.equal(endedWithPortInUse(3, line), true, line);
        assert.equal(endedWithPortInUse(3, `INFO: earlier lines\n${line}`), true, line);
        assert.equal(endedWithPortInUse(0, line), false, `code 0: ${line}`);
        assert.equal(endedWithPortInUse(null, line), false, `no code: ${line}`);
    }
    assert.equal(endedWithPortInUse(1, 'RuntimeError: something else\n'), false);
    assert.equal(endedWithPortInUse(3, RESERVED), false, 'another errno is not "port in use"');
    assert.equal(endedWithPortInUse(3, ''), false);
});

test('T-APP-03: isRunning is false after the server process ended (9.2 item 2)', () => {
    const alive = { pid: 42, exitCode: null, signalCode: null, killed: false };
    assert.equal(processIsRunning(alive), true);
    assert.equal(processIsRunning({ ...alive, exitCode: 3 }), false, 'an exit code');
    assert.equal(processIsRunning({ ...alive, exitCode: 0 }), false, 'exit code 0');
    assert.equal(processIsRunning({ ...alive, signalCode: 'SIGTERM' }), false, 'a signal');
    assert.equal(processIsRunning({ ...alive, killed: true }), false, 'killed');
    assert.equal(processIsRunning({ ...alive, pid: undefined }), false, 'no PID');
    assert.equal(processIsRunning(null), false, 'no process');
});

test('T-APP-04: the four texts in English, es, zh-CN and ar, and the renderer sends each (9.2 item 3, Q948)', () => {
    const keys = ['savingRecordingsMessage', 'savingRecordingsDetail', 'portInUseMessage', 'portInUseDetail'] as const;
    const en: Record<string, string> = JSON.parse(source('src/i18n/locales/en-english.json'));
    assert.equal(en.savingRecordingsMessage, 'Recordings are still being saved.');
    assert.equal(en.savingRecordingsDetail, 'SkellyCam closes by itself when this is done.');
    assert.equal(en.portInUseMessage, 'SkellyCam cannot start its server: port {{port}} is in use.');
    assert.equal(en.portInUseDetail, 'Another program, or another copy of SkellyCam, uses this port. Close it, then click “Launch server” in the connection menu, or restart SkellyCam.');
    // the main process has the English texts until the renderer sends its labels
    for (const key of keys) assert.equal(SERVER_MESSAGE_TEXTS[key], en[key].replace('{{port}}', '53117'), key);
    for (const file of ['es-espanol.json', 'zh-CN-zhongwen.json', 'ar-arabic.json']) {
        const texts: Record<string, string> = JSON.parse(source(`src/i18n/locales/${file}`));
        for (const key of keys) {
            assert.ok(texts[key] && texts[key] !== en[key], `${file}: ${key}`);
        }
        assert.ok(texts.portInUseMessage.includes('{{port}}'), `${file}: the port`);
        assert.ok(texts.portInUseDetail.includes('SkellyCam') && texts.portInUseDetail.includes('Launch server'), `${file}: names`);
    }
    // No React render in the node unit tests: the renderer's key list is read as text
    const hook = source('src/hooks/useMenuActions.ts');
    for (const key of keys) assert.match(hook, new RegExp(`'${key}',`), `useMenuActions.ts does not send ${key}`);
    assert.match(hook, /t\(key, \{ port: DEFAULT_PORT \}\)/, 'the renderer does not fill {{port}}');
});
