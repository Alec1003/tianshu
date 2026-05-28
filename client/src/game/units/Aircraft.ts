import Weapon from "@/game/units/Weapon";
import { convertColorNameToSideColor, SIDE_COLOR } from "@/utils/colors";

interface IAircraft {
  id: string;
  name: string;
  sideId: string;
  className: string;
  latitude: number;
  longitude: number;
  altitude: number;
  heading: number;
  speed: number;
  currentFuel: number;
  maxFuel: number;
  fuelRate: number; // lbs/hr
  range: number;
  route?: number[][];
  selected?: boolean;
  sideColor?: string | SIDE_COLOR;
  weapons?: Weapon[];
  homeBaseId?: string;
  rtb?: boolean;
  targetId?: string;
  desiredRoute?: number[][];
  isObjective?: boolean;
  isTanker?: boolean;
  fuelOffloadCapacity?: number;
  fuelTransferRate?: number;
  refuelRange?: number;
  isElectronicWarfare?: boolean;
  jammingRange?: number;
  jammingStrength?: number;
  jammingModes?: string[];
  communicationDisruption?: number;
}

export default class Aircraft {
  id: string;
  name: string;
  sideId: string;
  className: string;
  latitude: number;
  longitude: number;
  altitude: number; // FT ASL -- currently default -- need to reference from database
  heading: number;
  speed: number; // KTS -- currently default -- need to reference from database
  currentFuel: number;
  maxFuel: number;
  fuelRate: number; // lbs/hr
  range: number; // NM -- currently default -- need to reference from database
  route: number[][];
  selected: boolean;
  sideColor: SIDE_COLOR;
  weapons: Weapon[];
  homeBaseId: string;
  rtb: boolean;
  targetId: string;
  desiredRoute: number[][] = [];
  isObjective: boolean;
  isTanker: boolean;
  fuelOffloadCapacity: number;
  fuelTransferRate: number;
  refuelRange: number;
  isElectronicWarfare: boolean;
  jammingRange: number;
  jammingStrength: number;
  jammingModes: string[];
  communicationDisruption: number;

  constructor(parameters: IAircraft) {
    this.id = parameters.id;
    this.name = parameters.name;
    this.sideId = parameters.sideId;
    this.className = parameters.className;
    this.latitude = parameters.latitude;
    this.longitude = parameters.longitude;
    this.altitude = parameters.altitude;
    this.heading = parameters.heading;
    this.speed = parameters.speed;
    this.currentFuel = parameters.currentFuel;
    this.maxFuel = parameters.maxFuel;
    this.fuelRate = parameters.fuelRate;
    this.range = parameters.range;
    this.route = parameters.route ?? [];
    this.selected = parameters.selected ?? false;
    this.sideColor = convertColorNameToSideColor(parameters.sideColor);
    this.weapons = parameters.weapons ?? [];
    this.homeBaseId = parameters.homeBaseId ?? "";
    this.rtb = parameters.rtb ?? false;
    this.targetId = parameters.targetId ?? "";
    this.desiredRoute = parameters.desiredRoute ?? [];
    this.isObjective = parameters.isObjective ?? false;
    const classNameLower = this.className.toLowerCase();
    this.isTanker =
      parameters.isTanker ??
      (classNameLower.includes("tanker") ||
        this.className.toUpperCase().startsWith("KC-"));
    this.fuelOffloadCapacity =
      parameters.fuelOffloadCapacity && parameters.fuelOffloadCapacity > 0
        ? parameters.fuelOffloadCapacity
        : this.isTanker
          ? this.maxFuel * 0.75
          : 0;
    this.fuelTransferRate =
      parameters.fuelTransferRate && parameters.fuelTransferRate > 0
        ? parameters.fuelTransferRate
        : this.isTanker
          ? 100
          : 0;
    this.refuelRange =
      parameters.refuelRange && parameters.refuelRange > 0
        ? parameters.refuelRange
        : this.isTanker
          ? 2
          : 0;
    const ewTokens = [
      "electronic",
      "ewar",
      "jammer",
      "growler",
      "prowler",
      "raven",
      "电子战",
      "干扰",
    ];
    this.isElectronicWarfare =
      parameters.isElectronicWarfare ??
      ewTokens.some((token) => classNameLower.includes(token));
    this.jammingRange =
      parameters.jammingRange && parameters.jammingRange > 0
        ? parameters.jammingRange
        : 0;
    this.jammingStrength = Math.max(
      0,
      Math.min(0.85, parameters.jammingStrength ?? 0)
    );
    this.jammingModes = parameters.jammingModes ?? [];
    this.communicationDisruption = Math.max(
      0,
      Math.min(0.85, parameters.communicationDisruption ?? 0)
    );
  }

  getTotalWeaponQuantity(): number {
    let sum = 0;
    this.weapons.forEach((weapon) => {
      sum += weapon.currentQuantity;
    });
    return sum;
  }

  getWeaponWithHighestEngagementRange(): Weapon | undefined {
    if (this.weapons.length === 0) return;
    return this.weapons.reduce((a, b) =>
      a.getEngagementRange() > b.getEngagementRange() ? a : b
    );
  }

  getWeaponEngagementRange(): number {
    if (this.weapons.length === 0) return 0;
    return (
      this.getWeaponWithHighestEngagementRange()?.getEngagementRange() ?? 0
    );
  }

  getDetectionRange(): number {
    return this.range;
  }
}
