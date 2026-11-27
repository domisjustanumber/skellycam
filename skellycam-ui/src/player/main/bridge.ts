// The preload bridge of the take handler (specs/player.md sections 4.3, step 2, and 5.10). The page gets `open`,
// `close` and the calls of the recently opened list: no call can add a folder to the picked list or to that list [U1].
import type {ContextBridge, IpcRenderer} from 'electron';

export const TAKE_CHANNELS = ['skellycam-take:open', 'skellycam-take:close', 'skellycam-take:recent',
    'skellycam-take:open-recent', 'skellycam-take:clear-recent'] as const;

export function exposeTakeBridge(contextBridge: ContextBridge, ipcRenderer: IpcRenderer): void {
    contextBridge.exposeInMainWorld('skellycamTake', {
        open: (folderPath: string) => ipcRenderer.invoke(TAKE_CHANNELS[0], folderPath),
        close: (token: string) => ipcRenderer.invoke(TAKE_CHANNELS[1], token),
        recent: () => ipcRenderer.invoke(TAKE_CHANNELS[2]),
        openRecent: (folder: string) => ipcRenderer.invoke(TAKE_CHANNELS[3], folder),
        clearRecent: () => ipcRenderer.invoke(TAKE_CHANNELS[4]),
    });
}
