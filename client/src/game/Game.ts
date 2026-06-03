import { randomUUID } from "@/utils/generateUUID";
import Aircraft from "@/game/units/Aircraft";
import Facility from "@/game/units/Facility";
import Scenario from "@/game/Scenario";

import {
  getBearingBetweenTwoPoints,
  getDistanceBetweenTwoPoints,
  randomInt,
} from "@/utils/mapFunctions";
import Airbase from "@/game/units/Airbase";
import Side from "@/game/Side";
import Weapon from "@/game/units/Weapon";
import {
  GAME_SPEED_DELAY_MS,
  NAUTICAL_MILES_TO_METERS,
} from "@/utils/constants";
import Ship from "@/game/units/Ship";
import Obstacle from "@/game/units/Obstacle";
import ReferencePoint from "@/game/units/ReferencePoint";
import PatrolMission from "@/game/mission/PatrolMission";
import StrikeMission from "@/game/mission/StrikeMission";
import PlaybackRecorder from "@/game/playback/PlaybackRecorder";
import RecordingPlayer from "@/game/playback/RecordingPlayer";
import { SIDE_COLOR } from "@/utils/colors";
import Relationships from "@/game/Relationships";
import Dba from "@/game/db/Dba";
import SimulationLogs, { SimulationLogType } from "@/game/log/SimulationLogs";
import { SideDoctrine } from "@/game/Doctrine";

const MAX_HISTORY_SIZE = 20;

// 胜负判定原因：
// - KEY_UNIT_DESTROYED：某关键单位（isObjective=true）被击毁，对方立即胜（唯一“决胜”条件）。
// - TIMEOUT：达到 scenario.duration 上限 → 按总分裁定胜方。
// 空字符串表示尚未结束（gameOutcome.ended=false）。
// 备注：一方作战单位归零本身不再触发胜负，推演继续直到关键单位被毁或超时。
export type GameOutcomeReason = "" | "KEY_UNIT_DESTROYED" | "TIMEOUT";

export interface GameOutcome {
  ended: boolean;
  winnerSideId: string;
  reason: GameOutcomeReason;
  endedAt: number; // scenario.currentTime when game ended (unix seconds)
}

const createInitialGameOutcome = (): GameOutcome => ({
  ended: false,
  winnerSideId: "",
  reason: "",
  endedAt: 0,
});
const DEFAULT_AIRCRAFT_WEAPON_KEYS: Record<string, number> = {
  "AIM-120 AMRAAM": 4,
  "AIM-9 Sidewinder": 2,
  "AGM-65 Maverick": 2,
};
const LEGACY_AIRCRAFT_WEAPON_KEYS: Record<string, number> = {
  ...DEFAULT_AIRCRAFT_WEAPON_KEYS,
  "AGM-158 JASSM": 2,
};
const DEFAULT_FACILITY_WEAPON_KEYS: Record<string, number> = {
  "48N6 (S-400 Triumf)": 8,
  "9M96 (S-300V4)": 12,
  "57E6E (Pantsir-S1)": 16,
};
const DEFAULT_SHIP_WEAPON_KEYS: Record<string, number> = {
  "RIM-174 Standard SM-6": 96,
  "RIM-116 RAM": 42,
  "RGM-84 Harpoon": 8,
};

interface IMapView {
  defaultCenter: number[];
  currentCameraCenter: number[];
  defaultZoom: number;
  currentCameraZoom: number;
}

interface IAttackParams {
  autoAttack: boolean;
  currentAttackerId: string;
  currentWeaponId: string;
  currentWeaponQuantity: number;
}

export type Mission = PatrolMission | StrikeMission;

export default class Game {
  mapView: IMapView = {
    defaultCenter: [0, 0],
    currentCameraCenter: [0, 0],
    defaultZoom: 0,
    currentCameraZoom: 0,
  };
  currentScenario: Scenario;
  currentSideId: string = "";
  scenarioPaused: boolean = true;
  recordingScenario: boolean = false;
  playbackRecorder: PlaybackRecorder = new PlaybackRecorder(10);
  recordingPlayer: RecordingPlayer = new RecordingPlayer();
  addingAircraft: boolean = false;
  addingAirbase: boolean = false;
  addingFacility: boolean = false;
  addingReferencePoint: boolean = false;
  addingShip: boolean = false;
  selectingTarget: boolean = false;
  currentAttackParams: IAttackParams = {
    autoAttack: false,
    currentAttackerId: "",
    currentWeaponId: "",
    currentWeaponQuantity: 0,
  };
  selectedUnitId: string = "";
  selectedUnitClassName: string | null = null;
  numberOfWaypoints: number = 50;
  godMode: boolean = true;
  eraserMode: boolean = false;
  history: string[] = [];
  unitDba: Dba = new Dba();
  demoMode: boolean = true; // flag for features that should be removed in the final product
  simulationLogs: SimulationLogs = new SimulationLogs();
  // 当前推演的胜负状态；由 checkGameEnded 在每个 step 末尾写入，UI 层据此弹
  // AAR 弹窗。loadScenario 时会被重置。
  gameOutcome: GameOutcome = createInitialGameOutcome();

  constructor(currentScenario: Scenario) {
    this.currentScenario = currentScenario;
  }

  getStableWeaponTemplate(
    seed: string,
    candidateClassNames?: string[],
    minimumRange?: number
  ) {
    const candidateWeaponDb =
      candidateClassNames && candidateClassNames.length > 0
        ? this.unitDba
            .getWeaponDb()
            .filter((weapon) => candidateClassNames.includes(weapon.className))
        : this.unitDba.getWeaponDb();
    const rangeFilteredWeaponDb =
      minimumRange != null
        ? candidateWeaponDb.filter(
            (weapon) => weapon.range >= minimumRange * 0.9
          )
        : candidateWeaponDb;
    const weaponDb =
      rangeFilteredWeaponDb.length > 0
        ? rangeFilteredWeaponDb
        : candidateWeaponDb;
    if (weaponDb.length === 0) return;
    let hash = 0;
    for (let i = 0; i < seed.length; i += 1) {
      hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
    }
    return weaponDb[hash % weaponDb.length];
  }

  getLoadedWeaponTemplate(weapon: Weapon, candidateClassNames?: string[]) {
    if (
      weapon.name === "Sample Weapon" ||
      weapon.className === "Sample Weapon"
    ) {
      return this.getStableWeaponTemplate(
        weapon.id || weapon.name || weapon.className,
        candidateClassNames,
        weapon.range
      );
    }
    return this.unitDba
      .getWeaponDb()
      .find((template) => template.className === weapon.className);
  }

  createLoadedWeapon(weapon: Weapon, candidateClassNames?: string[]): Weapon {
    const isLegacySample =
      weapon.name === "Sample Weapon" || weapon.className === "Sample Weapon";
    const template = this.getLoadedWeaponTemplate(weapon, candidateClassNames);
    const className = template?.className ?? weapon.className;
    const maxFuel = template?.maxFuel ?? weapon.maxFuel ?? 0;
    const maxQuantity = weapon.maxQuantity ?? 1;
    const currentQuantity = Math.max(
      0,
      Math.min(maxQuantity, weapon.currentQuantity ?? maxQuantity)
    );
    const legacySuffix = /^Sample Weapon\s*(#.+)?$/.exec(weapon.name)?.[1];
    const loadedTargetTypes = (weapon as unknown as { target_types?: string[] })
      .target_types;

    return new Weapon({
      id: weapon.id,
      name: isLegacySample
        ? `${className}${legacySuffix ? ` ${legacySuffix}` : ""}`
        : weapon.name,
      sideId: weapon.sideId,
      className,
      latitude: weapon.latitude,
      longitude: weapon.longitude,
      altitude: weapon.altitude,
      heading: weapon.heading,
      speed: template?.speed ?? weapon.speed ?? 0,
      currentFuel: Math.max(
        0,
        Math.min(weapon.currentFuel ?? maxFuel, maxFuel)
      ),
      maxFuel,
      fuelRate: template?.fuelRate ?? weapon.fuelRate ?? 0,
      range: template?.range ?? weapon.range ?? 100,
      route: weapon.route,
      targetId: weapon.targetId,
      lethality: template?.lethality ?? weapon.lethality ?? 0,
      maxQuantity,
      currentQuantity,
      sideColor: weapon.sideColor,
      targetTypes: template?.targetTypes ?? weapon.targetTypes ?? loadedTargetTypes,
    });
  }

  addSide(
    sideName: string,
    sideColor: SIDE_COLOR,
    sideHostiles: string[],
    sideAllies: string[],
    sideDoctrine: SideDoctrine
  ) {
    this.recordHistory();
    const side = new Side({
      id: randomUUID(),
      name: sideName,
      color: sideColor,
    });
    this.currentScenario.sides.push(side);
    this.currentScenario.relationships.updateRelationship(
      side.id,
      sideHostiles,
      sideAllies
    );
    this.currentScenario.updateSideDoctrine(side.id, sideDoctrine);
  }

  updateSide(
    sideId: string,
    sideName: string,
    sideColor: SIDE_COLOR,
    sideHostiles: string[],
    sideAllies: string[],
    sideDoctrine: SideDoctrine
  ) {
    const side = this.currentScenario.getSide(sideId);
    if (side) {
      this.recordHistory();
      side.name = sideName;
      side.color = sideColor;
      this.currentScenario.airbases.forEach((airbase) => {
        if (airbase.sideId === sideId) {
          airbase.sideColor = sideColor;
          airbase.aircraft.forEach((aircraft) => {
            aircraft.sideColor = sideColor;
            aircraft.weapons.forEach((weapon) => {
              weapon.sideColor = sideColor;
            });
          });
        }
      });
      this.currentScenario.ships.forEach((ship) => {
        if (ship.sideId === sideId) {
          ship.sideColor = sideColor;
          ship.aircraft.forEach((aircraft) => {
            aircraft.sideColor = sideColor;
            aircraft.weapons.forEach((weapon) => {
              weapon.sideColor = sideColor;
            });
          });
          ship.weapons.forEach((weapon) => {
            weapon.sideColor = sideColor;
          });
        }
      });
      this.currentScenario.facilities.forEach((facility) => {
        if (facility.sideId === sideId) {
          facility.sideColor = sideColor;
          facility.weapons.forEach((weapon) => {
            weapon.sideColor = sideColor;
          });
        }
      });
      this.currentScenario.aircraft.forEach((aircraft) => {
        if (aircraft.sideId === sideId) {
          aircraft.sideColor = sideColor;
          aircraft.weapons.forEach((weapon) => {
            weapon.sideColor = sideColor;
          });
        }
      });
      this.currentScenario.weapons.forEach((weapon) => {
        if (weapon.sideId === sideId) {
          weapon.sideColor = sideColor;
        }
      });
      this.currentScenario.referencePoints.forEach((referencePoint) => {
        if (referencePoint.sideId === sideId) {
          referencePoint.sideColor = sideColor;
        }
      });
      this.currentScenario.missions.forEach((mission) => {
        if (mission instanceof PatrolMission) {
          mission.assignedArea.forEach((point) => {
            if (point.sideId === sideId) {
              point.sideColor = sideColor;
            }
          });
        }
      });
      this.currentScenario.relationships.updateRelationship(
        sideId,
        sideHostiles,
        sideAllies
      );
      this.currentScenario.updateSideDoctrine(side.id, sideDoctrine);
    }
  }

  deleteSide(sideId: string) {
    this.recordHistory();
    this.currentScenario.sides = this.currentScenario.sides.filter(
      (side) => side.id !== sideId
    );
    this.currentScenario.aircraft = this.currentScenario.aircraft.filter(
      (aircraft) => aircraft.sideId !== sideId
    );
    this.currentScenario.airbases = this.currentScenario.airbases.filter(
      (airbase) => airbase.sideId !== sideId
    );
    this.currentScenario.facilities = this.currentScenario.facilities.filter(
      (facility) => facility.sideId !== sideId
    );
    this.currentScenario.ships = this.currentScenario.ships.filter(
      (ship) => ship.sideId !== sideId
    );
    this.currentScenario.missions = this.currentScenario.missions.filter(
      (mission) => mission.sideId !== sideId
    );
    this.currentScenario.weapons = this.currentScenario.weapons.filter(
      (weapon) => weapon.sideId !== sideId
    );
    this.currentScenario.referencePoints =
      this.currentScenario.referencePoints.filter(
        (referencePoint) => referencePoint.sideId !== sideId
      );
    this.currentScenario.relationships.deleteSide(sideId);
    this.currentScenario.removeSideDoctrine(sideId);
    if (this.currentSideId === sideId) {
      this.currentSideId = this.currentScenario.sides[0]?.id ?? "";
    }
  }

  getDefaultWeapons(
    weaponKeys: Record<string, number>,
    sideId: string,
    sideColor: SIDE_COLOR
  ): Weapon[] {
    const weapons: Weapon[] = [];
    const weaponTemplates = this.unitDba
      .getWeaponDb()
      .filter((weapon) => weapon.className in weaponKeys);
    weaponTemplates.forEach((weapon) => {
      const weaponQuantity = weaponKeys[weapon.className];
      const newWeapon = new Weapon({
        id: randomUUID(),
        name: weapon.className,
        sideId: sideId,
        className: weapon.className,
        latitude: 0.0,
        longitude: 0.0,
        altitude: 10000.0,
        heading: 90.0,
        speed: weapon.speed,
        currentFuel: weapon.maxFuel,
        maxFuel: weapon.maxFuel,
        fuelRate: weapon.fuelRate,
        range: weapon.range,
        sideColor: sideColor,
        targetId: null,
        lethality: weapon.lethality,
        maxQuantity: weaponQuantity,
        currentQuantity: weaponQuantity,
        targetTypes: weapon.targetTypes,
      });
      weapons.push(newWeapon);
    });

    return weapons;
  }

  getDefaultAircraftWeapons(sideId: string, sideColor: SIDE_COLOR): Weapon[] {
    return this.getDefaultWeapons(
      DEFAULT_AIRCRAFT_WEAPON_KEYS,
      sideId,
      sideColor
    );
  }

  getDefaultFacilityWeapons(sideId: string, sideColor: SIDE_COLOR): Weapon[] {
    return this.getDefaultWeapons(
      DEFAULT_FACILITY_WEAPON_KEYS,
      sideId,
      sideColor
    );
  }

  getDefaultShipWeapons(sideId: string, sideColor: SIDE_COLOR): Weapon[] {
    return this.getDefaultWeapons(DEFAULT_SHIP_WEAPON_KEYS, sideId, sideColor);
  }

  addAircraft(
    aircraftName: string,
    className: string,
    latitude: number,
    longitude: number,
    speed?: number,
    maxFuel?: number,
    fuelRate?: number,
    range?: number,
    isTanker?: boolean,
    fuelOffloadCapacity?: number,
    fuelTransferRate?: number,
    refuelRange?: number,
    isElectronicWarfare?: boolean,
    jammingRange?: number,
    jammingStrength?: number,
    jammingModes?: string[],
    communicationDisruption?: number
  ): Aircraft | undefined {
    if (!this.currentSideId) {
      return;
    }
    this.recordHistory();
    const aircraft = new Aircraft({
      id: randomUUID(),
      name: aircraftName,
      sideId: this.currentSideId,
      className: className,
      latitude: latitude,
      longitude: longitude,
      altitude: 10000.0,
      heading: 90.0,
      speed: speed ?? 300.0,
      currentFuel: maxFuel ?? 10000.0,
      maxFuel: maxFuel ?? 10000.0,
      fuelRate: fuelRate ?? 5000.0,
      range: range ?? 100,
      sideColor: this.currentScenario.getSideColor(this.currentSideId),
      weapons:
        !isTanker && this.demoMode
          ? this.getDefaultAircraftWeapons(
              this.currentSideId,
              this.currentScenario.getSideColor(this.currentSideId)
            )
          : [],
      homeBaseId: "",
      rtb: false,
      targetId: "",
      isTanker,
      fuelOffloadCapacity: fuelOffloadCapacity ?? 0,
      fuelTransferRate: fuelTransferRate ?? 0,
      refuelRange: refuelRange ?? 0,
      isElectronicWarfare,
      jammingRange: jammingRange ?? 0,
      jammingStrength: jammingStrength ?? 0,
      jammingModes: jammingModes ?? [],
      communicationDisruption: communicationDisruption ?? 0,
    });
    this.currentScenario.aircraft.push(aircraft);
    return aircraft;
  }

  addAircraftToAirbase(
    airbaseId: string,
    className: string,
    speed?: number,
    maxFuel?: number,
    fuelRate?: number,
    range?: number,
    isTanker?: boolean,
    fuelOffloadCapacity?: number,
    fuelTransferRate?: number,
    refuelRange?: number,
    isElectronicWarfare?: boolean,
    jammingRange?: number,
    jammingStrength?: number,
    jammingModes?: string[],
    communicationDisruption?: number
  ) {
    let airbaseAircraft: Aircraft[] = [];
    if (!this.currentSideId) {
      return airbaseAircraft;
    }
    const airbase = this.currentScenario.getAirbase(airbaseId);
    if (airbase) {
      this.recordHistory();
      airbaseAircraft = airbase.aircraft;
      if (!(className && speed && maxFuel && fuelRate && range))
        return airbaseAircraft;
      const aircraft = new Aircraft({
        id: randomUUID(),
        name: `${className} #${randomInt(0, 1000)}`,
        sideId: airbase.sideId,
        className: className,
        latitude: airbase.latitude - 0.5,
        longitude: airbase.longitude - 0.5,
        altitude: 10000.0,
        heading: 90.0,
        speed: speed,
        currentFuel: maxFuel,
        maxFuel: maxFuel,
        fuelRate: fuelRate,
        range: range,
        weapons:
          !isTanker && this.demoMode
            ? this.getDefaultAircraftWeapons(
                this.currentSideId,
                this.currentScenario.getSideColor(this.currentSideId)
              )
            : [],
        homeBaseId: airbase.id,
        rtb: false,
        sideColor: airbase.sideColor,
        isTanker,
        fuelOffloadCapacity: fuelOffloadCapacity ?? 0,
        fuelTransferRate: fuelTransferRate ?? 0,
        refuelRange: refuelRange ?? 0,
        isElectronicWarfare,
        jammingRange: jammingRange ?? 0,
        jammingStrength: jammingStrength ?? 0,
        jammingModes: jammingModes ?? [],
        communicationDisruption: communicationDisruption ?? 0,
      });
      airbase.aircraft.push(aircraft);
    }
    return airbaseAircraft;
  }

  removeAircraftFromAirbase(
    airbaseId: string,
    aircraftIds: string[]
  ): Aircraft[] {
    let airbaseAircraft: Aircraft[] = [];
    if (!this.currentSideId) {
      return airbaseAircraft;
    }
    this.recordHistory();
    const airbase = this.currentScenario.getAirbase(airbaseId);
    if (airbase) {
      airbase.aircraft = airbase.aircraft.filter(
        (aircraft) => !aircraftIds.includes(aircraft.id)
      );
      airbaseAircraft = airbase.aircraft;
    }
    return airbaseAircraft;
  }

  addAirbase(
    airbaseName: string,
    className: string,
    latitude: number,
    longitude: number
  ) {
    if (!this.currentSideId) {
      return;
    }
    this.recordHistory();
    const airbase = new Airbase({
      id: randomUUID(),
      name: airbaseName,
      sideId: this.currentSideId,
      className: className,
      latitude: latitude,
      longitude: longitude,
      altitude: 0.0,
      sideColor: this.currentScenario.getSideColor(this.currentSideId),
    });
    this.currentScenario.airbases.push(airbase);
    return airbase;
  }

  addReferencePoint(
    referencePointName: string,
    latitude: number,
    longitude: number
  ) {
    if (!this.currentSideId) {
      return;
    }
    this.recordHistory();
    const referencePoint = new ReferencePoint({
      id: randomUUID(),
      name: referencePointName,
      sideId: this.currentSideId,
      latitude: latitude,
      longitude: longitude,
      altitude: 0.0,
      sideColor: this.currentScenario.getSideColor(this.currentSideId),
    });
    this.currentScenario.referencePoints.push(referencePoint);
    return referencePoint;
  }

  removeReferencePoint(referencePointId: string) {
    this.recordHistory();
    this.currentScenario.referencePoints =
      this.currentScenario.referencePoints.filter(
        (referencePoint) => referencePoint.id !== referencePointId
      );
  }

  removeWeapon(weaponId: string) {
    this.recordHistory();
    this.currentScenario.weapons = this.currentScenario.weapons.filter(
      (weapon) => weapon.id !== weaponId
    );
  }

  removeAirbase(airbaseId: string) {
    this.recordHistory();
    this.currentScenario.airbases = this.currentScenario.airbases.filter(
      (airbase) => airbase.id !== airbaseId
    );
    this.currentScenario.aircraft.forEach((aircraft) => {
      if (aircraft.homeBaseId === airbaseId) {
        aircraft.homeBaseId = "";
        if (aircraft.rtb) {
          aircraft.rtb = false;
          aircraft.route = [];
        }
      }
    });
  }

  removeFacility(facilityId: string) {
    this.recordHistory();
    this.currentScenario.facilities = this.currentScenario.facilities.filter(
      (facility) => facility.id !== facilityId
    );
  }

  removeAircraft(aircraftId: string) {
    this.recordHistory();
    this.currentScenario.aircraft = this.currentScenario.aircraft.filter(
      (aircraft) => aircraft.id !== aircraftId
    );
  }

  addFacility(
    facilityName: string,
    className: string,
    latitude: number,
    longitude: number,
    range?: number
  ) {
    if (!this.currentSideId) {
      return;
    }
    this.recordHistory();
    const facility = new Facility({
      id: randomUUID(),
      name: facilityName,
      sideId: this.currentSideId,
      className: className,
      latitude: latitude,
      longitude: longitude,
      altitude: 0.0,
      range: range ?? 250,
      sideColor: this.currentScenario.getSideColor(this.currentSideId),
      weapons: this.demoMode
        ? this.getDefaultFacilityWeapons(
            this.currentSideId,
            this.currentScenario.getSideColor(this.currentSideId)
          )
        : [],
    });
    this.currentScenario.facilities.push(facility);
    return facility;
  }

  addShip(
    shipName: string,
    className: string,
    latitude: number,
    longitude: number,
    speed?: number,
    maxFuel?: number,
    fuelRate?: number,
    range?: number
  ): Ship | undefined {
    if (!this.currentSideId) {
      return;
    }
    this.recordHistory();
    const ship = new Ship({
      id: randomUUID(),
      name: shipName,
      sideId: this.currentSideId,
      className: className,
      latitude: latitude,
      longitude: longitude,
      altitude: 0.0,
      heading: 0.0,
      speed: speed ?? 30.0,
      currentFuel: maxFuel ?? 32000000.0,
      maxFuel: maxFuel ?? 32000000.0,
      fuelRate: fuelRate ?? 7000.0,
      range: range ?? 250,
      route: [],
      selected: false,
      sideColor: this.currentScenario.getSideColor(this.currentSideId),
      weapons: this.demoMode
        ? this.getDefaultShipWeapons(
            this.currentSideId,
            this.currentScenario.getSideColor(this.currentSideId)
          )
        : [],
      aircraft: [],
    });
    this.currentScenario.ships.push(ship);
    return ship;
  }

  duplicateUnit(unitId: string, unitType: string) {
    if (unitType === "aircraft") {
      const aircraft = this.currentScenario.getAircraft(unitId);
      if (aircraft) {
        this.recordHistory();
        const newAircraft = new Aircraft({
          id: randomUUID(),
          name: aircraft.name,
          sideId: aircraft.sideId,
          className: aircraft.className,
          latitude: aircraft.latitude - 0.5,
          longitude: aircraft.longitude - 0.5,
          altitude: aircraft.altitude,
          heading: aircraft.heading,
          speed: aircraft.speed,
          currentFuel: aircraft.maxFuel,
          maxFuel: aircraft.maxFuel,
          fuelRate: aircraft.fuelRate,
          range: aircraft.range,
          route: [],
          selected: false,
          weapons: aircraft.weapons,
          homeBaseId: aircraft.homeBaseId,
          rtb: false,
          targetId: aircraft.targetId,
          sideColor: aircraft.sideColor,
          isTanker: aircraft.isTanker,
          fuelOffloadCapacity: aircraft.fuelOffloadCapacity,
          fuelTransferRate: aircraft.fuelTransferRate,
          refuelRange: aircraft.refuelRange,
          isElectronicWarfare: aircraft.isElectronicWarfare,
          jammingRange: aircraft.jammingRange,
          jammingStrength: aircraft.jammingStrength,
          jammingModes: aircraft.jammingModes,
          communicationDisruption: aircraft.communicationDisruption,
        });
        this.currentScenario.aircraft.push(newAircraft);
        return newAircraft;
      }
    }
  }

  addAircraftToShip(
    shipId: string,
    className: string,
    speed?: number,
    maxFuel?: number,
    fuelRate?: number,
    range?: number,
    isTanker?: boolean,
    fuelOffloadCapacity?: number,
    fuelTransferRate?: number,
    refuelRange?: number,
    isElectronicWarfare?: boolean,
    jammingRange?: number,
    jammingStrength?: number,
    jammingModes?: string[],
    communicationDisruption?: number
  ) {
    let shipAircraft: Aircraft[] = [];
    if (!this.currentSideId) {
      return shipAircraft;
    }
    const ship = this.currentScenario.getShip(shipId);
    if (ship) {
      this.recordHistory();
      shipAircraft = ship.aircraft;
      if (!(className && speed && maxFuel && fuelRate && range))
        return shipAircraft;
      const aircraft = new Aircraft({
        id: randomUUID(),
        name: `${className} #${randomInt(0, 1000)}`,
        sideId: ship.sideId,
        className: className,
        latitude: ship.latitude - 0.5,
        longitude: ship.longitude - 0.5,
        altitude: 10000.0,
        heading: 90.0,
        speed: speed,
        currentFuel: maxFuel,
        maxFuel: maxFuel,
        fuelRate: fuelRate,
        range: range,
        weapons:
          !isTanker && this.demoMode
            ? this.getDefaultAircraftWeapons(
                this.currentSideId,
                this.currentScenario.getSideColor(this.currentSideId)
              )
            : [],
        homeBaseId: ship.id,
        rtb: false,
        sideColor: ship.sideColor,
        isTanker,
        fuelOffloadCapacity: fuelOffloadCapacity ?? 0,
        fuelTransferRate: fuelTransferRate ?? 0,
        refuelRange: refuelRange ?? 0,
        isElectronicWarfare,
        jammingRange: jammingRange ?? 0,
        jammingStrength: jammingStrength ?? 0,
        jammingModes: jammingModes ?? [],
        communicationDisruption: communicationDisruption ?? 0,
      });
      ship.aircraft.push(aircraft);
    }
    return shipAircraft;
  }

  launchAircraftFromShip(shipId: string, aircraftIds: string[]) {
    if (!this.currentSideId) {
      return [];
    }
    const ship = this.currentScenario.getShip(shipId);
    if (ship && ship.aircraft.length > 0) {
      this.recordHistory();
      const launchedAircraft: Aircraft[] = [];
      ship.aircraft = ship.aircraft.filter((shipAircraft) => {
        if (aircraftIds.includes(shipAircraft.id)) {
          launchedAircraft.push(shipAircraft);
          return false;
        }
        return true;
      });
      if (launchedAircraft.length > 0) {
        launchedAircraft.forEach((aircraft) => {
          this.currentScenario.aircraft.push(aircraft);
        });
        return launchedAircraft;
      }
    }
    return [];
  }

  removeAircraftFromShip(shipId: string, aircraftIds: string[]): Aircraft[] {
    let shipAircraft: Aircraft[] = [];
    if (!this.currentSideId) {
      return shipAircraft;
    }
    this.recordHistory();
    const ship = this.currentScenario.getShip(shipId);
    if (ship) {
      ship.aircraft = ship.aircraft.filter(
        (aircraft) => !aircraftIds.includes(aircraft.id)
      );
      shipAircraft = ship.aircraft;
    }
    return shipAircraft;
  }

  removeShip(shipId: string) {
    this.recordHistory();
    this.currentScenario.ships = this.currentScenario.ships.filter(
      (ship) => ship.id !== shipId
    );
    this.currentScenario.aircraft.forEach((aircraft) => {
      if (aircraft.homeBaseId === shipId) {
        aircraft.homeBaseId = "";
        if (aircraft.rtb) {
          aircraft.rtb = false;
          aircraft.route = [];
        }
      }
    });
  }

  private aircraftIdsAssignedToOtherMissions(
    excludeMissionId: string = ""
  ): Set<string> {
    const used = new Set<string>();
    this.currentScenario.missions.forEach((mission) => {
      if (excludeMissionId && mission.id === excludeMissionId) return;
      mission.assignedUnitIds.forEach((unitId) => used.add(unitId));
    });
    return used;
  }

  private filterAssignableAttackers(
    candidates: string[],
    excludeMissionId: string = ""
  ): string[] {
    const used = this.aircraftIdsAssignedToOtherMissions(excludeMissionId);
    const seen = new Set<string>();
    const result: string[] = [];
    candidates.forEach((unitId) => {
      if (!unitId || used.has(unitId) || seen.has(unitId)) return;
      seen.add(unitId);
      result.push(unitId);
    });
    return result;
  }

  createPatrolMission(
    missionName: string,
    assignedUnits: string[],
    assignedArea: ReferencePoint[]
  ) {
    if (assignedArea.length < 3) return;
    const filteredUnits = this.filterAssignableAttackers(assignedUnits);
    if (filteredUnits.length < 1) return;
    this.recordHistory();
    const currentSideId = this.currentScenario.getSide(this.currentSideId)?.id;
    const patrolMission = new PatrolMission({
      id: randomUUID(),
      name: missionName,
      sideId: currentSideId ?? this.currentSideId,
      assignedUnitIds: filteredUnits,
      assignedArea: assignedArea,
      active: true,
    });
    this.currentScenario.missions.push(patrolMission);
  }

  updatePatrolMission(
    missionId: string,
    missionName?: string,
    assignedUnits?: string[],
    assignedArea?: ReferencePoint[]
  ) {
    const patrolMission = this.currentScenario.getPatrolMission(missionId);
    if (patrolMission) {
      this.recordHistory();
      if (missionName && missionName !== "") patrolMission.name = missionName;
      if (assignedUnits && assignedUnits.length > 0) {
        const filteredUnits = this.filterAssignableAttackers(
          assignedUnits,
          missionId
        );
        if (filteredUnits.length > 0)
          patrolMission.assignedUnitIds = filteredUnits;
      }
      if (assignedArea && assignedArea.length > 2) {
        patrolMission.assignedArea = assignedArea;
        patrolMission.updatePatrolAreaGeometry();
      }
    }
  }

  createStrikeMission(
    missionName: string,
    assignedAttackers: string[],
    assignedTargets: string[]
  ) {
    const filteredAttackers = this.filterAssignableAttackers(assignedAttackers);
    if (filteredAttackers.length < 1) return;
    this.recordHistory();
    const currentSideId = this.currentScenario.getSide(this.currentSideId)?.id;
    const strikeMission = new StrikeMission({
      id: randomUUID(),
      name: missionName,
      sideId: currentSideId ?? this.currentSideId,
      assignedUnitIds: filteredAttackers,
      assignedTargetIds: assignedTargets,
      active: true,
    });
    this.currentScenario.missions.push(strikeMission);
  }

  updateStrikeMission(
    missionId: string,
    missionName?: string,
    assignedAttackers?: string[],
    assignedTargets?: string[]
  ) {
    const strikeMission = this.currentScenario.getStrikeMission(missionId);
    if (strikeMission) {
      this.recordHistory();
      if (missionName && missionName !== "") strikeMission.name = missionName;
      if (assignedAttackers && assignedAttackers.length > 0) {
        const filteredAttackers = this.filterAssignableAttackers(
          assignedAttackers,
          missionId
        );
        if (filteredAttackers.length > 0)
          strikeMission.assignedUnitIds = filteredAttackers;
      }
      if (assignedTargets && assignedTargets.length > 0)
        strikeMission.assignedTargetIds = assignedTargets;
    }
  }

  deleteMission(missionId: string) {
    this.recordHistory();
    this.currentScenario.missions = this.currentScenario.missions.filter(
      (mission) => mission.id !== missionId
    );
  }

  moveAircraft(aircraftId: string, newLatitude: number, newLongitude: number) {
    const aircraft = this.currentScenario.getAircraft(aircraftId);
    if (aircraft) {
      aircraft.desiredRoute.push([newLatitude, newLongitude]);
      if (aircraft.desiredRoute.length === 1) {
        aircraft.heading = getBearingBetweenTwoPoints(
          aircraft.latitude,
          aircraft.longitude,
          newLatitude,
          newLongitude
        );
      }
      return aircraft;
    }
  }

  moveShip(shipId: string, newLatitude: number, newLongitude: number) {
    const ship = this.currentScenario.getShip(shipId);
    if (ship) {
      ship.desiredRoute.push([newLatitude, newLongitude]);
      if (ship.desiredRoute.length === 1) {
        ship.heading = getBearingBetweenTwoPoints(
          ship.latitude,
          ship.longitude,
          newLatitude,
          newLongitude
        );
      }
      return ship;
    }
  }

  commitRoute(unitId: string) {
    const aircraft = this.currentScenario.getAircraft(unitId);
    if (aircraft) {
      this.recordHistory();
      aircraft.route = aircraft.desiredRoute.map(([latitude, longitude]) => [
        latitude,
        longitude,
      ]);
      aircraft.desiredRoute = [];
      return aircraft;
    }
    const ship = this.currentScenario.getShip(unitId);
    if (ship) {
      this.recordHistory();
      ship.route = ship.desiredRoute.map(([latitude, longitude]) => [
        latitude,
        longitude,
      ]);
      ship.desiredRoute = [];
      return ship;
    }
  }

  teleportUnit(unitId: string, newLatitude: number, newLongitude: number) {
    const aircraft = this.currentScenario.getAircraft(unitId);
    if (aircraft) {
      this.recordHistory();
      aircraft.latitude = newLatitude;
      aircraft.longitude = newLongitude;
      return aircraft;
    }
    const airbase = this.currentScenario.getAirbase(unitId);
    if (airbase) {
      this.recordHistory();
      airbase.latitude = newLatitude;
      airbase.longitude = newLongitude;
      airbase.aircraft.forEach((aircraft) => {
        aircraft.latitude = newLatitude - 0.5;
        aircraft.longitude = newLongitude - 0.5;
      });
      return airbase;
    }
    const facility = this.currentScenario.getFacility(unitId);
    if (facility) {
      this.recordHistory();
      facility.latitude = newLatitude;
      facility.longitude = newLongitude;
      return facility;
    }
    const ship = this.currentScenario.getShip(unitId);
    if (ship) {
      this.recordHistory();
      ship.latitude = newLatitude;
      ship.longitude = newLongitude;
      ship.aircraft.forEach((aircraft) => {
        aircraft.latitude = newLatitude - 0.5;
        aircraft.longitude = newLongitude - 0.5;
      });
      return ship;
    }
    const referencePoint = this.currentScenario.getReferencePoint(unitId);
    if (referencePoint) {
      this.recordHistory();
      referencePoint.latitude = newLatitude;
      referencePoint.longitude = newLongitude;
      this.currentScenario.missions.forEach((mission) => {
        if (
          mission instanceof PatrolMission &&
          mission.assignedArea.some((point) => point.id === referencePoint.id)
        ) {
          mission.assignedArea = mission.assignedArea.map((point) =>
            point.id === referencePoint.id ? referencePoint : point
          );
          mission.updatePatrolAreaGeometry();
        }
      });
      return referencePoint;
    }
    const weapon = this.currentScenario.getWeapon(unitId);
    if (weapon) {
      this.recordHistory();
      weapon.latitude = newLatitude;
      weapon.longitude = newLongitude;
      return weapon;
    }
  }

  launchAircraftFromAirbase(airbaseId: string, aircraftIds: string[]) {
    if (!this.currentSideId) {
      return [];
    }
    const airbase = this.currentScenario.getAirbase(airbaseId);
    if (airbase && airbase.aircraft.length > 0) {
      this.recordHistory();
      const launchedAircraft: Aircraft[] = [];
      airbase.aircraft = airbase.aircraft.filter((airbaseAircraft) => {
        if (aircraftIds.includes(airbaseAircraft.id)) {
          launchedAircraft.push(airbaseAircraft);
          return false;
        }
        return true;
      });
      if (launchedAircraft.length > 0) {
        launchedAircraft.forEach((aircraft) => {
          this.currentScenario.aircraft.push(aircraft);
        });
        return launchedAircraft;
      }
    }
    return [];
  }

  aircraftReturnToBase(aircraftId: string) {
    const aircraft = this.currentScenario.getAircraft(aircraftId);
    if (aircraft) {
      this.recordHistory();
      if (aircraft.rtb) {
        this.simulationLogs.addLog(
          aircraft.sideId,
          `${aircraft.name} cancelled RTB`,
          this.currentScenario.currentTime,
          SimulationLogType.RETURN_TO_BASE
        );
        aircraft.rtb = false;
        aircraft.route = [];
        return aircraft;
      } else {
        aircraft.rtb = true;
        const homeBase =
          aircraft.homeBaseId !== ""
            ? this.currentScenario.getAircraftHomeBase(aircraftId)
            : this.currentScenario.getClosestBaseToAircraft(aircraftId);
        if (homeBase) {
          if (aircraft.homeBaseId !== homeBase.id)
            aircraft.homeBaseId = homeBase.id;
          this.moveAircraft(aircraftId, homeBase.latitude, homeBase.longitude);
          this.simulationLogs.addLog(
            aircraft.sideId,
            `${aircraft.name} returning to ${homeBase.name}`,
            this.currentScenario.currentTime,
            SimulationLogType.RETURN_TO_BASE
          );
          return this.commitRoute(aircraftId);
        }
      }
    }
  }

  getFuelNeededToReturnToBase(aircraft: Aircraft) {
    if (aircraft.speed === 0) return 0;
    const homeBase =
      aircraft.homeBaseId !== ""
        ? this.currentScenario.getAircraftHomeBase(aircraft.id)
        : this.currentScenario.getClosestBaseToAircraft(aircraft.id);
    if (homeBase) {
      const distanceBetweenAircraftAndBaseNm =
        (getDistanceBetweenTwoPoints(
          aircraft.latitude,
          aircraft.longitude,
          homeBase.latitude,
          homeBase.longitude
        ) *
          1000) /
        NAUTICAL_MILES_TO_METERS;
      const timeNeededToReturnToBaseHr =
        distanceBetweenAircraftAndBaseNm / aircraft.speed;
      const fuelNeededToReturnToBase =
        timeNeededToReturnToBaseHr * aircraft.fuelRate;
      return fuelNeededToReturnToBase;
    }
    return 0;
  }

  landAircraft(aircraftId: string) {
    const aircraft = this.currentScenario.getAircraft(aircraftId);
    if (aircraft && aircraft.rtb) {
      const homeBase = this.currentScenario.getAircraftHomeBase(aircraftId);
      if (homeBase) {
        const newAircraft = new Aircraft({
          id: aircraft.id,
          name: aircraft.name,
          sideId: aircraft.sideId,
          className: aircraft.className,
          latitude: homeBase.latitude - 0.5,
          longitude: homeBase.longitude - 0.5,
          altitude: aircraft.altitude,
          heading: 90.0,
          speed: aircraft.speed,
          currentFuel: aircraft.maxFuel,
          maxFuel: aircraft.maxFuel,
          fuelRate: aircraft.fuelRate,
          range: aircraft.range,
          weapons: aircraft.weapons,
          homeBaseId: homeBase.id,
          rtb: false,
          targetId: aircraft.targetId,
          sideColor: aircraft.sideColor,
          isObjective: aircraft.isObjective,
          isTanker: aircraft.isTanker,
          fuelOffloadCapacity: aircraft.fuelOffloadCapacity,
          fuelTransferRate: aircraft.fuelTransferRate,
          refuelRange: aircraft.refuelRange,
          isElectronicWarfare: aircraft.isElectronicWarfare,
          jammingRange: aircraft.jammingRange,
          jammingStrength: aircraft.jammingStrength,
          jammingModes: aircraft.jammingModes,
          communicationDisruption: aircraft.communicationDisruption,
        });
        homeBase.aircraft.push(newAircraft);
        this.removeAircraft(aircraft.id);
      }
    }
  }

  switchCurrentSide(sideId: string) {
    if (this.currentScenario.getSide(sideId)) {
      this.currentSideId = sideId;
    }
  }

  switchScenarioTimeCompression() {
    const timeCompressions = Object.keys(GAME_SPEED_DELAY_MS).map((speed) =>
      parseInt(speed)
    );
    for (let i = 0; i < timeCompressions.length; i++) {
      if (this.currentScenario.timeCompression === timeCompressions[i]) {
        this.currentScenario.timeCompression =
          timeCompressions[(i + 1) % timeCompressions.length];
        break;
      }
    }
  }

  exportCurrentScenario(): string {
    const exportObject = {
      currentScenario: this.currentScenario, // TODO clean up some parameters that are not needed before export, e.g. PatrolMission patrolAreaGeometry
      currentSideId: this.currentSideId,
      selectedUnitId: this.selectedUnitId,
      mapView: this.mapView,
    };
    return JSON.stringify(exportObject);
  }

  loadScenario(scenarioString: string) {
    const importObject = JSON.parse(scenarioString);
    this.currentSideId = importObject.currentSideId;
    this.selectedUnitId = importObject.selectedUnitId;
    this.mapView = importObject.mapView;
    this.simulationLogs.clearLogs();

    const savedScenario = importObject.currentScenario;
    const savedSides = savedScenario.sides.map((side: Side) => {
      const newSide = new Side({
        id: side.id,
        name: side.name,
        totalScore: side.totalScore,
        color: side.color,
      });
      return newSide;
    });
    const loadedScenario = new Scenario({
      id: savedScenario.id,
      name: savedScenario.name,
      startTime: savedScenario.startTime,
      currentTime: savedScenario.currentTime,
      duration: savedScenario.duration,
      sides: savedSides,
      timeCompression: savedScenario.timeCompression,
      relationships: new Relationships({
        hostiles: savedScenario.relationships?.hostiles ?? {},
        allies: savedScenario.relationships?.allies ?? {},
      }),
      doctrine: savedScenario.doctrine,
    });
    savedScenario.aircraft.forEach((aircraft: Aircraft) => {
      const aircraftWeapons: Weapon[] =
        aircraft.weapons?.map((weapon: Weapon) =>
          this.createLoadedWeapon(
            weapon,
            Object.keys(LEGACY_AIRCRAFT_WEAPON_KEYS)
          )
        ) ?? [];
      const newAircraft = new Aircraft({
        id: aircraft.id,
        name: aircraft.name,
        sideId: aircraft.sideId,
        className: aircraft.className,
        latitude: aircraft.latitude,
        longitude: aircraft.longitude,
        altitude: aircraft.altitude,
        heading: aircraft.heading,
        speed: aircraft.speed,
        currentFuel: aircraft.currentFuel,
        maxFuel: aircraft.maxFuel,
        fuelRate: aircraft.fuelRate,
        range: aircraft.range,
        route: aircraft.route,
        selected: aircraft.selected,
        weapons: aircraftWeapons,
        homeBaseId: aircraft.homeBaseId,
        rtb: aircraft.rtb,
        targetId: aircraft.targetId ?? "",
        sideColor: aircraft.sideColor,
        isObjective: aircraft.isObjective,
        isTanker: aircraft.isTanker,
        fuelOffloadCapacity: aircraft.fuelOffloadCapacity,
        fuelTransferRate: aircraft.fuelTransferRate,
        refuelRange: aircraft.refuelRange,
        isElectronicWarfare: aircraft.isElectronicWarfare,
        jammingRange: aircraft.jammingRange,
        jammingStrength: aircraft.jammingStrength,
        jammingModes: aircraft.jammingModes,
        communicationDisruption: aircraft.communicationDisruption,
      });
      loadedScenario.aircraft.push(newAircraft);
    });
    savedScenario.airbases.forEach((airbase: Airbase) => {
      const airbaseAircraft: Aircraft[] = [];
      airbase.aircraft.forEach((aircraft: Aircraft) => {
        const aircraftWeapons: Weapon[] =
          aircraft.weapons?.map((weapon: Weapon) =>
            this.createLoadedWeapon(
              weapon,
              Object.keys(LEGACY_AIRCRAFT_WEAPON_KEYS)
            )
          ) ?? [];
        const newAircraft = new Aircraft({
          id: aircraft.id,
          name: aircraft.name,
          sideId: aircraft.sideId,
          className: aircraft.className,
          latitude: aircraft.latitude,
          longitude: aircraft.longitude,
          altitude: aircraft.altitude,
          heading: aircraft.heading,
          speed: aircraft.speed,
          currentFuel: aircraft.currentFuel,
          maxFuel: aircraft.maxFuel,
          fuelRate: aircraft.fuelRate,
          range: aircraft.range,
          route: aircraft.route,
          selected: aircraft.selected,
          weapons: aircraftWeapons,
          homeBaseId: aircraft.homeBaseId,
          rtb: aircraft.rtb,
          targetId: aircraft.targetId ?? "",
          sideColor: aircraft.sideColor,
          isObjective: aircraft.isObjective,
          isTanker: aircraft.isTanker,
          fuelOffloadCapacity: aircraft.fuelOffloadCapacity,
          fuelTransferRate: aircraft.fuelTransferRate,
          refuelRange: aircraft.refuelRange,
          isElectronicWarfare: aircraft.isElectronicWarfare,
          jammingRange: aircraft.jammingRange,
          jammingStrength: aircraft.jammingStrength,
          jammingModes: aircraft.jammingModes,
          communicationDisruption: aircraft.communicationDisruption,
        });
        airbaseAircraft.push(newAircraft);
      });
      const newAirbase = new Airbase({
        id: airbase.id,
        name: airbase.name,
        sideId: airbase.sideId,
        className: airbase.className,
        latitude: airbase.latitude,
        longitude: airbase.longitude,
        altitude: airbase.altitude,
        sideColor: airbase.sideColor,
        aircraft: airbaseAircraft,
        isObjective: airbase.isObjective,
      });
      loadedScenario.airbases.push(newAirbase);
    });
    savedScenario.facilities.forEach((facility: Facility) => {
      const facilityWeapons: Weapon[] =
        facility.weapons?.map((weapon: Weapon) =>
          this.createLoadedWeapon(
            weapon,
            Object.keys(DEFAULT_FACILITY_WEAPON_KEYS)
          )
        ) ?? [];
      const newFacility = new Facility({
        id: facility.id,
        name: facility.name,
        sideId: facility.sideId,
        className: facility.className,
        latitude: facility.latitude,
        longitude: facility.longitude,
        altitude: facility.altitude,
        range: facility.range,
        weapons: facilityWeapons,
        sideColor: facility.sideColor,
        isObjective: facility.isObjective,
      });
      loadedScenario.facilities.push(newFacility);
    });
    savedScenario.weapons.forEach((weapon: Weapon) => {
      const newWeapon = this.createLoadedWeapon(weapon);
      loadedScenario.weapons.push(newWeapon);
    });
    savedScenario.ships?.forEach((ship: Ship) => {
      const shipAircraft: Aircraft[] = [];
      ship.aircraft.forEach((aircraft: Aircraft) => {
        const aircraftWeapons: Weapon[] =
          aircraft.weapons?.map((weapon: Weapon) =>
            this.createLoadedWeapon(
              weapon,
              Object.keys(LEGACY_AIRCRAFT_WEAPON_KEYS)
            )
          ) ?? [];
        const newAircraft = new Aircraft({
          id: aircraft.id,
          name: aircraft.name,
          sideId: aircraft.sideId,
          className: aircraft.className,
          latitude: aircraft.latitude,
          longitude: aircraft.longitude,
          altitude: aircraft.altitude,
          heading: aircraft.heading,
          speed: aircraft.speed,
          currentFuel: aircraft.currentFuel,
          maxFuel: aircraft.maxFuel,
          fuelRate: aircraft.fuelRate,
          range: aircraft.range,
          route: aircraft.route,
          selected: aircraft.selected,
          weapons: aircraftWeapons,
          homeBaseId: aircraft.homeBaseId,
          rtb: aircraft.rtb,
          targetId: aircraft.targetId ?? "",
          sideColor: aircraft.sideColor,
          isObjective: aircraft.isObjective,
          isTanker: aircraft.isTanker,
          fuelOffloadCapacity: aircraft.fuelOffloadCapacity,
          fuelTransferRate: aircraft.fuelTransferRate,
          refuelRange: aircraft.refuelRange,
          isElectronicWarfare: aircraft.isElectronicWarfare,
          jammingRange: aircraft.jammingRange,
          jammingStrength: aircraft.jammingStrength,
          jammingModes: aircraft.jammingModes,
          communicationDisruption: aircraft.communicationDisruption,
        });
        shipAircraft.push(newAircraft);
      });
      const shipWeapons: Weapon[] =
        ship.weapons?.map((weapon: Weapon) =>
          this.createLoadedWeapon(weapon, Object.keys(DEFAULT_SHIP_WEAPON_KEYS))
        ) ?? [];
      const newShip = new Ship({
        id: ship.id,
        name: ship.name,
        sideId: ship.sideId,
        className: ship.className,
        latitude: ship.latitude,
        longitude: ship.longitude,
        altitude: ship.altitude,
        heading: ship.heading,
        speed: ship.speed,
        currentFuel: ship.currentFuel,
        maxFuel: ship.maxFuel,
        fuelRate: ship.fuelRate,
        range: ship.range,
        route: ship.route,
        sideColor: ship.sideColor,
        weapons: shipWeapons,
        aircraft: shipAircraft,
        isObjective: ship.isObjective,
      });
      loadedScenario.ships.push(newShip);
    });
    savedScenario.referencePoints?.forEach((referencePoint: ReferencePoint) => {
      const newReferencePoint = new ReferencePoint({
        id: referencePoint.id,
        name: referencePoint.name,
        sideId: referencePoint.sideId,
        latitude: referencePoint.latitude,
        longitude: referencePoint.longitude,
        altitude: referencePoint.altitude,
        sideColor: referencePoint.sideColor,
      });
      loadedScenario.referencePoints.push(newReferencePoint);
    });
    savedScenario.obstacles?.forEach((obstacle: Obstacle) => {
      loadedScenario.obstacles.push(
        new Obstacle({
          id: obstacle.id,
          name: obstacle.name,
          className: obstacle.className,
          sideId: obstacle.sideId ?? "",
          latitude: obstacle.latitude,
          longitude: obstacle.longitude,
          altitude: obstacle.altitude,
          radiusNm: obstacle.radiusNm,
          obstacleType: obstacle.obstacleType,
          sideColor: obstacle.sideColor,
          active: obstacle.active,
          movementPenalty: obstacle.movementPenalty,
          detectionPenalty: obstacle.detectionPenalty,
          communicationPenalty: obstacle.communicationPenalty,
          affectedDomains: obstacle.affectedDomains,
          description: obstacle.description,
        })
      );
    });
    savedScenario.missions?.forEach((mission: Mission) => {
      const baseProps = {
        id: mission.id,
        name: mission.name,
        sideId: mission.sideId,
        assignedUnitIds: mission.assignedUnitIds,
        active: mission.active,
      };
      if ("assignedArea" in mission) {
        const assignedArea: ReferencePoint[] = [];
        mission.assignedArea.forEach((point) => {
          const referencePoint = new ReferencePoint({
            id: point.id,
            name: point.name,
            sideId: point.sideId,
            latitude: point.latitude,
            longitude: point.longitude,
            altitude: point.altitude,
            sideColor: point.sideColor,
          });
          assignedArea.push(referencePoint);
        });
        loadedScenario.missions.push(
          new PatrolMission({
            ...baseProps,
            assignedArea: assignedArea,
          })
        );
      } else {
        loadedScenario.missions.push(
          new StrikeMission({
            ...baseProps,
            assignedTargetIds: mission.assignedTargetIds,
          })
        );
      }
    });

    this.currentScenario = loadedScenario;
    // 加载新场景时清空胜负状态，避免上一局的 ended=true 阻塞 step 推进。
    this.gameOutcome = createInitialGameOutcome();
  }

  toggleGodMode(enabled: boolean = !this.godMode) {
    this.godMode = enabled;
  }

  toggleEraserMode(enabled: boolean = !this.eraserMode) {
    this.eraserMode = enabled;
  }

  updateOnBoardWeaponPositions() {
    this.currentScenario.aircraft.forEach((aircraft) => {
      aircraft.weapons.forEach((weapon) => {
        weapon.latitude = aircraft.latitude;
        weapon.longitude = aircraft.longitude;
      });
    });
    this.currentScenario.facilities.forEach((facility) => {
      facility.weapons.forEach((weapon) => {
        weapon.latitude = facility.latitude;
        weapon.longitude = facility.longitude;
      });
    });
    this.currentScenario.ships.forEach((ship) => {
      ship.weapons.forEach((weapon) => {
        weapon.latitude = ship.latitude;
        weapon.longitude = ship.longitude;
      });
    });
  }

  // 软重置：清掉胜负 / 评分 / 关键单位事件。当前 Game 不持有初始 JSON 副本，
  // 完整场景重载交给 AITacticalCommandPlatform.loadScenarioFromObject。
  reset() {
    this.gameOutcome = createInitialGameOutcome();
    this.currentScenario.lastObjectiveDestroyed = null;
    this.currentScenario.sides.forEach((side) => {
      side.totalScore = 0;
    });
    this.simulationLogs.clearLogs();
  }

  // 胜负判定：每个 step 末尾调用。优先级（高 → 低）：
  //   1. 已结束 → 直接返回
  //   2. KEY_UNIT_DESTROYED：消费 scenario.lastObjectiveDestroyed → 攻方胜
  //   3. TIMEOUT：达到 scenario.duration → 取总分最高方
  // 注：一方作战单位全毁本身不再结束推演（不是胜利条件），继续等关键单位或超时。
  startRecording() {
    this.playbackRecorder.startRecording(this.currentScenario);
  }

  recordStep(force: boolean = false) {
    if (
      this.recordingScenario &&
      (this.playbackRecorder.shouldRecord(this.currentScenario.currentTime) ||
        force)
    ) {
      this.playbackRecorder.recordStep(
        this.exportCurrentScenario(),
        this.currentScenario.currentTime
      );
    }
  }

  exportRecording() {
    this.playbackRecorder.exportRecording(this.currentScenario.currentTime);
  }

  recordHistory() {
    if (this.history.length > MAX_HISTORY_SIZE) {
      this.history.shift();
    }
    this.history.push(this.exportCurrentScenario());
  }

  undo(): boolean {
    if (this.history.length > 0) {
      const lastScenario = this.history.pop();
      if (lastScenario) {
        this.loadScenario(lastScenario);
        return true;
      }
    }
    return false;
  }
}
