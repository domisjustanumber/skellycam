// Electron preload: result posting and manifest access over IPC (works for file://, app:// and http pages alike).
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('__harness', {
  post: (key, json) => ipcRenderer.send('harness-result', key, json),
  manifest: () => ipcRenderer.invoke('harness-manifest'),
});
