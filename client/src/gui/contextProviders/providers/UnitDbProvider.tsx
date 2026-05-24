import React, { useEffect, useState } from "react";
import {
  UnitDbContext,
  SetUnitDbContext,
} from "@/gui/contextProviders/contexts/UnitDbContext";
import { getUnitAssetCatalog } from "@/api/unitAssets";
import { useAuth } from "@/features/auth/AuthContext";
import Dba from "@/game/db/Dba";
import { catalogToDba } from "@/game/db/unitAssetCatalog";

export const UnitDbProvider = ({ children }: { children: React.ReactNode }) => {
  const { user } = useAuth();
  const [currentUnitDb, setCurrentUnitDb] = useState<Dba>(() => new Dba());

  useEffect(() => {
    let cancelled = false;
    if (!user) {
      setCurrentUnitDb(new Dba());
      return () => {
        cancelled = true;
      };
    }

    getUnitAssetCatalog()
      .then((catalog) => {
        if (!cancelled) setCurrentUnitDb(catalogToDba(catalog));
      })
      .catch(() => {
        if (!cancelled) setCurrentUnitDb(new Dba());
      });

    return () => {
      cancelled = true;
    };
  }, [user]);

  return (
    <UnitDbContext.Provider value={currentUnitDb}>
      <SetUnitDbContext.Provider value={setCurrentUnitDb}>
        {children}
      </SetUnitDbContext.Provider>
    </UnitDbContext.Provider>
  );
};
