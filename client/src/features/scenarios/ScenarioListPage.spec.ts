import { describe, expect, it } from "vitest";

import type { ScenarioListItem } from "@/api/types";

import { projectMetrics } from "./scenarioMetrics";

function scenario(overrides: Partial<ScenarioListItem>): ScenarioListItem {
  return {
    id: "tpl-desert_storm_1991",
    name: "沙漠风暴",
    description: "",
    is_template: true,
    owner_id: null,
    version: 1,
    status: "draft",
    mission_count: 11,
    unit_count: 26,
    side_count: 2,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("projectMetrics", () => {
  it("uses backend scenario statistics instead of hash-derived placeholders", () => {
    expect(projectMetrics(scenario({}))).toEqual({
      tasks: 11,
      units: 26,
      sides: 2,
    });
  });

  it("never displays negative metrics from malformed API payloads", () => {
    expect(
      projectMetrics(
        scenario({
          mission_count: -1,
          unit_count: -22,
          side_count: -3,
        })
      )
    ).toEqual({
      tasks: 0,
      units: 0,
      sides: 0,
    });
  });
});
