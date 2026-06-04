const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");
const { spawn } = require("node:child_process");

const { app, BrowserWindow, Menu, dialog, ipcMain, shell } = require("electron");
const { autoUpdater } = require("electron-updater");

const { createDesktopServer } = require("./static-server.cjs");

app.setName("TianShu");

let mainWindow = null;
let backendProcess = null;
let desktopServer = null;
let backendLogStream = null;
let startupState = {
  backendPort: 0,
  frontendUrl: ""
};

function repoRoot() {
  return app.isPackaged ? process.resourcesPath : path.resolve(__dirname, "..");
}

function userDataRoot() {
  return app.getPath("userData");
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function sqliteUrl(filePath) {
  return `sqlite+aiosqlite:///${filePath.replace(/\\/g, "/")}`;
}

function readOrCreateSecret(fileName) {
  const secretPath = path.join(userDataRoot(), fileName);
  if (fs.existsSync(secretPath)) {
    const existing = fs.readFileSync(secretPath, "utf8").trim();
    if (existing.length >= 32) return existing;
  }

  const secret = crypto.randomBytes(32).toString("hex");
  fs.writeFileSync(secretPath, `${secret}\n`, { encoding: "utf8", mode: 0o600 });
  return secret;
}

function resolvePythonExecutable(root) {
  const candidates = [
    path.join(root, ".python312", "python.exe"),
    path.join(root, ".python312", "Scripts", "python.exe"),
    path.join(root, ".python312", "bin", "python")
  ];
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (!found) {
    throw new Error(
      `Python runtime not found. Checked: ${candidates.join(", ")}`
    );
  }
  return found;
}

function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => {
        if (!address || typeof address === "string") {
          reject(new Error("Could not allocate a local port."));
          return;
        }
        resolve(address.port);
      });
    });
  });
}

function waitForHealth(port, timeoutMs = 90000) {
  const startedAt = Date.now();
  const healthUrl = `http://127.0.0.1:${port}/health`;

  return new Promise((resolve, reject) => {
    const poll = () => {
      const request = http.get(healthUrl, (response) => {
        response.resume();
        if (response.statusCode === 200) {
          resolve();
          return;
        }
        retry();
      });
      request.on("error", retry);
      request.setTimeout(2500, () => {
        request.destroy();
        retry();
      });
    };

    const retry = () => {
      if (Date.now() - startedAt > timeoutMs) {
        reject(new Error(`Backend health check timed out: ${healthUrl}`));
        return;
      }
      setTimeout(poll, 750);
    };

    poll();
  });
}

function backendEnvironment(root, frontendPort) {
  const dataDir = ensureDir(path.join(userDataRoot(), "data"));
  const skillsDir = ensureDir(path.join(userDataRoot(), "skills"));
  const logsDir = ensureDir(path.join(userDataRoot(), "logs"));
  const jwtSecret = readOrCreateSecret("jwt.secret");
  const modelSecret = readOrCreateSecret("model-config.secret");

  backendLogStream = fs.createWriteStream(path.join(logsDir, "backend.log"), {
    flags: "a"
  });

  return {
    ...process.env,
    TIANSHU_APP_ROOT: root,
    TIANSHU_RESOURCE_DIR: root,
    TIANSHU_USER_DATA_DIR: dataDir,
    TIANSHU_SKILLS_DIR: skillsDir,
    TIANSHU_DATABASE_URL: sqliteUrl(path.join(dataDir, "tianshu.db")),
    TIANSHU_JWT_SECRET: jwtSecret,
    TIANSHU_MODEL_CONFIG_SECRET: modelSecret,
    TIANSHU_CORS_ORIGINS: [
      `http://127.0.0.1:${frontendPort}`,
      `http://localhost:${frontendPort}`
    ].join(","),
    TIANSHU_ENV: "development",
    PYTHONUNBUFFERED: "1"
  };
}

async function startBackend(root, frontendPort) {
  const serverDir = path.join(root, "server");
  const python = resolvePythonExecutable(root);
  const backendPort = await getFreePort();
  const env = backendEnvironment(root, frontendPort);

  backendProcess = spawn(
    python,
    [
      "-m",
      "uvicorn",
      "app.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      String(backendPort)
    ],
    {
      cwd: serverDir,
      env,
      windowsHide: true
    }
  );

  backendProcess.stdout.on("data", (chunk) => backendLogStream?.write(chunk));
  backendProcess.stderr.on("data", (chunk) => backendLogStream?.write(chunk));
  backendProcess.on("exit", (code, signal) => {
    backendLogStream?.write(
      `\n[desktop] backend exited code=${code} signal=${signal}\n`
    );
  });

  await waitForHealth(backendPort);
  return backendPort;
}

function stopBackend() {
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill();
  }
  backendProcess = null;
  backendLogStream?.end();
  backendLogStream = null;
}

function installMenu() {
  const template = [
    {
      label: "TianShu",
      submenu: [
        {
          label: "检查更新",
          click: () => checkForUpdates()
        },
        { type: "separator" },
        {
          label: "打开用户数据目录",
          click: () => shell.openPath(userDataRoot())
        },
        { type: "separator" },
        { role: "quit", label: "退出" }
      ]
    },
    {
      label: "View",
      submenu: [
        { role: "reload" },
        { role: "forceReload" },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" }
      ]
    }
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function isTrustedExternalUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

function sendUpdateStatus(payload) {
  mainWindow?.webContents.send("desktop:update-status", payload);
}

function allowUnsignedAutoUpdates() {
  return process.env.TIANSHU_ALLOW_UNSIGNED_AUTO_UPDATES === "true";
}

function unsignedUpdatesAreBlocked() {
  return autoUpdater.verifyUpdateCodeSignature === false && !allowUnsignedAutoUpdates();
}

async function checkForUpdates() {
  if (!app.isPackaged) {
    sendUpdateStatus({ status: "skipped", message: "Updater only runs in packaged builds." });
    return { skipped: true };
  }
  if (unsignedUpdatesAreBlocked()) {
    const message =
      "Auto-update is disabled until Windows code signing and update signature verification are enabled.";
    sendUpdateStatus({ status: "skipped", message });
    return { skipped: true, message };
  }

  try {
    const result = await autoUpdater.checkForUpdatesAndNotify();
    sendUpdateStatus({ status: "checked" });
    return { updateInfo: result?.updateInfo ?? null };
  } catch (error) {
    sendUpdateStatus({ status: "error", message: error.message });
    return { error: error.message };
  }
}

function configureUpdater() {
  if (unsignedUpdatesAreBlocked()) {
    autoUpdater.autoDownload = false;
    autoUpdater.autoInstallOnAppQuit = false;
    return;
  }
  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.on("checking-for-update", () =>
    sendUpdateStatus({ status: "checking" })
  );
  autoUpdater.on("update-available", (info) =>
    sendUpdateStatus({ status: "available", version: info.version })
  );
  autoUpdater.on("update-not-available", () =>
    sendUpdateStatus({ status: "not-available" })
  );
  autoUpdater.on("download-progress", (progress) =>
    sendUpdateStatus({
      status: "downloading",
      percent: Math.round(progress.percent)
    })
  );
  autoUpdater.on("update-downloaded", (info) =>
    sendUpdateStatus({ status: "downloaded", version: info.version })
  );
  autoUpdater.on("error", (error) =>
    sendUpdateStatus({ status: "error", message: error.message })
  );
}

async function createMainWindow() {
  const root = repoRoot();
  const distDir = path.join(root, "client", "dist");
  const provisionalFrontendPort = await getFreePort();
  const backendPort = await startBackend(root, provisionalFrontendPort);

  desktopServer = await createDesktopServer({
    distDir,
    backendPort,
    port: provisionalFrontendPort
  });

  startupState = {
    backendPort,
    frontendUrl: desktopServer.url
  };

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1180,
    minHeight: 760,
    title: "TianShu",
    backgroundColor: "#05070d",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, "preload.cjs")
    }
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (isTrustedExternalUrl(url)) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });

  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (url.startsWith(desktopServer.url)) {
      return;
    }
    event.preventDefault();
    if (isTrustedExternalUrl(url)) {
      shell.openExternal(url);
    }
  });

  await mainWindow.loadURL(`${desktopServer.url}/scenarios`);
  if (app.isPackaged) {
    setTimeout(() => checkForUpdates(), 2500);
  }
}

ipcMain.handle("desktop:get-app-info", () => ({
  version: app.getVersion(),
  isPackaged: app.isPackaged,
  backendPort: startupState.backendPort,
  frontendUrl: startupState.frontendUrl,
  userDataDir: userDataRoot()
}));

ipcMain.handle("desktop:check-for-updates", () => checkForUpdates());

app.whenReady().then(async () => {
  installMenu();
  configureUpdater();
  try {
    await createMainWindow();
  } catch (error) {
    dialog.showErrorBox(
      "TianShu failed to start",
      `${error.message}\n\nLogs: ${path.join(userDataRoot(), "logs", "backend.log")}`
    );
    stopBackend();
    app.quit();
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createMainWindow().catch((error) => {
      dialog.showErrorBox("TianShu failed to start", error.message);
    });
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  desktopServer?.close();
  desktopServer = null;
  stopBackend();
});
