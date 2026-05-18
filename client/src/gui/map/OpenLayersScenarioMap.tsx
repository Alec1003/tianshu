import { get as getProjection, transform } from "ol/proj.js";
import type Game from "@/game/Game";
import { DEFAULT_OL_PROJECTION_CODE } from "@/utils/constants";
import ScenarioMap from "@/gui/map/ScenarioMap";

interface OpenLayersScenarioMapProps {
  game: Game;
  mobileView: boolean;
}

export default function OpenLayersScenarioMap({
  game,
  mobileView,
}: Readonly<OpenLayersScenarioMapProps>) {
  const projection = getProjection(DEFAULT_OL_PROJECTION_CODE) ?? undefined;

  return (
    <ScenarioMap
      center={transform(
        game.mapView.currentCameraCenter,
        "EPSG:4326",
        DEFAULT_OL_PROJECTION_CODE
      )}
      zoom={game.mapView.currentCameraZoom}
      game={game}
      projection={projection}
      mobileView={mobileView}
    />
  );
}
