import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";

const srcRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const ignoredTopLevelDirs = new Set(["game"]);
const targetExtensions = new Set([".ts", ".tsx"]);
const forbiddenPatterns = [
  {
    label: "frontend step invocation",
    pattern: /\bgame\.step\s*\(/,
  },
  {
    label: "frontend outcome invocation",
    pattern: /\bgame\.checkGameEnded\s*\(/,
  },
  {
    label: "frontend local simulation resume",
    pattern: /\bgame\.scenarioPaused\s*=\s*false\b/,
  },
];

function collectSourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const fullPath = join(dir, entry);
    const stat = statSync(fullPath);

    if (stat.isDirectory()) {
      if (dir === srcRoot && ignoredTopLevelDirs.has(entry)) return [];
      return collectSourceFiles(fullPath);
    }

    const extension = entry.endsWith(".tsx")
      ? ".tsx"
      : entry.endsWith(".ts")
        ? ".ts"
        : "";
    return targetExtensions.has(extension) ? [fullPath] : [];
  });
}

describe("backend runtime boundary", () => {
  test("UI code does not advance the frontend simulation engine", () => {
    const offenders = collectSourceFiles(srcRoot).flatMap((file) => {
      const content = readFileSync(file, "utf-8");
      return forbiddenPatterns
        .filter(({ pattern }) => pattern.test(content))
        .map(({ label }) => `${relative(srcRoot, file)}: ${label}`);
    });

    expect(offenders).toEqual([]);
  });

  test("legacy frontend engine tests are removed", () => {
    const legacyTestDir = join(srcRoot, "game", "test");
    const legacyTestFiles = existsSync(legacyTestDir)
      ? collectSourceFiles(legacyTestDir)
      : [];
    expect(legacyTestFiles).toEqual([]);
  });

  test("Game render adapter does not expose local simulation controls", () => {
    const gameSource = readFileSync(join(srcRoot, "game", "Game.ts"), "utf-8");

    expect(gameSource).not.toMatch(/\n\s+(?:async\s+)?step\s*\(/);
    expect(gameSource).not.toMatch(/\n\s+checkGameEnded\s*\(/);
    expect(gameSource).not.toMatch(/\n\s+updateGameState\s*\(/);
  });
});
