// The preload bridge of the take handler (specs/player.md section 4.3, step 2). The page gets `open`
// and `close` only: no call can add a folder to the picked list [U1].
import type {ContextBridge, IpcRenderer} from 'electron';

export const TAKE_CHANNELS = ['skellycam-take:open', 'skellycam-take:close'] as const;

export function exposeTakeBridge(contextBridge: ContextBridge, ipcRenderer: IpcRenderer): void {
    contextBridge.exposeInMainWorld('skellycamTake', {
        open: (folderPath: string) => ipcRenderer.invoke(TAKE_CHANNELS[0], folderPath),
        close: (token: string) => ipcRenderer.invoke(TAKE_CHANNELS[1], token),
    });
}
