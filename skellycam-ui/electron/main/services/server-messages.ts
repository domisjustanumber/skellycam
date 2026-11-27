// The two messages of the end and the start of the server: specs/recorder.md 9.2 (Q925, Q927 [ADR-9V4Y])
// No electron import: the unit tests run in Node.
import type {ChildProcess} from 'node:child_process';
import {DEFAULT_PORT} from '../../../src/services/server/server-helpers/server-urls.ts';

export const SAVING_NOTICE_DELAY_MS = 10_000;

// English until the renderer sends the translated texts with the menu labels
export const SERVER_MESSAGE_TEXTS = {
    savingRecordingsMessage: 'Recordings are still being saved.',
    savingRecordingsDetail: 'SkellyCam closes by itself when this is done.',
    portInUseMessage: `SkellyCam cannot start its server: port ${DEFAULT_PORT} is in use.`,
    portInUseDetail: 'Another program, or another copy of SkellyCam, uses this port. Close it, then click “Launch server” in the connection menu, or restart SkellyCam.',
};

/** Q925: the wait has no bound. After `delayMs` it calls `show`, once; at the end of the wait it closes what show opened. */
export async function noticeWhileWaiting<T>(wait: Promise<T>, delayMs: number, show: () => () => void): Promise<T> {
    let close = () => {};
    const timer = setTimeout(() => { close = show(); }, delayMs);
    try {
        return await wait;
    } finally {
        clearTimeout(timer);
        close();
    }
}

// The bind error of `loop.create_server` for a port in use: WSAEADDRINUSE on Windows, EADDRINUSE on Linux and macOS
const PORT_IN_USE = /\[Errno (?:10048|98|48)\] error while attempting to bind on address/;

/** Q927: the server ended with an error code, and the end of its stderr holds the bind error of a port in use. */
export function endedWithPortInUse(code: number | null, stderrTail: string): boolean {
    return code !== null && code !== 0 && PORT_IN_USE.test(stderrTail);
}

export function processIsRunning(child: Pick<ChildProcess, 'pid' | 'exitCode' | 'signalCode' | 'killed'> | null): boolean {
    return child !== null && child.pid !== undefined && !child.killed && child.exitCode === null && child.signalCode === null;
}
