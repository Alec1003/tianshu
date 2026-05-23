import Aircraft from "@/game/units/Aircraft";
import Airbase from "@/game/units/Airbase";
import Facility from "@/game/units/Facility";
import Side from "@/game/Side";
import Weapon from "@/game/units/Weapon";
import Ship from "@/game/units/Ship";
import { getDistanceBetweenTwoPoints } from "@/utils/mapFunctions";
import ReferencePoint from "@/game/units/ReferencePoint";
import PatrolMission from "@/game/mission/PatrolMission";
import type { Target } from "@/game/Target";
import StrikeMission from "@/game/mission/StrikeMission";
import { Mission } from "@/game/Game";
import { SIDE_COLOR } from "@/utils/colors";
import Relationships from "@/game/Relationships";
import { randomUUID } from "@/utils/generateUUID";
import Doctrine, { DoctrineType, SideDoctrine } from "@/game/Doctrine";

type HomeBase = Airbase | Ship;

// 关键单位（isObjective）被毁事件，用于胜负判定。
// 在 weaponEngagement.onUnitDestroyed 中写入；Game.checkGameEnded 读取。
export interface ObjectiveDestroyedEvent {
  attackerSideId: string;
  victimSideId: string;
  unitId: string;
  unitName: string;
  unitType: "aircraft" | "weapon" | "facility" | "ship" | "airbase";
  destroyedAt: number; // scenario currentTime (unix seconds)
}

interface IScenario {
  id: string;
  name: string;
  startTime: number;
  currentTime?: number;
  duration: number;
  sides?: Side[];
  timeCompression?: number;
  aircraft?: Aircraft[];
  ships?: Ship[];
  facilities?: Facility[];
  airbases?: Airbase[];
  weapons?: Weapon[];
  referencePoints?: ReferencePoint[];
  missions?: PatrolMission[];
  relationships?: Relationships;
  doctrine?: Doctrine;
}

export default class Scenario {
  id: string;
  name: string;
  startTime: number;
  currentTime: number;
  duration: number;
  sides: Side[];
  timeCompression: number;
  aircraft: Aircraft[];
  ships: Ship[];
  facilities: Facility[];
  airbases: Airbase[];
  weapons: Weapon[];
  referencePoints: ReferencePoint[];
  missions: Mission[];
  relationships: Relationships;
  doctrine: Doctrine;
  // 最近一次关键单位被毁事件（KEY_UNIT_DESTROYED 触发器）。Game.checkGameEnded
  // 在每个 tick 末尾消费它来判定胜负，消费后保留（仅初始化和 reset 时清空），
  // 以便 AAR 弹窗能展示是哪个关键单位被击毁。
  lastObjectiveDestroyed: ObjectiveDestroyedEvent | null = null;

  constructor(parameters: IScenario) {
    this.id = parameters.id;
    this.name = parameters.name;
    this.startTime = parameters.startTime;
    this.currentTime = parameters.currentTime ?? parameters.startTime;
    this.duration = parameters.duration;
    this.sides = parameters.sides ?? [];
    this.timeCompression = parameters.timeCompression ?? 1;
    this.aircraft = parameters.aircraft ?? [];
    this.facilities = parameters.facilities ?? [];
    this.airbases = parameters.airbases ?? [];
    this.weapons = parameters.weapons ?? [];
    this.ships = parameters.ships ?? [];
    this.referencePoints = parameters.referencePoints ?? [];
    this.missions = parameters.missions ?? [];
    this.relationships = parameters.relationships ?? new Relationships({});
    // 防御性兜底：servers / 历史快照可能把 doctrine 序列化成 {} 或缺失某些
    // sideId 的条目。这里若任意一方没条令就用默认（全开交战类）补齐，避免
    // checkSideDoctrine 直接返回 false 导致红蓝静止不交战。
    const incoming = parameters.doctrine;
    if (!incoming || Object.keys(incoming).length === 0) {
      this.doctrine = this.getDefaultDoctrine();
    } else {
      this.doctrine = incoming;
      this.sides.forEach((side) => {
        if (!this.doctrine[side.id]) {
          this.doctrine[side.id] = this.getDefaultSideDoctrine();
        }
      });
    }
  }

  getDefaultDoctrine(): Doctrine {
    const defaultDoctrine: Doctrine = {};
    this.sides.forEach((side) => {
      defaultDoctrine[side.id] = this.getDefaultSideDoctrine();
    });
    return defaultDoctrine;
  }

  getDefaultSideDoctrine(): SideDoctrine {
    return {
      [DoctrineType.AIRCRAFT_ATTACK_HOSTILE]: true,
      [DoctrineType.AIRCRAFT_CHASE_HOSTILE]: true,
      [DoctrineType.AIRCRAFT_RTB_WHEN_OUT_OF_RANGE]: false,
      [DoctrineType.AIRCRAFT_RTB_WHEN_STRIKE_MISSION_COMPLETE]: false,
      [DoctrineType.SAM_ATTACK_HOSTILE]: true,
      [DoctrineType.SHIP_ATTACK_HOSTILE]: true,
    };
  }

  getSideDoctrine(sideId: string): SideDoctrine {
    if (!this.doctrine[sideId]) {
      this.doctrine[sideId] = this.getDefaultSideDoctrine();
    }
    return this.doctrine[sideId];
  }

  checkSideDoctrine(sideId: string, doctrineType: DoctrineType): boolean {
    if (!this.doctrine[sideId]) return false;
    return this.doctrine[sideId][doctrineType] ?? false;
  }

  updateSideDoctrine(sideId: string, sideDoctrine?: SideDoctrine) {
    if (!this.doctrine[sideId]) {
      this.doctrine[sideId] = this.getDefaultSideDoctrine();
    }
    if (sideDoctrine) {
      Object.keys(sideDoctrine).forEach((key) => {
        const doctrineKey = key as DoctrineType;
        if (this.doctrine[sideId][doctrineKey] !== undefined) {
          this.doctrine[sideId][doctrineKey] = sideDoctrine[doctrineKey];
        }
      });
    }
  }

  removeSideDoctrine(sideId: string) {
    if (this.doctrine[sideId]) {
      delete this.doctrine[sideId];
    }
  }

  getSide(sideId: string | null | undefined): Side | undefined {
    return this.sides.find((side) => side.id === sideId);
  }

  getSideName(sideId: string | null | undefined): string {
    const side = this.getSide(sideId);
    if (side) {
      return side.name;
    }
    return "N/A";
  }

  getSideColor(sideId: string | null | undefined): SIDE_COLOR {
    const side = this.getSide(sideId);
    if (side) {
      return side.color;
    }
    return SIDE_COLOR.BLACK;
  }

  getAircraft(aircraftId: string | null): Aircraft | undefined {
    return this.aircraft.find((aircraft) => aircraft.id === aircraftId);
  }

  getFacility(facilityId: string | null): Facility | undefined {
    return this.facilities.find((facility) => facility.id === facilityId);
  }

  getAirbase(airbaseId: string | null): Airbase | undefined {
    return this.airbases.find((airbase) => airbase.id === airbaseId);
  }

  getWeapon(weaponId: string | null): Weapon | undefined {
    return this.weapons.find((weapon) => weapon.id === weaponId);
  }

  getShip(shipId: string | null): Ship | undefined {
    return this.ships.find((ship) => ship.id === shipId);
  }

  getReferencePoint(
    referencePointId: string | null
  ): ReferencePoint | undefined {
    return this.referencePoints.find(
      (referencePoint) => referencePoint.id === referencePointId
    );
  }

  getPatrolMission(missionId: string | null): PatrolMission | undefined {
    return this.missions.find(
      (mission) => mission.id === missionId && mission instanceof PatrolMission
    ) as PatrolMission;
  }

  getStrikeMission(missionId: string | null): StrikeMission | undefined {
    return this.missions.find(
      (mission) => mission.id === missionId && mission instanceof StrikeMission
    ) as StrikeMission;
  }

  getAllPatrolMissions(): PatrolMission[] {
    return this.missions.filter(
      (mission) => mission instanceof PatrolMission
    ) as PatrolMission[];
  }

  getAllStrikeMissions(): StrikeMission[] {
    return this.missions.filter(
      (mission) => mission instanceof StrikeMission
    ) as StrikeMission[];
  }

  getMissionByAssignedUnitId(unitId: string): Mission | undefined {
    return this.missions.find((mission) =>
      mission.assignedUnitIds.includes(unitId)
    );
  }

  updateScenarioName(name: string): void {
    this.name = name;
  }

  deleteWeaponFromAircraft(aircraftId: string, weaponId: string): Weapon[] {
    const aircraft = this.getAircraft(aircraftId);
    let aircraftWeapons: Weapon[] = [];
    if (aircraft) {
      const weaponIndex = aircraft.weapons.findIndex(
        (weapon) => weapon.id === weaponId
      );
      if (weaponIndex !== -1) {
        aircraft.weapons.splice(weaponIndex, 1);
      }
      aircraftWeapons = aircraft.weapons;
    }
    return aircraftWeapons;
  }

  updateAircraftWeaponQuantity(
    aircraftId: string,
    weaponId: string,
    increment: number
  ) {
    const aircraft = this.getAircraft(aircraftId);
    let aircraftWeapons: Weapon[] = [];
    if (aircraft) {
      const weapon = aircraft.weapons.find((weapon) => weapon.id === weaponId);
      if (weapon) {
        weapon.currentQuantity = Math.max(
          0,
          Math.min(weapon.maxQuantity, weapon.currentQuantity + increment)
        );
      }
      aircraftWeapons = aircraft.weapons;
    }
    return aircraftWeapons;
  }

  addWeaponToAircraft(
    aircraftId: string,
    weaponClassName?: string,
    weaponSpeed?: number,
    weaponMaxFuel?: number,
    weaponFuelRate?: number,
    weaponRange?: number,
    weaponLethality?: number
  ): Weapon[] {
    const aircraft = this.getAircraft(aircraftId);
    let aircraftWeapons: Weapon[] = [];
    if (aircraft) {
      aircraftWeapons = aircraft.weapons;
      if (
        !(
          weaponClassName &&
          weaponSpeed &&
          weaponMaxFuel &&
          weaponFuelRate &&
          weaponRange &&
          weaponLethality
        )
      ) {
        return aircraftWeapons;
      }
      if (
        aircraft.weapons.find((weapon) => weapon.className === weaponClassName)
      ) {
        return aircraftWeapons;
      }
      const weapon = new Weapon({
        id: randomUUID(),
        name: weaponClassName,
        sideId: aircraft.sideId,
        className: weaponClassName,
        latitude: aircraft.latitude,
        longitude: aircraft.longitude,
        altitude: 10000.0,
        heading: 90.0,
        speed: weaponSpeed,
        currentFuel: weaponMaxFuel,
        maxFuel: weaponMaxFuel,
        fuelRate: weaponFuelRate,
        range: weaponRange,
        sideColor: aircraft.sideColor,
        targetId: null,
        lethality: weaponLethality,
        maxQuantity: 1,
        currentQuantity: 1,
      });
      aircraftWeapons.push(weapon);
    }
    return aircraftWeapons;
  }

  deleteWeaponFromFacility(facilityId: string, weaponId: string): Weapon[] {
    const facility = this.getFacility(facilityId);
    let facilityWeapons: Weapon[] = [];
    if (facility) {
      const weaponIndex = facility.weapons.findIndex(
        (weapon) => weapon.id === weaponId
      );
      if (weaponIndex !== -1) {
        facility.weapons.splice(weaponIndex, 1);
      }
      facilityWeapons = facility.weapons;
    }
    return facilityWeapons;
  }

  updateFacilityWeaponQuantity(
    facilityId: string,
    weaponId: string,
    increment: number
  ) {
    const facility = this.getFacility(facilityId);
    let facilityWeapons: Weapon[] = [];
    if (facility) {
      const weapon = facility.weapons.find((weapon) => weapon.id === weaponId);
      if (weapon) {
        weapon.currentQuantity = Math.max(
          0,
          Math.min(weapon.maxQuantity, weapon.currentQuantity + increment)
        );
      }
      facilityWeapons = facility.weapons;
    }
    return facilityWeapons;
  }

  addWeaponToFacility(
    facilityId: string,
    weaponClassName?: string,
    weaponSpeed?: number,
    weaponMaxFuel?: number,
    weaponFuelRate?: number,
    weaponRange?: number,
    weaponLethality?: number
  ): Weapon[] {
    const facility = this.getFacility(facilityId);
    let facilityWeapons: Weapon[] = [];
    if (facility) {
      facilityWeapons = facility.weapons;
      if (
        !(
          weaponClassName &&
          weaponSpeed &&
          weaponMaxFuel &&
          weaponFuelRate &&
          weaponRange &&
          weaponLethality
        )
      ) {
        return facilityWeapons;
      }
      if (
        facility.weapons.find((weapon) => weapon.className === weaponClassName)
      ) {
        return facilityWeapons;
      }
      const weapon = new Weapon({
        id: randomUUID(),
        name: weaponClassName,
        sideId: facility.sideId,
        className: weaponClassName,
        latitude: facility.latitude,
        longitude: facility.longitude,
        altitude: 10000.0,
        heading: 90.0,
        speed: weaponSpeed,
        currentFuel: weaponMaxFuel,
        maxFuel: weaponMaxFuel,
        fuelRate: weaponFuelRate,
        range: weaponRange,
        sideColor: facility.sideColor,
        targetId: null,
        lethality: weaponLethality,
        maxQuantity: 1,
        currentQuantity: 1,
      });
      facilityWeapons.push(weapon);
    }
    return facilityWeapons;
  }

  deleteWeaponFromShip(shipId: string, weaponId: string): Weapon[] {
    const ship = this.getShip(shipId);
    let shipWeapons: Weapon[] = [];
    if (ship) {
      const weaponIndex = ship.weapons.findIndex(
        (weapon) => weapon.id === weaponId
      );
      if (weaponIndex !== -1) {
        ship.weapons.splice(weaponIndex, 1);
      }
      shipWeapons = ship.weapons;
    }
    return shipWeapons;
  }

  updateShipWeaponQuantity(
    shipId: string,
    weaponId: string,
    increment: number
  ) {
    const ship = this.getShip(shipId);
    let shipWeapons: Weapon[] = [];
    if (ship) {
      const weapon = ship.weapons.find((weapon) => weapon.id === weaponId);
      if (weapon) {
        weapon.currentQuantity = Math.max(
          0,
          Math.min(weapon.maxQuantity, weapon.currentQuantity + increment)
        );
      }
      shipWeapons = ship.weapons;
    }
    return shipWeapons;
  }

  addWeaponToShip(
    shipId: string,
    weaponClassName?: string,
    weaponSpeed?: number,
    weaponMaxFuel?: number,
    weaponFuelRate?: number,
    weaponRange?: number,
    weaponLethality?: number
  ): Weapon[] {
    const ship = this.getShip(shipId);
    let shipWeapons: Weapon[] = [];
    if (ship) {
      shipWeapons = ship.weapons;
      if (
        !(
          weaponClassName &&
          weaponSpeed &&
          weaponMaxFuel &&
          weaponFuelRate &&
          weaponRange &&
          weaponLethality
        )
      ) {
        return shipWeapons;
      }
      if (ship.weapons.find((weapon) => weapon.className === weaponClassName)) {
        return shipWeapons;
      }
      const weapon = new Weapon({
        id: randomUUID(),
        name: weaponClassName,
        sideId: ship.sideId,
        className: weaponClassName,
        latitude: ship.latitude,
        longitude: ship.longitude,
        altitude: 10000.0,
        heading: 90.0,
        speed: weaponSpeed,
        currentFuel: weaponMaxFuel,
        maxFuel: weaponMaxFuel,
        fuelRate: weaponFuelRate,
        range: weaponRange,
        sideColor: ship.sideColor,
        targetId: null,
        lethality: weaponLethality,
        maxQuantity: 1,
        currentQuantity: 1,
      });
      shipWeapons.push(weapon);
    }
    return shipWeapons;
  }

  updateAircraft(
    aircraftId: string,
    aircraftName: string,
    aircraftClassName: string,
    aircraftSpeed: number,
    aircraftCurrentFuel: number,
    aircraftFuelRate: number,
    aircraftRange: number
  ) {
    const aircraft = this.getAircraft(aircraftId);
    if (aircraft) {
      aircraft.name = aircraftName;
      aircraft.className = aircraftClassName;
      aircraft.speed = aircraftSpeed;
      aircraft.currentFuel = aircraftCurrentFuel;
      aircraft.fuelRate = aircraftFuelRate;
      aircraft.range = aircraftRange;
    }
  }

  updateFacility(
    facilityId: string,
    facilityName: string,
    facilityClassName: string,
    facilityRange: number
  ) {
    const facility = this.getFacility(facilityId);
    if (facility) {
      facility.name = facilityName;
      facility.className = facilityClassName;
      facility.range = facilityRange;
    }
  }

  updateAirbase(airbaseId: string, airbaseName: string) {
    const airbase = this.getAirbase(airbaseId);
    if (airbase) {
      airbase.name = airbaseName;
    }
  }

  updateShip(
    shipId: string,
    shipName: string,
    shipClassName: string,
    shipSpeed: number,
    shipCurrentFuel: number,
    shipRange: number
  ) {
    const ship = this.getShip(shipId);
    if (ship) {
      ship.name = shipName;
      ship.className = shipClassName;
      ship.speed = shipSpeed;
      ship.currentFuel = shipCurrentFuel;
      ship.range = shipRange;
    }
  }

  updateReferencePoint(referencePointId: string, referencePointName: string) {
    const referencePoint = this.getReferencePoint(referencePointId);
    if (referencePoint) {
      referencePoint.name = referencePointName;
    }
  }

  getAircraftHomeBase(aircraftId: string): HomeBase | undefined {
    const aircraft = this.getAircraft(aircraftId);
    if (aircraft) {
      return (
        this.getAirbase(aircraft.homeBaseId) ??
        this.getShip(aircraft.homeBaseId)
      );
    }
  }

  getClosestBaseToAircraft(aircraftId: string): HomeBase | undefined {
    const aircraft = this.getAircraft(aircraftId);
    if (aircraft) {
      let closestBase: HomeBase | undefined;
      let closestDistance = Number.MAX_VALUE;
      this.airbases.forEach((airbase) => {
        if (airbase.sideId !== aircraft.sideId) return;
        const distance = getDistanceBetweenTwoPoints(
          aircraft.latitude,
          aircraft.longitude,
          airbase.latitude,
          airbase.longitude
        );
        if (distance < closestDistance) {
          closestDistance = distance;
          closestBase = airbase;
        }
      });
      this.ships.forEach((ship) => {
        if (ship.sideId !== aircraft.sideId) return;
        const distance = getDistanceBetweenTwoPoints(
          aircraft.latitude,
          aircraft.longitude,
          ship.latitude,
          ship.longitude
        );
        if (distance < closestDistance) {
          closestDistance = distance;
          closestBase = ship;
        }
      });
      return closestBase;
    }
  }

  getAllTargetsFromEnemySides(sideId: string): Target[] {
    const targets: Target[] = [];
    this.aircraft.forEach((aircraft) => {
      if (this.isHostile(sideId, aircraft.sideId)) {
        targets.push(aircraft);
      }
    });
    this.facilities.forEach((facility) => {
      if (this.isHostile(sideId, facility.sideId)) {
        targets.push(facility);
      }
    });
    this.ships.forEach((ship) => {
      if (this.isHostile(sideId, ship.sideId)) {
        targets.push(ship);
      }
    });
    this.airbases.forEach((airbase) => {
      if (this.isHostile(sideId, airbase.sideId)) {
        targets.push(airbase);
      }
    });
    return targets;
  }

  isHostile(sideId: string, targetId: string): boolean {
    return this.relationships.isHostile(sideId, targetId);
  }
}
