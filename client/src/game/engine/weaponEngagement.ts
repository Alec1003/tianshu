import { randomUUID } from "@/utils/generateUUID";
import { fromLonLat, get as getProjection } from "ol/proj";
import {
  DEFAULT_OL_PROJECTION_CODE,
  NAUTICAL_MILES_TO_METERS,
} from "@/utils/constants";
import Aircraft from "@/game/units/Aircraft";
import Facility from "@/game/units/Facility";
import { Circle } from "ol/geom";
import Scenario from "@/game/Scenario";
import Weapon from "@/game/units/Weapon";
import {
  getBearingBetweenTwoPoints,
  getDistanceBetweenTwoPoints,
  getNextCoordinates,
  getTerminalCoordinatesFromDistanceAndBearing,
  randomFloat,
  randomInt,
} from "@/utils/mapFunctions";
import Airbase from "@/game/units/Airbase";
import Ship from "@/game/units/Ship";
import SimulationLogs, { SimulationLogType } from "@/game/log/SimulationLogs";

export type Target = Aircraft | Facility | Weapon | Airbase | Ship;

const WEAPON_ENDGAME_DISTANCE_KM = 1;

// 击毁敌方单位的基础分值（攻方 Side.totalScore 累加）。
// 数值参考 wargame 习惯：高价值固定目标 > 舰艇 > 防空设施 > 飞机 > 武器拦截。
export const UNIT_SCORE_TABLE = {
  aircraft: 10,
  weapon: 1,
  facility: 30,
  ship: 50,
  airbase: 100,
} as const;

// 关键单位（isObjective）被毁的额外加分；同时会让 Game.checkGameEnded
// 立刻把对方判为胜方。
export const OBJECTIVE_BONUS_SCORE = 200;

// 在 weaponEndgame 命中后调用：给攻方加分，并在 isObjective 命中时记录事件
// 到 Scenario 上，由 Game 在 step 末尾统一读取并触发胜负判定。
export function onUnitDestroyed(
  currentScenario: Scenario,
  attackerSideId: string,
  target: Target
) {
  const attackerSide = currentScenario.getSide(attackerSideId);
  if (!attackerSide) return;

  let baseScore = 0;
  let unitType: "aircraft" | "weapon" | "facility" | "ship" | "airbase" =
    "weapon";
  if (target instanceof Aircraft) {
    baseScore = UNIT_SCORE_TABLE.aircraft;
    unitType = "aircraft";
  } else if (target instanceof Weapon) {
    baseScore = UNIT_SCORE_TABLE.weapon;
    unitType = "weapon";
  } else if (target instanceof Facility) {
    baseScore = UNIT_SCORE_TABLE.facility;
    unitType = "facility";
  } else if (target instanceof Ship) {
    baseScore = UNIT_SCORE_TABLE.ship;
    unitType = "ship";
  } else if (target instanceof Airbase) {
    baseScore = UNIT_SCORE_TABLE.airbase;
    unitType = "airbase";
  }

  const isObjective =
    !(target instanceof Weapon) && (target as { isObjective?: boolean }).isObjective === true;
  const totalScore = baseScore + (isObjective ? OBJECTIVE_BONUS_SCORE : 0);

  attackerSide.totalScore = (attackerSide.totalScore ?? 0) + totalScore;

  if (isObjective) {
    currentScenario.lastObjectiveDestroyed = {
      attackerSideId,
      victimSideId: (target as { sideId: string }).sideId,
      unitId: target.id,
      unitName: target.name,
      unitType,
      destroyedAt: currentScenario.currentTime,
    };
  }
}

export function isThreatDetected(
  threat: Aircraft | Weapon,
  detector: Facility | Ship | Aircraft
): boolean {
  const projection = getProjection(DEFAULT_OL_PROJECTION_CODE);
  const detectorRangeGeometry = new Circle(
    fromLonLat([detector.longitude, detector.latitude], projection!),
    detector.getDetectionRange() * NAUTICAL_MILES_TO_METERS
  );
  return detectorRangeGeometry.intersectsCoordinate(
    fromLonLat([threat.longitude, threat.latitude], projection!)
  );
}

export function weaponCanEngageTarget(target: Target, weapon: Weapon) {
  const weaponEngagementRangeNm = weapon.getEngagementRange();
  const distanceToTargetKm = getDistanceBetweenTwoPoints(
    weapon.latitude,
    weapon.longitude,
    target.latitude,
    target.longitude
  );
  const distanceToTargetNm =
    (distanceToTargetKm * 1000) / NAUTICAL_MILES_TO_METERS;
  return distanceToTargetNm <= weaponEngagementRangeNm;
}

export function checkTargetTrackedByCount(
  currentScenario: Scenario,
  target: Target
) {
  let count = 0;
  currentScenario.weapons.forEach((weapon) => {
    if (weapon.targetId === target.id) count += 1;
  });
  return count;
}

export function weaponEndgame(
  currentScenario: Scenario,
  weapon: Weapon,
  target: Target,
  simulationLogs: SimulationLogs
): boolean {
  currentScenario.weapons = currentScenario.weapons.filter(
    (currentScenarioWeapon) => currentScenarioWeapon.id !== weapon.id
  );
  if (randomFloat() <= weapon.lethality) {
    if (target instanceof Aircraft) {
      currentScenario.aircraft = currentScenario.aircraft.filter(
        (currentScenarioAircraft) => currentScenarioAircraft.id !== target.id
      );
    } else if (target instanceof Facility) {
      currentScenario.facilities = currentScenario.facilities.filter(
        (currentScenarioFacility) => currentScenarioFacility.id !== target.id
      );
    } else if (target instanceof Weapon) {
      currentScenario.weapons = currentScenario.weapons.filter(
        (currentScenarioWeapon) => currentScenarioWeapon.id !== target.id
      );
    } else if (target instanceof Airbase) {
      currentScenario.airbases = currentScenario.airbases.filter(
        (currentScenarioAirbase) => currentScenarioAirbase.id !== target.id
      );
    } else if (target instanceof Ship) {
      currentScenario.ships = currentScenario.ships.filter(
        (currentScenarioShip) => currentScenarioShip.id !== target.id
      );
    }
    onUnitDestroyed(currentScenario, weapon.sideId, target);
    simulationLogs.addLog(
      weapon.sideId,
      `${weapon.name} has hit and destroyed ${target.name}`,
      currentScenario.currentTime,
      SimulationLogType.WEAPON_HIT
    );
    return true;
  }
  simulationLogs.addLog(
    weapon.sideId,
    `${weapon.name} has missed ${target.name}`,
    currentScenario.currentTime,
    SimulationLogType.WEAPON_MISSED
  );
  return false;
}

export function launchWeapon(
  currentScenario: Scenario,
  origin: Aircraft | Facility | Ship,
  target: Target,
  launchedWeapon: Weapon,
  launchedWeaponQuantity: number,
  simulationLogs: SimulationLogs
) {
  if (
    origin.weapons.length === 0 ||
    launchedWeapon.currentQuantity < launchedWeaponQuantity
  )
    return;

  for (let i = 0; i < launchedWeaponQuantity; i++) {
    const nextWeaponCoordinates = getNextCoordinates(
      origin.latitude,
      origin.longitude,
      target.latitude,
      target.longitude,
      launchedWeapon.speed
    );
    const nextWeaponLatitude = nextWeaponCoordinates[0];
    const nextWeaponLongitude = nextWeaponCoordinates[1];
    const newWeapon = new Weapon({
      id: randomUUID(),
      name: `${launchedWeapon.name} #${randomInt(1000)}`,
      sideId: origin.sideId,
      className: launchedWeapon.className,
      latitude: nextWeaponLatitude,
      longitude: nextWeaponLongitude,
      altitude: launchedWeapon.altitude,
      heading: getBearingBetweenTwoPoints(
        nextWeaponLatitude,
        nextWeaponLongitude,
        target.latitude,
        target.longitude
      ),
      speed: launchedWeapon.speed,
      currentFuel: launchedWeapon.currentFuel,
      maxFuel: launchedWeapon.maxFuel,
      fuelRate: launchedWeapon.fuelRate,
      range: launchedWeapon.range,
      route: [[target.latitude, target.longitude]],
      sideColor: launchedWeapon.sideColor,
      targetId: target.id,
      lethality: launchedWeapon.lethality,
      maxQuantity: 1,
      currentQuantity: 1,
    });
    currentScenario.weapons.push(newWeapon);
  }
  launchedWeapon.currentQuantity -= launchedWeaponQuantity;
  simulationLogs.addLog(
    origin.sideId,
    `${origin.name} launched ${launchedWeaponQuantity}x ${launchedWeapon.name} at ${target.name}`,
    currentScenario.currentTime,
    SimulationLogType.WEAPON_LAUNCHED
  );
  if (launchedWeapon.currentQuantity < 1) {
    origin.weapons = origin.weapons.filter(
      (currentOriginWeapon) => currentOriginWeapon.id !== launchedWeapon.id
    );
    simulationLogs.addLog(
      origin.sideId,
      `${origin.name} has expended all stores of ${launchedWeapon.name}`,
      currentScenario.currentTime,
      SimulationLogType.WEAPON_EXPENDED
    );
  }
}

export function weaponEngagement(
  currentScenario: Scenario,
  weapon: Weapon,
  simulationLogs: SimulationLogs
) {
  if (!currentScenario.getWeapon(weapon.id)) return;

  const target =
    currentScenario.getAircraft(weapon.targetId) ??
    currentScenario.getFacility(weapon.targetId) ??
    currentScenario.getWeapon(weapon.targetId) ??
    currentScenario.getShip(weapon.targetId) ??
    currentScenario.getAirbase(weapon.targetId);
  if (target) {
    const weaponRoute = weapon.route;
    if (weaponRoute.length > 0) {
      const distanceToTargetKm = getDistanceBetweenTwoPoints(
        weapon.latitude,
        weapon.longitude,
        target.latitude,
        target.longitude
      );
      if (distanceToTargetKm <= WEAPON_ENDGAME_DISTANCE_KM) {
        weaponEndgame(currentScenario, weapon, target, simulationLogs);
        return;
      } else {
        const nextWeaponCoordinates = getNextCoordinates(
          weapon.latitude,
          weapon.longitude,
          target.latitude,
          target.longitude,
          weapon.speed
        );
        const nextWeaponLatitude = nextWeaponCoordinates[0];
        const nextWeaponLongitude = nextWeaponCoordinates[1];
        weapon.heading = getBearingBetweenTwoPoints(
          nextWeaponLatitude,
          nextWeaponLongitude,
          target.latitude,
          target.longitude
        );
        weapon.latitude = nextWeaponLatitude;
        weapon.longitude = nextWeaponLongitude;
        const remainingDistanceToTargetKm = getDistanceBetweenTwoPoints(
          weapon.latitude,
          weapon.longitude,
          target.latitude,
          target.longitude
        );
        if (remainingDistanceToTargetKm <= WEAPON_ENDGAME_DISTANCE_KM) {
          weaponEndgame(currentScenario, weapon, target, simulationLogs);
          return;
        }
      }
      weapon.currentFuel -= weapon.fuelRate / 3600;
      if (weapon.currentFuel <= 0) {
        currentScenario.weapons = currentScenario.weapons.filter(
          (currentScenarioWeapon) => currentScenarioWeapon.id !== weapon.id
        );
        simulationLogs.addLog(
          weapon.sideId,
          `${weapon.name} has run out of fuel and is no longer operational`,
          currentScenario.currentTime,
          SimulationLogType.WEAPON_CRASHED
        );
      }
    }
  } else {
    currentScenario.weapons = currentScenario.weapons.filter(
      (currentScenarioWeapon) => currentScenarioWeapon.id !== weapon.id
    );
    simulationLogs.addLog(
      weapon.sideId,
      `${weapon.name} has lost its target and is no longer operational`,
      currentScenario.currentTime,
      SimulationLogType.WEAPON_CRASHED
    );
  }
}

export function aircraftPursuit(currentScenario: Scenario, aircraft: Aircraft) {
  const target = currentScenario.getAircraft(aircraft.targetId);
  if (!target) {
    aircraft.targetId = "";
    return;
  }
  if (aircraft.weapons.length < 1) return;

  const TRAIL_DISTANCE_NM = 5;
  const trailKm = (TRAIL_DISTANCE_NM * NAUTICAL_MILES_TO_METERS) / 1000;
  const behindBearing = (target.heading + 180) % 360;
  const trailPosition = getTerminalCoordinatesFromDistanceAndBearing(
    target.latitude,
    target.longitude,
    trailKm,
    behindBearing
  );
  const trailLat = trailPosition[0];
  const trailLon = trailPosition[1];

  aircraft.route = [[trailLat, trailLon]];
  aircraft.heading = getBearingBetweenTwoPoints(
    aircraft.latitude,
    aircraft.longitude,
    trailLat,
    trailLon
  );
}

export function routeAircraftToStrikePosition(
  currentScenario: Scenario,
  aircraft: Aircraft,
  targetId: string,
  strikeRadiusNm: number
) {
  const target =
    currentScenario.getFacility(targetId) ||
    currentScenario.getShip(targetId) ||
    currentScenario.getAirbase(targetId) ||
    currentScenario.getAircraft(targetId);
  if (!target) return;
  if (aircraft.weapons.length < 1) return;

  const bearingBetweenAircraftAndTarget = getBearingBetweenTwoPoints(
    aircraft.latitude,
    aircraft.longitude,
    target.latitude,
    target.longitude
  );
  const bearingBetweenTargetAndAircraft = getBearingBetweenTwoPoints(
    target.latitude,
    target.longitude,
    aircraft.latitude,
    aircraft.longitude
  );
  const strikeLocation = getTerminalCoordinatesFromDistanceAndBearing(
    target.latitude,
    target.longitude,
    (strikeRadiusNm * NAUTICAL_MILES_TO_METERS) / 1000,
    bearingBetweenTargetAndAircraft
  );

  aircraft.route.push([strikeLocation[0], strikeLocation[1]]);
  aircraft.heading = bearingBetweenAircraftAndTarget;
}
