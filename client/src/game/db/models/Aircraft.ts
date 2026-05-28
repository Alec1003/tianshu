export interface IAircraftModel {
  className: string;
  speed: number;
  maxFuel: number;
  fuelRate: number;
  range: number;
  isTanker?: boolean;
  fuelOffloadCapacity?: number;
  fuelTransferRate?: number;
  refuelRange?: number;
  isElectronicWarfare?: boolean;
  jammingRange?: number;
  jammingStrength?: number;
  jammingModes?: string[];
  communicationDisruption?: number;
  dataSource: {
    speedSrc: string;
    maxFuelSrc: string;
    fuelRateSrc: string;
    rangeSrc: string;
  };
  units: {
    speedUnit: string;
    maxFuelUnit: string;
    fuelRateUnit: string;
    rangeUnit: string;
    jammingRangeUnit?: string;
  };
}
