const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("tianshuDesktop", {
  getAppInfo: () => ipcRenderer.invoke("desktop:get-app-info"),
  checkForUpdates: () => ipcRenderer.invoke("desktop:check-for-updates"),
  onUpdateStatus: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("desktop:update-status", listener);
    return () => ipcRenderer.removeListener("desktop:update-status", listener);
  }
});
