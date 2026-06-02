const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");

const requiredFiles = [
  "client/dist/index.html",
  "server/app/main.py",
  "server/app/platform/paths.py",
  "gym/blade/Game.py",
  "client/src/scenarios/SCS.json"
];

const pythonCandidates = [
  ".python312/python.exe",
  ".python312/Scripts/python.exe",
  ".python312/bin/python"
];

const missing = requiredFiles.filter(
  (relativePath) => !fs.existsSync(path.join(root, relativePath))
);

if (!pythonCandidates.some((relativePath) => fs.existsSync(path.join(root, relativePath)))) {
  missing.push(`one of: ${pythonCandidates.join(", ")}`);
}

if (missing.length > 0) {
  console.error("Electron package resources are missing:");
  for (const item of missing) {
    console.error(`- ${item}`);
  }
  console.error("");
  console.error("Run `npm run build:client` and make sure .python312 exists before packaging.");
  process.exit(1);
}

console.log("Electron package resources OK.");
