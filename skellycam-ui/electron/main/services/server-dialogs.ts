// The message boxes of specs/recorder.md 9.2 (Q925, Q927 [ADR-9V4Y]). Not unit tested: they need Electron.
import { BrowserWindow, dialog } from 'electron';
import { getLabels } from './menu-builder';

/** Item 1: no parent window, so the box shows also when no window is left. It returns the close of the box. */
export function showSavingNotice(): () => void {
    const t = getLabels();
    const box = new AbortController();
    // One system "OK" button: a click or a close removes the box only; the wait for the server goes on
    dialog.showMessageBox({ type: 'info', title: 'SkellyCam', message: t.savingRecordingsMessage, detail: t.savingRecordingsDetail, signal: box.signal })
        .catch(error => console.error('The saving message failed:', error));
    return () => box.abort();
}

/** Item 2: the app stays open; "Launch server" of the connection menu is the retry. */
export function showPortInUse(): void {
    const t = getLabels();
    const options = { type: 'error' as const, title: 'SkellyCam', message: t.portInUseMessage, detail: t.portInUseDetail };
    const window = BrowserWindow.getAllWindows().find(w => !w.isDestroyed());
    (window ? dialog.showMessageBox(window, options) : dialog.showMessageBox(options))
        .catch(error => console.error('The port-in-use message failed:', error));
}
