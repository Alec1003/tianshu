export interface IWeaponModel {
  className: string;
  speed: number;
  maxFuel: number;
  fuelRate: number;
  range: number;
  lethality: number;
  targetTypes?: string[];
}
