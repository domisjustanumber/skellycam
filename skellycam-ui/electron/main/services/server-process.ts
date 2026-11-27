// The start of the server process: specs/recorder.md 9.3 (choices ADR-YR3G). No electron import: the unit tests run in Node.
import { spawn, type ChildProcess } from 'node:child_process';

export const STDERR_TAIL_CHARS = 4096;

export interface ServerProcess {
    child: ChildProcess;
    stderrTail: () => string;
}

/**
 * No shell and no output limit, so no output size can kill or detach the server. stdout goes to the null device
 * (nobody read it; it cannot fill or block); stderr is read at all times and only its tail is kept (9.2 item 2).
 */
// The caller must add an 'error' listener before the next tick (python-server.ts does), or ENOENT crashes the main process
export function startServerProcess(executablePath: string, args: string[] = []): ServerProcess {
    const child = spawn(executablePath, args, { env: { ...process.env }, stdio: ['pipe', 'ignore', 'pipe'] });
    let tail = '';
    child.stderr?.setEncoding('utf8');
    child.stderr?.on('data', (chunk: string) => { tail = (tail + chunk).slice(-STDERR_TAIL_CHARS); });
    return { child, stderrTail: () => tail };
}
