import Scenario from "@/game/Scenario";

export function isHostileToCurrentSide(
  scenario: Scenario,
  sideId: string,
  currentSideId: string
) {
  if (!currentSideId || !sideId || sideId === currentSideId) return false;
  return scenario.isHostile(currentSideId, sideId);
}
