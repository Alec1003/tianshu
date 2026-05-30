import type {
  ScenarioCompareItem,
  ScenarioCompareReport,
  ScenarioCompareResponse,
  ScenarioCompareSession,
  TrainingScoreRecord,
  TrainingScoreResponse,
} from "@/api/types";

export type CompareScoreSource = "live" | string;

export interface ScenarioCompareSourceOption {
  id: CompareScoreSource;
  label: string;
}

export interface ScenarioCompareResolvedItem extends ScenarioCompareItem {
  activeScore: TrainingScoreResponse;
  activeScoreRecord: TrainingScoreRecord | null;
  latestScoreRecord: TrainingScoreRecord | null;
  scoreSourceId: CompareScoreSource;
  scoreSourceLabel: string;
  availableSources: ScenarioCompareSourceOption[];
  trendFromLatestRecord: number | null;
  liveScoreDelta: number | null;
}

export interface ScenarioCompareSnapshotItem {
  id: string;
  name: string;
  baseline: boolean;
  source: {
    id: CompareScoreSource;
    label: string;
    archived_record_id: string | null;
  };
  score: {
    overall_score: number;
    grade: string;
    confidence: string;
    generated_at: string;
  };
  score_deltas: {
    versus_baseline: number | null;
    versus_latest_archived: number | null;
    versus_live: number | null;
  };
  summary: {
    mission_count: number;
    unit_count: number;
    timeline_event_count: number;
    aar_count: number;
  };
}

export interface ScenarioCompareSnapshot {
  generated_at: string;
  baseline_id: string;
  baseline_name: string;
  items: ScenarioCompareSnapshotItem[];
}

export interface ScenarioCompareRestoreState {
  baselineId: string;
  selectedSources: Record<string, CompareScoreSource>;
}

function compactIso(iso?: string | null): string {
  if (!iso) return "未归档";
  const time = new Date(iso);
  if (Number.isNaN(time.getTime())) return "未归档";
  return time.toISOString().slice(0, 16).replace("T", " ");
}

function recordLabel(record: TrainingScoreRecord): string {
  return `${compactIso(record.created_at)} · ${record.overall_score} 分`;
}

export function scoreSourceOptions(
  records: TrainingScoreRecord[]
): ScenarioCompareSourceOption[] {
  return [
    { id: "live", label: "实时评分" },
    ...records.map((record) => ({
      id: record.id,
      label: `归档 ${recordLabel(record)}`,
    })),
  ];
}

export function resolveScenarioCompareItems(
  items: ScenarioCompareItem[],
  recordsByScenario: Record<string, TrainingScoreRecord[]>,
  selectedSources: Record<string, CompareScoreSource>
): ScenarioCompareResolvedItem[] {
  return items.map((item) => {
    const records = recordsByScenario[item.id] ?? [];
    const latestScoreRecord = records[0] ?? null;
    const selectedSourceId = selectedSources[item.id] ?? "live";
    const activeScoreRecord =
      selectedSourceId === "live"
        ? null
        : (records.find((record) => record.id === selectedSourceId) ?? null);
    const activeScore = activeScoreRecord?.score ?? item.training_score;
    const activeSourceId = activeScoreRecord?.id ?? "live";
    const latestScoreValue = latestScoreRecord?.score.overall_score ?? null;
    const liveScoreDelta =
      activeScoreRecord === null
        ? null
        : activeScore.overall_score - item.training_score.overall_score;

    return {
      ...item,
      activeScore,
      activeScoreRecord,
      latestScoreRecord,
      scoreSourceId: activeSourceId,
      scoreSourceLabel:
        activeScoreRecord === null
          ? "实时评分"
          : `归档 ${recordLabel(activeScoreRecord)}`,
      availableSources: scoreSourceOptions(records),
      trendFromLatestRecord:
        latestScoreValue === null
          ? null
          : activeScore.overall_score - latestScoreValue,
      liveScoreDelta,
    };
  });
}

export function buildScenarioCompareSnapshot(
  response: ScenarioCompareResponse,
  baselineId: string,
  items: ScenarioCompareResolvedItem[]
): ScenarioCompareSnapshot | null {
  const baseline =
    items.find((item) => item.id === baselineId) ?? items[0] ?? null;
  if (!baseline) return null;

  return {
    generated_at: response.generated_at,
    baseline_id: baseline.id,
    baseline_name: baseline.name,
    items: items.map((item) => ({
      id: item.id,
      name: item.name,
      baseline: item.id === baseline.id,
      source: {
        id: item.scoreSourceId,
        label: item.scoreSourceLabel,
        archived_record_id: item.activeScoreRecord?.id ?? null,
      },
      score: {
        overall_score: item.activeScore.overall_score,
        grade: item.activeScore.grade,
        confidence: item.activeScore.confidence,
        generated_at: item.activeScore.generated_at,
      },
      score_deltas: {
        versus_baseline:
          item.id === baseline.id
            ? null
            : item.activeScore.overall_score -
              baseline.activeScore.overall_score,
        versus_latest_archived: item.trendFromLatestRecord,
        versus_live: item.liveScoreDelta,
      },
      summary: {
        mission_count: item.mission_count,
        unit_count: item.unit_count,
        timeline_event_count: item.timeline_event_count,
        aar_count: item.aar_count,
      },
    })),
  };
}

export function buildScenarioCompareRestoreState(
  report: ScenarioCompareReport
): ScenarioCompareRestoreState {
  return {
    baselineId: report.baseline_scenario_id,
    selectedSources: Object.fromEntries(
      report.snapshot.items.map((item) => [
        item.id,
        item.source.archived_record_id ?? "live",
      ])
    ),
  };
}

export function buildScenarioCompareRestoreStateFromSession(
  compareSession: ScenarioCompareSession
): ScenarioCompareRestoreState {
  return {
    baselineId: compareSession.state.baseline_id,
    selectedSources: compareSession.state.selected_sources,
  };
}
