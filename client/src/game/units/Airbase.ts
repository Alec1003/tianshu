import Aircraft from "@/game/units/Aircraft";
import { convertColorNameToSideColor, SIDE_COLOR } from "@/utils/colors";

interface IAirbase {
  id: string;
  name: string;
  sideId: string;
  className: string;
  latitude: number;
  longitude: number;
  altitude: number;
  sideColor?: string | SIDE_COLOR;
  aircraft?: Aircraft[];
  isObjective?: boolean;
}

export default class Airbase {
  id: string;
  name: string;
  sideId: string;
  className: string;
  latitude: number;
  longitude: number;
  altitude: number; // FT ASL -- currently default -- need to reference from database
  sideColor: SIDE_COLOR;
  aircraft: Aircraft[];
  isObjective: boolean;

  constructor(parameters: IAirbase) {
    this.id = parameters.id;
    this.name = parameters.name;
    this.sideId = parameters.sideId;
    this.className = parameters.className;
    this.latitude = parameters.latitude;
    this.longitude = parameters.longitude;
    this.altitude = parameters.altitude;
    this.sideColor = convertColorNameToSideColor(parameters.sideColor);
    this.aircraft = parameters.aircraft ?? [];
    this.isObjective = parameters.isObjective ?? false;
  }
}
