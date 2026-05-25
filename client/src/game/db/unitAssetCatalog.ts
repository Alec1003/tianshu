import type { UnitAsset, UnitAssetCatalogPayload } from "@/api/types";
import Dba from "@/game/db/Dba";
import type { IAircraftModel } from "@/game/db/models/Aircraft";
import type { IAirbaseModel } from "@/game/db/models/Airbase";
import type { IFacilityModel } from "@/game/db/models/Facility";
import type { IShipModel } from "@/game/db/models/Ship";
import type { IWeaponModel } from "@/game/db/models/Weapon";

export function catalogToDba(catalog: UnitAssetCatalogPayload): Dba {
  const db = new Dba();
  db.aircraftDb = catalog.aircraftDb as unknown as IAircraftModel[];
  db.airbaseDb = catalog.airbaseDb as unknown as IAirbaseModel[];
  db.facilityDb = catalog.facilityDb as unknown as IFacilityModel[];
  db.shipDb = catalog.shipDb as unknown as IShipModel[];
  db.weaponDb = catalog.weaponDb as unknown as IWeaponModel[];
  return db;
}

export function unitAssetsToDba(assets: UnitAsset[]): Dba {
  const db = new Dba();
  db.aircraftDb = uniqueUnitModels(
    assets,
    "aircraft",
    (model: IAircraftModel) => model.className
  );
  db.airbaseDb = uniqueUnitModels(
    assets,
    "airbase",
    (model: IAirbaseModel) => model.name
  );
  db.facilityDb = uniqueUnitModels(
    assets,
    "facility",
    (model: IFacilityModel) => model.className
  );
  db.shipDb = uniqueUnitModels(
    assets,
    "ship",
    (model: IShipModel) => model.className
  );
  db.weaponDb = uniqueUnitModels(
    assets,
    "weapon",
    (model: IWeaponModel) => model.className
  );
  return db;
}

function uniqueUnitModels<T>(
  assets: UnitAsset[],
  type: UnitAsset["type"],
  modelName: (model: T) => string
): T[] {
  const byName = new Map<string, T>();
  for (const asset of assets
    .filter((item) => item.type === type)
    .sort((a, b) => Number(b.is_system) - Number(a.is_system))) {
    const model = asset.data as unknown as T;
    byName.set(modelName(model), model);
  }
  return [...byName.values()];
}

export function dbaToCatalog(db: Dba): UnitAssetCatalogPayload {
  return {
    aircraftDb: db.getAircraftDb() as unknown as Record<string, unknown>[],
    airbaseDb: db.getAirbaseDb() as unknown as Record<string, unknown>[],
    facilityDb: db.getFacilityDb() as unknown as Record<string, unknown>[],
    shipDb: db.getShipDb() as unknown as Record<string, unknown>[],
    weaponDb: db.getWeaponDb() as unknown as Record<string, unknown>[],
  };
}
