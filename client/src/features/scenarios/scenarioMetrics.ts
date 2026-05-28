import type { ScenarioListItem } from "@/api/types";

export function projectMetrics(item: ScenarioListItem) {
  return {
    tasks: Math.max(0, item.mission_count ?? 0),
    units: Math.max(0, item.unit_count ?? 0),
    sides: Math.max(0, item.side_count ?? 0),
  };
}
