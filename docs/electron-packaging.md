# Electron desktop packaging

This repository can be packaged as a Windows desktop app with Electron,
electron-builder, and electron-updater.

## Runtime model

- Electron starts a bundled Python FastAPI backend on `127.0.0.1:<random>`.
- Electron starts a local Node HTTP server on `127.0.0.1:<random>` to serve
  `client/dist` and proxy `/api/*` to the backend.
- The renderer keeps using the existing relative `/api` client path, so React
  business logic does not need a desktop-specific API branch.
- Bundled read-only resources live under `process.resourcesPath`:
  - `server/`
  - `gym/`
  - `client/dist/`
  - `client/src/scenarios/`
  - `.python312/`
- Mutable desktop data lives under Electron `app.getPath("userData")`:
  - SQLite DB: `data/aicc.db`
  - custom skills: `skills/`
  - backend logs: `logs/backend.log`
  - generated local secrets: `jwt.secret`, `model-config.secret`

## Local build

Install dependencies once:

```powershell
npm ci
npm ci --prefix client
```

Build an unpacked desktop directory:

```powershell
npm run electron:pack
```

Build a Windows NSIS installer:

```powershell
npm run electron:dist
```

The installer is written to `dist-electron/`.

## Publishing updates

`package.json` publishes to GitHub repository `Alec1003/tianshu`. The release
workflow runs when a `v*` tag is pushed.

1. Bump the root `package.json` version.
2. Commit the change.
3. Create and push a matching tag, for example:

```powershell
git tag v0.2.1
git push tianshu codex/electron-updater-package
git push tianshu v0.2.1
```

GitHub Actions builds the installer and publishes release metadata such as
`latest.yml`. Packaged apps use `electron-updater` to check that release feed
and download updates.

## Notes

- The app is unsigned by default. Windows SmartScreen may warn until a signing
  certificate is configured. The current unsigned CI build explicitly excludes
  `.exe` files from electron-builder signing via `win.signExts: ["!.exe"]`;
  remove that exclusion when a real Windows code-signing certificate is wired.
- The backend is bound to loopback only; do not change it to `0.0.0.0` for
  desktop packaging.
- Do not store custom skills in renderer `localStorage`; keep them in the
  backend folder store via `AICC_SKILLS_DIR`.
