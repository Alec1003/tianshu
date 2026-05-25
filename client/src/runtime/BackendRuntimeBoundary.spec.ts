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
  {
    label: "frontend aircraft attack invocation",
    pattern: /\bgame\.handleAircraftAttack\s*\(/,
  },
  {
    label: "frontend ship attack invocation",
    pattern: /\bgame\.handleShipAttack\s*\(/,
  },
  {
    label: "frontend local mission mutation",
    pattern:
      /\bgame\.(?:createPatrolMission|createStrikeMission|updatePatrolMission|updateStrikeMission|deleteMission)\s*\(/,
  },
  {
    label: "frontend local unit add/delete mutation",
    pattern:
      /\bgame\.(?:addAircraft|addShip|addFacility|addAirbase|addReferencePoint|removeAircraft|removeShip|removeFacility|removeAirbase|removeReferencePoint)\s*\(/,
  },
  {
    label: "frontend local route commit",
    pattern: /\bgame\.commitRoute\s*\(/,
  },
  {
    label: "frontend local weapon mutation",
    pattern:
      /\bs\.(?:addWeaponToAircraft|addWeaponToShip|addWeaponToFacility|deleteWeaponFromAircraft|deleteWeaponFromShip|deleteWeaponFromFacility|updateAircraftWeaponQuantity|updateShipWeaponQuantity|updateFacilityWeaponQuantity)\s*\(/,
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

  test("legacy local-engine map views are removed", () => {
    expect(existsSync(join(srcRoot, "gui", "map", "ScenarioMap.tsx"))).toBe(
      false
    );
    expect(
      existsSync(join(srcRoot, "gui", "map", "OpenLayersScenarioMap.tsx"))
    ).toBe(false);
  });

  test("frontend weapon engagement engine is removed", () => {
    expect(
      existsSync(join(srcRoot, "game", "engine", "weaponEngagement.ts"))
    ).toBe(false);
  });

  test("Game render adapter does not expose local simulation controls", () => {
    const gameSource = readFileSync(join(srcRoot, "game", "Game.ts"), "utf-8");

    expect(gameSource).not.toMatch(/\n\s+(?:async\s+)?step\s*\(/);
    expect(gameSource).not.toMatch(/\n\s+checkGameEnded\s*\(/);
    expect(gameSource).not.toMatch(/\n\s+updateGameState\s*\(/);
    expect(gameSource).not.toMatch(/\n\s+handleAircraftAttack\s*\(/);
    expect(gameSource).not.toMatch(/\n\s+handleShipAttack\s*\(/);
    expect(gameSource).not.toContain("launchWeapon");
    expect(gameSource).not.toContain("weaponCanEngageTarget");
  });
});
