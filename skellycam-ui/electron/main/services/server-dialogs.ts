// The message boxes of specs/recorder.md 9.2 (Q925, Q927 [ADR-9V4Y]). Not unit tested: they need Electron.
import { BrowserWindow, dialog } from 'electron';
import { getLabels } from './menu-builder';
import { savingBoxPlace } from './server-messages.ts';

const openWindow = () => BrowserWindow.getAllWindows().find(w => !w.isDestroyed());

/** Item 1: on the window if one exists, else alone (no box on macOS). It returns the close of the box. */
export function showSavingNotice(): () => void {
    const window = openWindow();
    if (savingBoxPlace(process.platform, window !== undefined) === 'none') return () => {};
    const t = getLabels();
    const box = new AbortController();
    // One system "OK" button: a click or a close removes the box only; the wait for the server goes on
    const options = { type: 'info' as const, title: 'SkellyCam', message: t.savingRecordingsMessage, detail: t.savingRecordingsDetail, signal: box.signal };
    (window ? dialog.showMessageBox(window, options) : dialog.showMessageBox(options))
        .catch(error => console.error('The saving message failed:', error));
    return () => box.abort();
}

/** Item 2: the app stays open; "Launch server" of the connection menu is the retry. */
export function showPortInUse(): void {
    const t = getLabels();
    const options = { type: 'error' as const, title: 'SkellyCam', message: t.portInUseMessage, detail: t.portInUseDetail };
    const window = openWindow();
    (window ? dialog.showMessageBox(window, options) : dialog.showMessageBox(options))
        .catch(error => console.error('The port-in-use message failed:', error));
}
