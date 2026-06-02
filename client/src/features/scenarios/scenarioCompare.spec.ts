import { describe, expect, it } from "vitest";

import type {
  ScenarioCompareItem,
  ScenarioCompareReport,
  ScenarioCompareResponse,
  ScenarioCompareSession,
  TrainingScoreRecord,
} from "@/api/types";

import {
  buildScenarioCompareSnapshot,
  buildScenarioCompareRestoreState,
  buildScenarioCompareRestoreStateFromSession,
  resolveScenarioCompareItems,
} from "./scenarioCompare";

function compareItem(
  overrides: Partial<ScenarioCompareItem>
): ScenarioCompareItem {
  return {
    id: "scenario-1",
    name: "方案一",
    description: "",
    is_template: false,
    owner_id: "user-1",
    version: 3,
    status: "draft",
    branch_meta: null,
    mission_count: 8,
    unit_count: 14,
    side_count: 2,
    created_at: "2026-05-30T10:00:00Z",
    updated_at: "2026-05-30T10:00:00Z",
    training_score: {
      scenario_id: "scenario-1",
      runtime_scenario_id: "runtime-1",
      generated_at: "2026-05-30T10:00:00Z",
      overall_score: 81,
      grade: "A-",
      confidence: "high",
      dimensions: [],
      metrics: {},
      strengths: ["节奏好"],
      improvements: ["补给偏紧"],
    },
    timeline_event_count: 24,
    latest_event_at: "2026-05-30T10:05:00Z",
    aar_count: 2,
    latest_aar_at: "2026-05-30T10:06:00Z",
    ...overrides,
  };
}

function scoreRecord(
  overrides: Partial<TrainingScoreRecord>
): TrainingScoreRecord {
  return {
    id: "record-1",
    scenario_id: "scenario-1",
    owner_id: "user-1",
    runtime_scenario_id: "runtime-1",
    aar_record_id: null,
    overall_score: 76,
    grade: "B+",
    confidence: "medium",
    score: {
      scenario_id: "scenario-1",
      runtime_scenario_id: "runtime-1",
      generated_at: "2026-05-29T08:00:00Z",
      overall_score: 76,
      grade: "B+",
      confidence: "medium",
      dimensions: [],
      metrics: {},
      strengths: ["存活率高"],
      improvements: ["协同不足"],
    },
    metrics: {},
    created_at: "2026-05-29T08:00:00Z",
    ...overrides,
  };
}

describe("scenarioCompare", () => {
  it("falls back to live score when no archived source is selected", () => {
    const items = resolveScenarioCompareItems([compareItem({})], {}, {});

    expect(items[0].activeScore.overall_score).toBe(81);
    expect(items[0].scoreSourceId).toBe("live");
    expect(items[0].availableSources).toHaveLength(1);
  });

  it("switches to archived record when a history source is selected", () => {
    const archived = scoreRecord({});
    const items = resolveScenarioCompareItems(
      [compareItem({})],
      { "scenario-1": [archived] },
      { "scenario-1": archived.id }
    );

    expect(items[0].activeScore.overall_score).toBe(76);
    expect(items[0].activeScoreRecord?.id).toBe("record-1");
    expect(items[0].liveScoreDelta).toBe(-5);
    expect(items[0].availableSources).toHaveLength(2);
  });

  it("builds a compare snapshot from resolved items", () => {
    const item1 = compareItem({});
    const item2 = compareItem({
      id: "scenario-2",
      name: "方案二",
      training_score: {
        ...compareItem({}).training_score,
        scenario_id: "scenario-2",
        overall_score: 88,
        grade: "A",
      },
    });
    const response: ScenarioCompareResponse = {
      baseline_id: "scenario-1",
      generated_at: "2026-05-30T10:10:00Z",
      items: [item1, item2],
    };

    const resolved = resolveScenarioCompareItems(response.items, {}, {});
    const snapshot = buildScenarioCompareSnapshot(
      response,
      "scenario-1",
      resolved
    );

    expect(snapshot?.baseline_id).toBe("scenario-1");
    expect(snapshot?.items).toHaveLength(2);
    expect(snapshot?.items[1].score_deltas.versus_baseline).toBe(7);
    expect(snapshot?.items[1].source.id).toBe("live");
  });

  it("restores baseline and score sources from a saved report", () => {
    const report: ScenarioCompareReport = {
      id: "report-1",
      owner_id: "user-1",
      title: "saved report",
      baseline_scenario_id: "scenario-1",
      scenario_ids: ["scenario-1", "scenario-2"],
      created_at: "2026-05-30T10:15:00Z",
      snapshot: {
        generated_at: "2026-05-30T10:10:00Z",
        baseline_id: "scenario-1",
        baseline_name: "方案一",
        items: [
          {
            id: "scenario-1",
            name: "方案一",
            baseline: true,
            source: {
              id: "live",
              label: "实时评分",
              archived_record_id: null,
            },
            score: {
              overall_score: 81,
              grade: "A-",
              confidence: "high",
              generated_at: "2026-05-30T10:00:00Z",
            },
            score_deltas: {
              versus_baseline: null,
              versus_latest_archived: null,
              versus_live: null,
            },
            summary: {
              mission_count: 8,
              unit_count: 14,
              timeline_event_count: 24,
              aar_count: 2,
            },
          },
          {
            id: "scenario-2",
            name: "方案二",
            baseline: false,
            source: {
              id: "record-2",
              label: "归档 2026-05-29 08:00 / 76 分",
              archived_record_id: "record-2",
            },
            score: {
              overall_score: 76,
              grade: "B+",
              confidence: "medium",
              generated_at: "2026-05-29T08:00:00Z",
            },
            score_deltas: {
              versus_baseline: -5,
              versus_latest_archived: 0,
              versus_live: -5,
            },
            summary: {
              mission_count: 6,
              unit_count: 12,
              timeline_event_count: 18,
              aar_count: 1,
            },
          },
        ],
      },
    };

    const restored = buildScenarioCompareRestoreState(report);

    expect(restored.baselineId).toBe("scenario-1");
    expect(restored.selectedSources).toEqual({
      "scenario-1": "live",
      "scenario-2": "record-2",
    });
  });

  it("restores baseline and score sources from a saved compare session", () => {
    const compareSession: ScenarioCompareSession = {
      id: "session-1",
      owner_id: "user-1",
      title: "session",
      source_scenario_id: "scenario-1",
      baseline_scenario_id: "scenario-1",
      scenario_ids: ["scenario-1", "scenario-2"],
      state: {
        baseline_id: "scenario-2",
        selected_sources: {
          "scenario-1": "live",
          "scenario-2": "record-9",
        },
        plan_summaries: {},
      },
      created_at: "2026-05-30T10:15:00Z",
      updated_at: "2026-05-30T10:20:00Z",
    };

    const restored =
      buildScenarioCompareRestoreStateFromSession(compareSession);

    expect(restored.baselineId).toBe("scenario-2");
    expect(restored.selectedSources).toEqual({
      "scenario-1": "live",
      "scenario-2": "record-9",
    });
  });
});
