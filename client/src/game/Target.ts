import type Airbase from "@/game/units/Airbase";
import type Aircraft from "@/game/units/Aircraft";
import type Facility from "@/game/units/Facility";
import type Ship from "@/game/units/Ship";
import type Weapon from "@/game/units/Weapon";

export type Target = Aircraft | Facility | Weapon | Airbase | Ship;
