import Scenario from "@/game/Scenario";
import Aircraft from "@/game/units/Aircraft";
import Airbase from "@/game/units/Airbase";
import Facility from "@/game/units/Facility";
import ReferencePoint from "@/game/units/ReferencePoint";
import Ship from "@/game/units/Ship";
import Weapon from "@/game/units/Weapon";
import { NAUTICAL_MILES_TO_METERS } from "@/utils/constants";
import { getDistanceBetweenTwoPoints } from "@/utils/mapFunctions";

export interface ScenarioVisibility {
  godMode: boolean;
  currentSideId: string;
  includeDetectedHostiles?: boolean;
}

export type ScenarioMapObject = ScenarioMapUnit | Weapon;

export type ScenarioMapUnit =
  | Aircraft
  | Ship
  | Facility
  | Airbase
  | ReferencePoint;

type SensorPlatform = Aircraft | Ship | Facility;

function isSensorPlatform(unit: ScenarioMapObject): unit is SensorPlatform {
  return typeof (unit as SensorPlatform).getDetectionRange === "function";
}

export function isHostileToCurrentSide(
  scenario: Scenario,
  sideId: string,
  currentSideId: string
) {
  if (!currentSideId || !sideId || sideId === currentSideId) return false;
  return scenario.isHostile(currentSideId, sideId);
}

function getFriendlySensors(
  scenario: Scenario,
  currentSideId: string
): SensorPlatform[] {
  const sensors: SensorPlatform[] = [
    ...scenario.aircraft,
    ...scenario.ships,
    ...scenario.facilities,
  ];

  return sensors.filter(
    (sensor) => !isHostileToCurrentSide(scenario, sensor.sideId, currentSideId)
  );
}

export function isDetectedByFriendlySensors(
  scenario: Scenario,
  object: ScenarioMapObject,
  currentSideId: string
) {
  if (!currentSideId) return true;

  return getFriendlySensors(scenario, currentSideId).some((sensor) => {
    const detectionRangeNm = sensor.getDetectionRange();
    if (!detectionRangeNm || detectionRangeNm <= 0) return false;

    const distanceKm = getDistanceBetweenTwoPoints(
      sensor.latitude,
      sensor.longitude,
      object.latitude,
      object.longitude
    );
    const distanceNm = (distanceKm * 1000) / NAUTICAL_MILES_TO_METERS;

    return distanceNm <= detectionRangeNm;
  });
}

export function isScenarioObjectVisible(
  scenario: Scenario,
  object: ScenarioMapObject,
  visibility: ScenarioVisibility
) {
  if (visibility.godMode || !visibility.currentSideId) return true;

  const hostile = isHostileToCurrentSide(
    scenario,
    object.sideId,
    visibility.currentSideId
  );
  if (!hostile) return true;

  return visibility.includeDetectedHostiles !== false
    ? isDetectedByFriendlySensors(scenario, object, visibility.currentSideId)
    : false;
}

export function isOperationalDetailVisible(
  scenario: Scenario,
  object: ScenarioMapObject,
  visibility: ScenarioVisibility
) {
  if (visibility.godMode || !visibility.currentSideId) return true;

  return !isHostileToCurrentSide(
    scenario,
    object.sideId,
    visibility.currentSideId
  );
}

export function hasSensorRange(object: ScenarioMapObject) {
  return isSensorPlatform(object) && object.getDetectionRange() > 0;
}
