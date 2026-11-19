// The preload script of the test Electron app: the bridge of the module (4.3 step 2), and a raw IPC
// pass-through that only the harness has, so T-PLAY-62 can call each channel of the module from a page.
import {contextBridge, ipcRenderer} from 'electron';

contextBridge.exposeInMainWorld('harnessIpc', {
    invoke: (channel: string, ...args: unknown[]) => ipcRenderer.invoke(channel, ...args),
    send: (channel: string, ...args: unknown[]) => ipcRenderer.send(channel, ...args),
    productError: () => ipcRenderer.invoke('harness:product-error'),
});

import('../../main/bridge.ts')
    .then(m => m.exposeTakeBridge(contextBridge, ipcRenderer))
    .catch(e => contextBridge.exposeInMainWorld('harnessBridgeError', String(e)));
