import { get as getProjection, transform } from "ol/proj.js";
import type Game from "@/game/Game";
import { DEFAULT_OL_PROJECTION_CODE } from "@/utils/constants";
import ScenarioMap from "@/gui/map/ScenarioMap";
import type { RuntimeAttackRequest } from "@/api/types";

interface OpenLayersScenarioMapProps {
  game: Game;
  mobileView: boolean;
  onPlay?: () => void | Promise<void>;
  onPause?: () => void | Promise<void>;
  onStep?: () => void | Promise<void>;
  onReset?: () => void | Promise<void>;
  onAttack?: (attack: RuntimeAttackRequest) => void | Promise<void>;
}

export default function OpenLayersScenarioMap({
  game,
  mobileView,
  onPlay,
  onPause,
  onStep,
  onReset,
  onAttack,
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
      onPlay={onPlay}
      onPause={onPause}
      onStep={onStep}
      onReset={onReset}
      onAttack={onAttack}
    />
  );
}
