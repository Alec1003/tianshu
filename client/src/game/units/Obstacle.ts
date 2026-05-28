export type ObstacleType =
  | "no_go"
  | "restricted_airspace"
  | "blocked_area"
  | "terrain"
  | "weather"
  | "sensor_shadow"
  | "communication_shadow";

interface IObstacle {
  id: string;
  name: string;
  className: string;
  sideId?: string;
  latitude: number;
  longitude: number;
  altitude?: number;
  radiusNm?: number;
  obstacleType?: ObstacleType | string;
  sideColor?: string;
  active?: boolean;
  movementPenalty?: number;
  detectionPenalty?: number;
  communicationPenalty?: number;
  affectedDomains?: string[];
  description?: string;
}

export default class Obstacle {
  id: string;
  name: string;
  className: string;
  sideId: string;
  latitude: number;
  longitude: number;
  altitude: number;
  radiusNm: number;
  obstacleType: ObstacleType | string;
  sideColor: string;
  active: boolean;
  movementPenalty: number;
  detectionPenalty: number;
  communicationPenalty: number;
  affectedDomains: string[];
  description: string;

  constructor(parameters: IObstacle) {
    this.id = parameters.id;
    this.name = parameters.name;
    this.className = parameters.className;
    this.sideId = parameters.sideId ?? "";
    this.latitude = parameters.latitude;
    this.longitude = parameters.longitude;
    this.altitude = parameters.altitude ?? 0;
    this.radiusNm = parameters.radiusNm ?? 10;
    this.obstacleType = parameters.obstacleType ?? "no_go";
    this.sideColor = parameters.sideColor ?? "#38bdf8";
    this.active = parameters.active ?? true;
    this.movementPenalty = parameters.movementPenalty ?? 1;
    this.detectionPenalty = parameters.detectionPenalty ?? 0;
    this.communicationPenalty = parameters.communicationPenalty ?? 0;
    this.affectedDomains = parameters.affectedDomains ?? ["aircraft", "ship"];
    this.description = parameters.description ?? "";
  }
}
