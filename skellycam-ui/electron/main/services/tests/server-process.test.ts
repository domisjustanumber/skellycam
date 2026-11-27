// Run: node --experimental-strip-types --test electron/main/services/tests/server-process.test.ts
// specs/recorder.md 9.3: no output size can kill or detach the server (choices ADR-YR3G)
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { startServerProcess } from '../server-process.ts';

const CHILD = fileURLToPath(new URL('./big-output-child.mjs', import.meta.url));
const LINE = "ERROR:    [Errno 10048] error while attempting to bind on address ('127.0.0.1', 53117): end\n";

test('T-APP-06: a server that writes more than 100 MiB to stdout and to stderr still runs, with a PID (9.3)', async () => {
    const { child, stderrTail } = startServerProcess(process.execPath, [CHILD]);
    const exit = once(child, 'exit');
    try {
        assert.ok(child.pid, 'no PID');
        const deadline = Date.now() + 60_000;
        while (!stderrTail().endsWith(LINE)) {
            assert.ok(child.exitCode === null && child.signalCode === null,
                `the server process ended: code ${child.exitCode}, signal ${child.signalCode}`);
            assert.ok(Date.now() < deadline, 'the child wrote its output for 60 s');
            await new Promise(resolve => setTimeout(resolve, 20));
        }
        assert.equal(child.exitCode, null);
        assert.equal(child.signalCode, null);
        assert.equal(child.killed, false);
        assert.ok(stderrTail().length <= 4096, `the tail has ${stderrTail().length} characters`);
    } finally {
        if (child.exitCode === null && child.signalCode === null) child.kill(); // the test's own child
        await exit;
    }
});
