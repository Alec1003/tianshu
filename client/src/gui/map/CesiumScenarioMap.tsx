import { useCallback, useContext, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Box, Dialog, ListSubheader, Menu, MenuItem } from "@mui/material";
import {
  AircraftDb,
  AirbaseDb,
  FacilityDb,
  ShipDb,
  WeaponDb,
} from "@/game/db/UnitDb";
import type Aircraft from "@/game/units/Aircraft";
import type Facility from "@/game/units/Facility";
import type Ship from "@/game/units/Ship";
import MissionCreatorCard from "@/gui/map/mission/MissionCreatorCard";
import MissionEditorCard from "@/gui/map/mission/MissionEditorCard";
import type { Target } from "@/game/Target";
import {
  CallbackProperty,
  Cartesian2,
  Cartesian3,
  Cartographic,
  Color,
  Entity,
  Ion,
  MapMode2D,
  SceneMode,
  Math as CesiumMath,
  PolylineDashMaterialProperty,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  UrlTemplateImageryProvider,
  Viewer,
} from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import Game from "@/game/Game";
import type {
  RuntimeDeployUnitRequest,
  RuntimeAddWeaponRequest,
  RuntimeDeleteWeaponRequest,
  RuntimeSetUnitPositionRequest,
  RuntimeUnitType,
  RuntimeUpdateUnitRequest,
  RuntimeUpdateWeaponQuantityRequest,
  RuntimeVisibility,
  RuntimeWeaponCarrierType,
} from "@/api/types";
import { SetMouseMapCoordinatesContext } from "@/gui/contextProviders/contexts/MouseMapCoordinatesContext";
import { SetScenarioTimeContext } from "@/gui/contextProviders/contexts/ScenarioTimeContext";
import BottomInfoDisplay from "@/gui/map/toolbar/BottomInfoDisplay";
import {
  CesiumScenarioEntities,
  type ScenarioUnit,
} from "@/gui/map/CesiumScenarioEntities";
import CesiumUnitInfoCard from "@/gui/map/CesiumUnitInfoCard";
import type {
  CesiumBaseLayerKey,
  CesiumPlacement,
} from "@/gui/map/CesiumMapTypes";
import WeaponTable from "@/gui/map/feature/shared/WeaponTable";
import { localizeAirbaseName, localizeUnitName } from "@/i18n/entityNames";

export type CesiumSceneModeKey = "2d" | "3d";

interface CesiumScenarioMapProps {
  game: Game;
  mobileView: boolean;
  embedded?: boolean;
  showToolbar?: boolean;
  showRoutes?: boolean;
  showRanges?: boolean;
  baseLayer?: CesiumBaseLayerKey;
  onBaseLayerChange?: (key: CesiumBaseLayerKey) => void;
  sceneMode?: CesiumSceneModeKey;
  onSceneModeChange?: (mode: CesiumSceneModeKey) => void;
  placement?: CesiumPlacement | null;
  missionCreatorOpen?: boolean;
  missionEditorMissionId?: string | null;
  onMissionCreatorOpenChange?: (open: boolean) => void;
  onMissionEditorMissionIdChange?: (missionId: string | null) => void;
  onPlacementChange?: (placement: CesiumPlacement | null) => void;
  onScenarioMutation?: () => void;
  onPlay?: () => void | Promise<void>;
  onPause?: () => void | Promise<void>;
  onStep?: () => void | Promise<void>;
  onReset?: () => void | Promise<void>;
  runtimeVisibility?: RuntimeVisibility | null;
  onDeployUnit?: (unit: RuntimeDeployUnitRequest) => void | Promise<void>;
  onDeleteUnit?: (
    unitType: RuntimeUnitType,
    unitId: string
  ) => void | Promise<void>;
  onMoveUnit?: (
    unitType: "aircraft" | "ship",
    unitId: string,
    route: number[][]
  ) => void | Promise<void>;
  onSetUnitPosition?: (
    position: RuntimeSetUnitPositionRequest
  ) => void | Promise<void>;
  onUpdateUnit?: (update: RuntimeUpdateUnitRequest) => void | Promise<void>;
  onCreatePatrolMission?: (
    name: string,
    assignedUnitIds: string[],
    referencePointIds: string[]
  ) => void | Promise<void>;
  onCreateStrikeMission?: (
    name: string,
    assignedUnitIds: string[],
    assignedTargetIds: string[]
  ) => void | Promise<void>;
  onUpdatePatrolMission?: (
    missionId: string,
    name: string,
    assignedUnitIds: string[],
    referencePointIds: string[]
  ) => void | Promise<void>;
  onUpdateStrikeMission?: (
    missionId: string,
    name: string,
    assignedUnitIds: string[],
    assignedTargetIds: string[]
  ) => void | Promise<void>;
  onDeleteMission?: (missionId: string) => void | Promise<void>;
  onAddWeapon?: (weapon: RuntimeAddWeaponRequest) => void | Promise<void>;
  onDeleteWeapon?: (weapon: RuntimeDeleteWeaponRequest) => void | Promise<void>;
  onUpdateWeaponQuantity?: (
    weapon: RuntimeUpdateWeaponQuantityRequest
  ) => void | Promise<void>;
}

// Reserved legacy rail width when non-embedded callers still offset content.
const TOOLBAR_WIDTH = 240;
const OBSTACLE_TEMPLATES = [
  {
    className: "禁行区",
    obstacleType: "no_go",
    radiusNm: 15,
    movementPenalty: 1,
    detectionPenalty: 0,
    communicationPenalty: 0,
  },
  {
    className: "复杂地形区",
    obstacleType: "terrain",
    radiusNm: 20,
    movementPenalty: 0.45,
    detectionPenalty: 0.2,
    communicationPenalty: 0.1,
  },
  {
    className: "恶劣天气区",
    obstacleType: "weather",
    radiusNm: 25,
    movementPenalty: 0.25,
    detectionPenalty: 0.35,
    communicationPenalty: 0.15,
  },
  {
    className: "雷达遮蔽区",
    obstacleType: "sensor_shadow",
    radiusNm: 18,
    movementPenalty: 0,
    detectionPenalty: 0.55,
    communicationPenalty: 0.1,
  },
] as const;
const obstacleLabels = Object.fromEntries(
  OBSTACLE_TEMPLATES.map((item) => [item.className, item.className])
);

// approximate OL zoom <-> Cesium altitude (meters) conversion
const EARTH_CIRCUMFERENCE_M = 40075016.686;
const olZoomToAltitude = (zoom: number) =>
  EARTH_CIRCUMFERENCE_M / Math.pow(2, zoom);
const altitudeToOlZoom = (altitude: number) =>
  altitude > 0 ? Math.log2(EARTH_CIRCUMFERENCE_M / altitude) : 0;

function toRuntimeUnitType(unitType: ScenarioUnit["type"]): RuntimeUnitType {
  return unitType === "referencePoint" ? "reference_point" : unitType;
}

function canPlotUnitRoute(
  unitType: ScenarioUnit["type"]
): unitType is "aircraft" | "ship" {
  return unitType === "aircraft" || unitType === "ship";
}

function canCarryWeapons(
  unitType: ScenarioUnit["type"]
): unitType is "aircraft" | "ship" | "facility" {
  return (
    unitType === "aircraft" || unitType === "ship" || unitType === "facility"
  );
}

function canBeObjective(unitType: ScenarioUnit["type"]) {
  return (
    unitType === "aircraft" ||
    unitType === "ship" ||
    unitType === "facility" ||
    unitType === "airbase"
  );
}

// Cesium Ion access token. Provide via client/.env -> VITE_CESIUM_ION_TOKEN=<your-token>
const ionToken = import.meta.env.VITE_CESIUM_ION_TOKEN ?? "";
if (ionToken) {
  Ion.defaultAccessToken = ionToken;
}

const DEFAULT_SATELLITE_TILE_URL =
  "https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}";
const SATELLITE_TILE_URL =
  (
    import.meta.env.VITE_CESIUM_SATELLITE_TILE_URL as string | undefined
  )?.trim() || DEFAULT_SATELLITE_TILE_URL;
const DEFAULT_SATELLITE_MAXIMUM_LEVEL = 16;

function parseImageryMaximumLevel(value: string | undefined, fallback: number) {
  const parsed = Number.parseInt(value?.trim() ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

const SATELLITE_MAXIMUM_LEVEL = parseImageryMaximumLevel(
  import.meta.env.VITE_CESIUM_SATELLITE_MAX_LEVEL as string | undefined,
  DEFAULT_SATELLITE_MAXIMUM_LEVEL
);

// Base-layer URL templates. All four are reachable without tokens.
// `lightVector` = Gaode (Amap) vector w/ Chinese labels.
// `darkMatter`  = CartoDB Dark Matter raster (tactical / night ops).
// `satellite`   = Gaode satellite raster, clamped to z16 by default because
//                 some sea areas return placeholder tiles at z17+.
// `sentinel`    = EOX Sentinel-2 cloudless (open ESA Copernicus data, free,
//                 no key, global mid-res true-color, slightly slower in CN).
function imageryProviderFor(
  key: CesiumBaseLayerKey
): UrlTemplateImageryProvider {
  switch (key) {
    case "lightVector":
      return new UrlTemplateImageryProvider({
        url: "https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}",
        subdomains: ["1", "2", "3", "4"],
        maximumLevel: 18,
      });
    case "darkMatter":
      return new UrlTemplateImageryProvider({
        url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        subdomains: ["a", "b", "c", "d"],
        maximumLevel: 19,
      });
    case "satellite":
      return new UrlTemplateImageryProvider({
        url: SATELLITE_TILE_URL,
        subdomains: ["1", "2", "3", "4"],
        maximumLevel: SATELLITE_MAXIMUM_LEVEL,
      });
    case "sentinel":
      return new UrlTemplateImageryProvider({
        url: "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg",
        maximumLevel: 14,
      });
  }
}

const RUNTIME_ACTION_LABELS = {
  addWeapon: "添加武器",
  clearRoute: "清除航线",
  createPatrolMission: "创建巡逻任务",
  createStrikeMission: "创建打击任务",
  deleteMission: "删除任务",
  deleteUnit: "删除单位",
  deleteWeapon: "删除武器",
  deployUnit: "部署单位",
  moveUnit: "移动单位",
  planRoute: "规划航线",
  submitRoute: "提交航线",
  updatePatrolMission: "更新巡逻任务",
  updateStrikeMission: "更新打击任务",
  updateUnit: "更新单位",
  updateWeaponQuantity: "更新武器数量",
} as const;

type RuntimeActionKey = keyof typeof RUNTIME_ACTION_LABELS;

export default function CesiumScenarioMap({
  game,
  mobileView,
  embedded = false,
  showToolbar = false,
  showRoutes = true,
  showRanges = true,
  baseLayer: controlledBaseLayer,
  onBaseLayerChange,
  sceneMode: controlledSceneMode,
  onSceneModeChange,
  placement: controlledPlacement,
  missionCreatorOpen,
  missionEditorMissionId,
  onMissionCreatorOpenChange,
  onMissionEditorMissionIdChange,
  onPlacementChange,
  onScenarioMutation,
  onPlay,
  onPause,
  onStep,
  onReset,
  runtimeVisibility = null,
  onDeployUnit,
  onDeleteUnit,
  onMoveUnit,
  onSetUnitPosition,
  onUpdateUnit,
  onCreatePatrolMission,
  onCreateStrikeMission,
  onUpdatePatrolMission,
  onUpdateStrikeMission,
  onDeleteMission,
  onAddWeapon,
  onDeleteWeapon,
  onUpdateWeaponQuantity,
}: Readonly<CesiumScenarioMapProps>) {
  const { t } = useTranslation();
  // Localized className -> label dictionaries for the right-click add-unit
  // cascade submenu. The i18n key separator is `.`, and many real-world
  // classNames contain dots / slashes (e.g. `F/A-18 Hornet`), so we fetch the
  // whole bag via `returnObjects` and index by the literal className. Missing
  // entries gracefully fall back to the original English className.
  const aircraftLabels = (t("unitClass.aircraft", {
    returnObjects: true,
    defaultValue: {},
  }) || {}) as Record<string, string>;
  const shipLabels = (t("unitClass.ship", {
    returnObjects: true,
    defaultValue: {},
  }) || {}) as Record<string, string>;
  const facilityLabels = (t("unitClass.facility", {
    returnObjects: true,
    defaultValue: {},
  }) || {}) as Record<string, string>;
  const labelFromDict = (dict: Record<string, string>) => (opt: string) =>
    dict[opt] ?? opt;
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const entitiesRef = useRef<CesiumScenarioEntities | null>(null);
  const setCurrentMouseMapCoordinatesToContext = useContext(
    SetMouseMapCoordinatesContext
  );
  const setCurrentScenarioTimeToContext = useContext(SetScenarioTimeContext);
  // The unit popup is React-owned, but selection lives inside the controller
  // so it can re-skin the billboard during sync. We mirror the typed unit here
  // for rendering convenience; the controller is the source of truth for ids.
  const [selectedUnit, setSelectedUnit] = useState<ScenarioUnit | null>(null);
  const selectedUnitRef = useRef<ScenarioUnit | null>(null);
  selectedUnitRef.current = selectedUnit;
  // Toolbar-driven state. baseLayer + placement live in React so re-renders
  // update the toolbar UI; refs mirror them for the long-lived Cesium effect.
  const [internalBaseLayer, setInternalBaseLayer] =
    useState<CesiumBaseLayerKey>("satellite");
  const baseLayer = controlledBaseLayer ?? internalBaseLayer;
  const setBaseLayer = useCallback(
    (nextBaseLayer: CesiumBaseLayerKey) => {
      if (onBaseLayerChange) {
        onBaseLayerChange(nextBaseLayer);
        return;
      }
      setInternalBaseLayer(nextBaseLayer);
    },
    [onBaseLayerChange]
  );
  // 2D / 3D scene morph state. Cesium uses SceneMode.SCENE2D / SCENE3D; we
  // mirror to React state so the floating top toolbar can highlight the
  // active button without subscribing to scene events.
  const [is3D, setIs3D] = useState(controlledSceneMode === "3d");
  const activeSceneMode: CesiumSceneModeKey =
    controlledSceneMode ?? (is3D ? "3d" : "2d");
  const [internalPlacement, setInternalPlacement] =
    useState<CesiumPlacement | null>(null);
  const placementIsControlled = controlledPlacement !== undefined;
  const placement =
    (placementIsControlled ? controlledPlacement : internalPlacement) ?? null;
  const placementRef = useRef<CesiumPlacement | null>(null);
  placementRef.current = placement;
  const setPlacement = useCallback(
    (nextPlacement: CesiumPlacement | null) => {
      placementRef.current = nextPlacement;
      if (placementIsControlled) {
        onPlacementChange?.(nextPlacement);
        return;
      }
      setInternalPlacement(nextPlacement);
    },
    [onPlacementChange, placementIsControlled]
  );
  // Tick bumped after any toolbar-driven game mutation so the toolbar (which
  // reads game.currentScenario.sides etc. imperatively) re-renders.
  const [scenarioTick, setScenarioTick] = useState(0);
  const bumpScenario = useCallback(() => {
    setScenarioTick((n) => n + 1);
    onScenarioMutation?.();
  }, [onScenarioMutation]);
  const reportRuntimeUnavailable = useCallback((action: RuntimeActionKey) => {
    const label = RUNTIME_ACTION_LABELS[action];
    console.error(`[AICC] runtime handler missing: ${action}`);
    window.alert(`后端仿真接口未就绪，无法${label}。请刷新页面后重试。`);
  }, []);
  const reportRuntimeFailure = useCallback(
    (action: RuntimeActionKey, err: unknown) => {
      const label = RUNTIME_ACTION_LABELS[action];
      console.error(`[AICC] runtime ${action} failed:`, err);
      window.alert(`${label}失败，请检查后端服务后重试。`);
    },
    []
  );

  // Interaction state. Refs so the long-lived Cesium event handlers can read
  // / mutate without re-binding on every React render.
  const dragRef = useRef<{
    unitId: string;
    type: ScenarioUnit["type"];
    latitude?: number;
    longitude?: number;
  } | null>(null);
  // Click-to-plot route mode. Active when the user pressed "Plot Route" on
  // the unit card; LEFT_CLICK on the map adds a waypoint, LEFT_DOUBLE_CLICK
  // commits, Esc cancels. Mirrored to React state for UI feedback (button
  // toggles between "Plot Route" / "Finish Route").
  const routePlotRef = useRef<{
    unitId: string;
    type: "aircraft" | "ship";
  } | null>(null);
  const [routePlotting, setRoutePlotting] = useState<string | null>(null);
  const routeEntityRef = useRef<Entity | null>(null);

  // Right-click context menu state. Two modes:
  //  - "unit": right-clicked on an existing unit -> select / clearRoute / delete
  //  - "add":  right-clicked on empty terrain   -> drop a new unit at lat/lon
  const [contextMenu, setContextMenu] = useState<
    | {
        kind: "unit";
        screenX: number;
        screenY: number;
        unit: ScenarioUnit;
      }
    | {
        kind: "add";
        screenX: number;
        screenY: number;
        lat: number;
        lon: number;
      }
    | null
  >(null);
  const [unitContextView, setUnitContextView] = useState<"actions" | "weapons">(
    "actions"
  );

  // Mission creator dialog (Patrol / Strike). Tactical layout can control this
  // from its sidebar; legacy map toolbar falls back to local state.
  const [internalMissionCreatorOpen, setInternalMissionCreatorOpen] =
    useState(false);
  const missionCreatorVisible =
    missionCreatorOpen ?? internalMissionCreatorOpen;
  const setMissionCreatorVisible = useCallback(
    (open: boolean) => {
      if (onMissionCreatorOpenChange) {
        onMissionCreatorOpenChange(open);
      } else {
        setInternalMissionCreatorOpen(open);
      }
    },
    [onMissionCreatorOpenChange]
  );
  const [internalMissionEditorMissionId, setInternalMissionEditorMissionId] =
    useState<string | null>(null);
  const visibleMissionEditorMissionId =
    missionEditorMissionId ?? internalMissionEditorMissionId;
  const setVisibleMissionEditorMissionId = useCallback(
    (missionId: string | null) => {
      if (onMissionEditorMissionIdChange) {
        onMissionEditorMissionIdChange(missionId);
      } else {
        setInternalMissionEditorMissionId(missionId);
      }
    },
    [onMissionEditorMissionIdChange]
  );

  // Second-stage menu shown after the user picks "Add Aircraft / Ship / ..."
  // in the right-click add menu. Lets them pick a concrete className from the
  // unit db before dropping the unit.
  const [classChooser, setClassChooser] = useState<{
    anchorEl: HTMLElement;
    options: string[];
    // Optional localized label for each option. The original `className`
    // (the `options` entry) is still passed to `onPick` so db lookups keep
    // working — only the displayed text is translated.
    labelOf?: (option: string) => string;
    onPick: (className: string) => void;
  } | null>(null);

  // Eraser / God mode are owned by Game; we mirror to bumpScenario when toggled
  // so the toolbar refresh picks up the active highlight.
  const toggleEraser = useCallback(() => {
    game.toggleEraserMode();
    bumpScenario();
  }, [game, bumpScenario]);
  const toggleGodMode = useCallback(() => {
    game.toggleGodMode();
    bumpScenario();
  }, [game, bumpScenario]);

  // Plot a fresh route for the given unit: clears any prior desiredRoute,
  // arms click-to-plot mode, and installs a live polyline preview.
  const startPlotRoute = useCallback(
    (unitId: string, type: "aircraft" | "ship") => {
      if (!onMoveUnit) {
        reportRuntimeUnavailable("planRoute");
        return;
      }
      const viewer = viewerRef.current;
      if (!viewer) return;
      // Clear existing desiredRoute so the user plots from scratch starting
      // at the unit's current position (matches OL behaviour).
      const u =
        type === "aircraft"
          ? game.currentScenario.getAircraft(unitId)
          : game.currentScenario.getShip(unitId);
      if (u) {
        u.desiredRoute = [];
      }
      // Remove any leftover preview polyline.
      if (routeEntityRef.current) {
        viewer.entities.remove(routeEntityRef.current);
        routeEntityRef.current = null;
      }
      routePlotRef.current = { unitId, type };
      setRoutePlotting(unitId);
      viewer.canvas.style.cursor = "crosshair";

      // Live preview: from unit pos through every desiredRoute waypoint.
      const scen = game.currentScenario;
      const sideColor = u?.sideColor || "#ffff00";
      routeEntityRef.current = viewer.entities.add({
        polyline: {
          positions: new CallbackProperty(() => {
            const cur =
              type === "aircraft"
                ? scen.getAircraft(unitId)
                : scen.getShip(unitId);
            if (!cur) return [];
            const pts: Cartesian3[] = [
              Cartesian3.fromDegrees(cur.longitude, cur.latitude),
            ];
            for (const [la, lo] of cur.desiredRoute) {
              pts.push(Cartesian3.fromDegrees(lo, la));
            }
            return pts;
          }, false),
          width: 2,
          material: new PolylineDashMaterialProperty({
            color: Color.fromCssColorString(sideColor),
            dashLength: 12,
          }),
        },
      });
    },
    [game, onMoveUnit, reportRuntimeUnavailable]
  );

  const cancelPlotRoute = useCallback(() => {
    const viewer = viewerRef.current;
    const plot = routePlotRef.current;
    if (plot) {
      const u =
        plot.type === "aircraft"
          ? game.currentScenario.getAircraft(plot.unitId)
          : game.currentScenario.getShip(plot.unitId);
      if (u) u.desiredRoute = [];
    }
    if (viewer && routeEntityRef.current) {
      viewer.entities.remove(routeEntityRef.current);
      routeEntityRef.current = null;
    }
    if (viewer) viewer.canvas.style.cursor = "";
    routePlotRef.current = null;
    setRoutePlotting(null);
    bumpScenario();
  }, [game, bumpScenario]);

  const clearUnitRoute = useCallback(
    (unitId: string, type: "aircraft" | "ship") => {
      if (!onMoveUnit) {
        reportRuntimeUnavailable("clearRoute");
        return;
      }
      void Promise.resolve(onMoveUnit(type, unitId, [])).catch((err) => {
        reportRuntimeFailure("clearRoute", err);
      });
    },
    [onMoveUnit, reportRuntimeFailure, reportRuntimeUnavailable]
  );

  // Esc to cancel plot mode or any pending placement.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (routePlotRef.current) {
        cancelPlotRoute();
        return;
      }
      if (placementRef.current) {
        placementRef.current = null;
        setPlacement(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [cancelPlotRoute, setPlacement]);
  // keep latest values reachable from one-shot effect without re-running it
  const gameRef = useRef(game);
  const setCoordsRef = useRef(setCurrentMouseMapCoordinatesToContext);
  const setScenarioTimeRef = useRef(setCurrentScenarioTimeToContext);
  const showRoutesRef = useRef(showRoutes);
  const showRangesRef = useRef(showRanges);
  const runtimeVisibilityRef = useRef<RuntimeVisibility | null>(
    runtimeVisibility
  );
  const deployUnitRef = useRef(onDeployUnit);
  const deleteUnitRef = useRef(onDeleteUnit);
  const moveUnitRef = useRef(onMoveUnit);
  const setUnitPositionRef = useRef(onSetUnitPosition);
  const updateUnitRef = useRef(onUpdateUnit);
  gameRef.current = game;
  setCoordsRef.current = setCurrentMouseMapCoordinatesToContext;
  setScenarioTimeRef.current = setCurrentScenarioTimeToContext;
  showRoutesRef.current = showRoutes;
  showRangesRef.current = showRanges;
  runtimeVisibilityRef.current = runtimeVisibility;
  deployUnitRef.current = onDeployUnit;
  deleteUnitRef.current = onDeleteUnit;
  moveUnitRef.current = onMoveUnit;
  setUnitPositionRef.current = onSetUnitPosition;
  updateUnitRef.current = onUpdateUnit;

  const resolveScenarioUnit = useCallback(
    (current: ScenarioUnit): ScenarioUnit | null => {
      const scenario = game.currentScenario;
      const unit =
        current.type === "aircraft"
          ? scenario.getAircraft(current.unit.id)
          : current.type === "ship"
            ? scenario.getShip(current.unit.id)
            : current.type === "facility"
              ? scenario.getFacility(current.unit.id)
              : current.type === "airbase"
                ? scenario.getAirbase(current.unit.id)
                : current.type === "obstacle"
                  ? scenario.getObstacle(current.unit.id)
                  : scenario.getReferencePoint(current.unit.id);
      if (!unit) return null;
      return { ...current, unit } as ScenarioUnit;
    },
    [game]
  );

  const refreshSelectedUnitFromScenario = useCallback(() => {
    const current = selectedUnitRef.current;
    if (!current) return;
    const next = resolveScenarioUnit(current);
    if (!next) {
      entitiesRef.current?.setSelected(null);
      selectedUnitRef.current = null;
      setSelectedUnit(null);
      return;
    }
    selectedUnitRef.current = next;
    setSelectedUnit(next);
  }, [resolveScenarioUnit]);

  const refreshContextUnitFromScenario = useCallback(() => {
    setContextMenu((current) => {
      if (current?.kind !== "unit") return current;
      const next = resolveScenarioUnit(current.unit);
      return next ? { ...current, unit: next } : null;
    });
  }, [resolveScenarioUnit]);

  const applyRuntimeUpdateUnit = useCallback(
    async (update: RuntimeUpdateUnitRequest) => {
      if (!onUpdateUnit) {
        reportRuntimeUnavailable("updateUnit");
        return;
      }
      try {
        await onUpdateUnit(update);
        refreshSelectedUnitFromScenario();
      } catch (err) {
        reportRuntimeFailure("updateUnit", err);
      }
    },
    [
      onUpdateUnit,
      refreshSelectedUnitFromScenario,
      reportRuntimeFailure,
      reportRuntimeUnavailable,
    ]
  );

  const toggleObjectiveForUnit = useCallback(
    (unit: ScenarioUnit) => {
      if (!canBeObjective(unit.type)) return;
      const s = game.currentScenario;
      const currentUnit =
        unit.type === "aircraft"
          ? s.getAircraft(unit.unit.id)
          : unit.type === "ship"
            ? s.getShip(unit.unit.id)
            : unit.type === "facility"
              ? s.getFacility(unit.unit.id)
              : s.getAirbase(unit.unit.id);
      if (!currentUnit) return;
      void applyRuntimeUpdateUnit({
        unit_type: toRuntimeUnitType(unit.type),
        unit_id: unit.unit.id,
        patch: { is_objective: !currentUnit.isObjective },
      });
    },
    [applyRuntimeUpdateUnit, game]
  );

  const toggleRoutePlotForUnit = useCallback(
    (unit: ScenarioUnit) => {
      if (!canPlotUnitRoute(unit.type)) return;
      if (routePlotRef.current?.unitId === unit.unit.id) {
        const plot = routePlotRef.current;
        const u =
          plot.type === "aircraft"
            ? game.currentScenario.getAircraft(plot.unitId)
            : game.currentScenario.getShip(plot.unitId);
        if (u && u.desiredRoute.length > 0) {
          const route = u.desiredRoute.map(([latitude, longitude]) => [
            latitude,
            longitude,
          ]);
          if (onMoveUnit) {
            void Promise.resolve(onMoveUnit(plot.type, plot.unitId, route))
              .then(refreshSelectedUnitFromScenario)
              .catch((err) => {
                reportRuntimeFailure("submitRoute", err);
              });
          } else {
            reportRuntimeUnavailable("submitRoute");
          }
        }
        if (viewerRef.current && routeEntityRef.current) {
          viewerRef.current.entities.remove(routeEntityRef.current);
          routeEntityRef.current = null;
        }
        routePlotRef.current = null;
        setRoutePlotting(null);
        if (viewerRef.current) viewerRef.current.canvas.style.cursor = "";
        return;
      }
      startPlotRoute(unit.unit.id, unit.type);
    },
    [
      game,
      onMoveUnit,
      refreshSelectedUnitFromScenario,
      reportRuntimeFailure,
      reportRuntimeUnavailable,
      startPlotRoute,
    ]
  );

  const addWeaponToUnit = useCallback(
    (unit: ScenarioUnit, unitId: string, weaponClassName: string) => {
      if (!canCarryWeapons(unit.type)) return [];
      const tmpl = WeaponDb.find((w) => w.className === weaponClassName);
      if (!tmpl) return [];
      const carrierType = unit.type as RuntimeWeaponCarrierType;
      const s = game.currentScenario;
      const currentUnit =
        unit.type === "aircraft"
          ? s.getAircraft(unitId)
          : unit.type === "ship"
            ? s.getShip(unitId)
            : s.getFacility(unitId);
      if (!onAddWeapon) {
        reportRuntimeUnavailable("addWeapon");
        return currentUnit?.weapons ?? [];
      }
      void Promise.resolve(
        onAddWeapon({
          unit_type: carrierType,
          unit_id: unitId,
          class_name: tmpl.className,
          speed: tmpl.speed,
          max_fuel: tmpl.maxFuel,
          fuel_rate: tmpl.fuelRate,
          range: tmpl.range,
          lethality: tmpl.lethality,
        })
      )
        .then(() => {
          refreshSelectedUnitFromScenario();
          refreshContextUnitFromScenario();
        })
        .catch((err) => {
          reportRuntimeFailure("addWeapon", err);
        });
      return currentUnit?.weapons ?? [];
    },
    [
      game,
      onAddWeapon,
      refreshContextUnitFromScenario,
      refreshSelectedUnitFromScenario,
      reportRuntimeFailure,
      reportRuntimeUnavailable,
    ]
  );

  const deleteWeaponFromUnit = useCallback(
    (unit: ScenarioUnit, unitId: string, weaponId: string) => {
      if (!canCarryWeapons(unit.type)) return [];
      const carrierType = unit.type as RuntimeWeaponCarrierType;
      const s = game.currentScenario;
      const currentUnit =
        unit.type === "aircraft"
          ? s.getAircraft(unitId)
          : unit.type === "ship"
            ? s.getShip(unitId)
            : s.getFacility(unitId);
      if (!onDeleteWeapon) {
        reportRuntimeUnavailable("deleteWeapon");
        return currentUnit?.weapons ?? [];
      }
      void Promise.resolve(
        onDeleteWeapon({
          unit_type: carrierType,
          unit_id: unitId,
          weapon_id: weaponId,
        })
      )
        .then(() => {
          refreshSelectedUnitFromScenario();
          refreshContextUnitFromScenario();
        })
        .catch((err) => {
          reportRuntimeFailure("deleteWeapon", err);
        });
      return currentUnit?.weapons ?? [];
    },
    [
      game,
      onDeleteWeapon,
      refreshContextUnitFromScenario,
      refreshSelectedUnitFromScenario,
      reportRuntimeFailure,
      reportRuntimeUnavailable,
    ]
  );

  const updateWeaponQuantityForUnit = useCallback(
    (
      unit: ScenarioUnit,
      unitId: string,
      weaponId: string,
      increment: number
    ) => {
      if (!canCarryWeapons(unit.type)) return [];
      const carrierType = unit.type as RuntimeWeaponCarrierType;
      const s = game.currentScenario;
      const currentUnit =
        unit.type === "aircraft"
          ? s.getAircraft(unitId)
          : unit.type === "ship"
            ? s.getShip(unitId)
            : s.getFacility(unitId);
      if (!onUpdateWeaponQuantity) {
        reportRuntimeUnavailable("updateWeaponQuantity");
        return currentUnit?.weapons ?? [];
      }
      void Promise.resolve(
        onUpdateWeaponQuantity({
          unit_type: carrierType,
          unit_id: unitId,
          weapon_id: weaponId,
          increment,
        })
      )
        .then(() => {
          refreshSelectedUnitFromScenario();
          refreshContextUnitFromScenario();
        })
        .catch((err) => {
          reportRuntimeFailure("updateWeaponQuantity", err);
        });
      return currentUnit?.weapons ?? [];
    },
    [
      game,
      onUpdateWeaponQuantity,
      refreshContextUnitFromScenario,
      refreshSelectedUnitFromScenario,
      reportRuntimeFailure,
      reportRuntimeUnavailable,
    ]
  );

  useEffect(() => {
    if (!containerRef.current) return;
    // mount guard (defensive; StrictMode is also disabled in main.tsx)
    if (viewerRef.current) return;

    const viewer = new Viewer(containerRef.current, {
      baseLayerPicker: false,
      geocoder: false,
      timeline: false,
      animation: false,
      homeButton: false,
      infoBox: false,
      sceneModePicker: false,
      // Start in flat 2D mode by default so legacy users don't see a globe
      // until they explicitly toggle 3D from the floating top toolbar.
      sceneMode:
        activeSceneMode === "3d" ? SceneMode.SCENE3D : SceneMode.SCENE2D,
      mapMode2D: MapMode2D.ROTATE,
      navigationHelpButton: false,
      fullscreenButton: false,
      selectionIndicator: false,
      shouldAnimate: false,
      baseLayer: false as unknown as undefined,
    });
    viewerRef.current = viewer;

    // Initial imagery layer is added by the dedicated baseLayer effect below.

    // Disable optional cosmetic layers that ship with Cesium and would
    // otherwise issue extra HTTP requests (skybox star textures, sun, moon,
    // ground atmosphere). Our 2D-style tactical view doesn't need them, and
    // on flaky networks they trigger ERR_NETWORK_CHANGED noise in the console.
    // Cesium's TS types are incomplete here; cast to any for the toggles.
    const scene = viewer.scene as unknown as {
      skyBox?: { show: boolean };
      sun?: { show: boolean };
      moon?: { show: boolean };
      skyAtmosphere?: { show: boolean };
      globe: { showGroundAtmosphere: boolean; baseColor: Color };
      fog: { enabled: boolean };
      backgroundColor: Color;
    };
    if (scene.skyBox) scene.skyBox.show = false;
    if (scene.sun) scene.sun.show = false;
    if (scene.moon) scene.moon.show = false;
    if (scene.skyAtmosphere) scene.skyAtmosphere.show = false;
    scene.globe.showGroundAtmosphere = false;
    scene.globe.baseColor = Color.fromCssColorString("#101820");
    scene.fog.enabled = false;
    // Solid background color so the canvas is never naked black.
    scene.backgroundColor = Color.fromCssColorString("#0d1117");

    // hide cesium credits container for cleaner UI
    (viewer.cesiumWidget.creditContainer as HTMLElement).style.display = "none";

    // Cesium binds a default LEFT_DOUBLE_CLICK that "tracks" the picked
    // entity (camera flies in). We want double-click to commit a plotted
    // route, so strip the default action up-front.
    viewer.screenSpaceEventHandler.removeInputAction(
      ScreenSpaceEventType.LEFT_DOUBLE_CLICK
    );

    // initial camera position from game.mapView (OL-zoom approximation)
    const initialGame = gameRef.current;
    setScenarioTimeRef.current(initialGame.currentScenario.currentTime);
    const [lon, lat] = initialGame.mapView.currentCameraCenter ?? [120, 20];
    const zoom = initialGame.mapView.currentCameraZoom ?? 5;
    viewer.camera.setView({
      destination: Cartesian3.fromDegrees(lon, lat, olZoomToAltitude(zoom)),
    });

    // Shared utility: screen pos -> lon/lat using the globe ellipsoid.
    const ellipsoid = viewer.scene.globe.ellipsoid;
    const ssHandler = new ScreenSpaceEventHandler(viewer.scene.canvas);

    // Suppress the browser's native context menu on right-click so our React
    // MUI Menu (anchored to cursor) is not occluded. We listen on window in
    // the capture phase and only block when the event originated inside the
    // cesium container (canvas / overlay / popup), to avoid stealing right-
    // click in genuine browser regions like dev-tools panels.
    const preventNativeContextMenu = (e: MouseEvent) => {
      // Unconditionally suppress on the Cesium view; we own the entire screen
      // here and the React MUI Menu replaces the browser native menu.
      // Capture on document ensures we run before React's delegated handlers
      // and any other listener.
      e.preventDefault();
      e.stopPropagation();
    };
    document.addEventListener("contextmenu", preventNativeContextMenu, {
      capture: true,
    });
    window.addEventListener("contextmenu", preventNativeContextMenu, {
      capture: true,
    });
    const screenToLonLat = (pos: Cartesian2): [number, number] | null => {
      const cart = viewer.camera.pickEllipsoid(pos, ellipsoid);
      if (!cart) return null;
      const carto = Cartographic.fromCartesian(cart, ellipsoid);
      return [
        CesiumMath.toDegrees(carto.longitude),
        CesiumMath.toDegrees(carto.latitude),
      ];
    };
    const pickUnit = (pos: Cartesian2) => {
      const picked = viewer.scene.pick(pos) as
        | { id?: { id?: string } }
        | undefined;
      return scenarioEntities.lookupUnit(picked?.id?.id);
    };

    // MOUSE_MOVE: bottom-info coordinate display + active drag / route updates.
    ssHandler.setInputAction((evt: { endPosition: Cartesian2 }) => {
      const ll = screenToLonLat(evt.endPosition);
      if (ll) {
        setCoordsRef.current({ longitude: ll[0], latitude: ll[1] });
      }
      // Drag: teleport the selected unit each move tick.
      const drag = dragRef.current;
      if (drag && ll) {
        gameRef.current.teleportUnit(drag.unitId, ll[1], ll[0]);
        drag.latitude = ll[1];
        drag.longitude = ll[0];
      }
    }, ScreenSpaceEventType.MOUSE_MOVE);

    // camera moveEnd -> sync back to game.mapView (parity with OL moveend handler)
    const removeMoveEnd = viewer.camera.moveEnd.addEventListener(() => {
      const carto = viewer.camera.positionCartographic;
      gameRef.current.mapView.currentCameraCenter = [
        CesiumMath.toDegrees(carto.longitude),
        CesiumMath.toDegrees(carto.latitude),
      ];
      gameRef.current.mapView.currentCameraZoom = altitudeToOlZoom(
        carto.height
      );
    });

    // Render units (aircraft / ship / facility / airbase / referencePoint) as
    // Cesium entities. We poll-diff so backend snapshots and local edit
    // mutations propagate without instrumenting the map renderer.
    const scenarioEntities = new CesiumScenarioEntities(viewer);
    entitiesRef.current = scenarioEntities;
    let syncInFlight = false;
    const syncEntities = () => {
      if (syncInFlight) return;
      syncInFlight = true;
      const currentGame = gameRef.current;
      const runtimeSideVisibility =
        runtimeVisibilityRef.current?.by_side[currentGame.currentSideId] ??
        runtimeVisibilityRef.current?.by_side[
          runtimeVisibilityRef.current.current_side_id
        ] ??
        null;
      scenarioEntities
        .sync(
          currentGame.currentScenario,
          {
            godMode: currentGame.godMode,
            visibleObjectIds: runtimeSideVisibility
              ? new Set(runtimeSideVisibility.visible_object_ids)
              : null,
            operationalDetailObjectIds: runtimeSideVisibility
              ? new Set(runtimeSideVisibility.operational_detail_object_ids)
              : null,
          },
          {
            showRoutes: showRoutesRef.current,
            showRanges: showRangesRef.current,
          }
        )
        .then(() => {
          // If the previously selected unit was deleted from the scenario,
          // controller drops its selectedId; reflect that in React state.
          if (
            scenarioEntities.getSelectedId() === null &&
            selectedUnitRef.current !== null
          ) {
            selectedUnitRef.current = null;
            setSelectedUnit(null);
          }
        })
        .catch((err) => console.error("[Cesium] entity sync failed:", err))
        .finally(() => {
          syncInFlight = false;
        });
    };
    syncEntities();
    const syncIntervalId = window.setInterval(syncEntities, 500);

    // Helper: remove a unit by id, regardless of type. Used by eraser mode and
    // by the right-click context menu's "delete" action.
    const removeUnitById = (unitType: ScenarioUnit["type"], id: string) => {
      const runtimeDelete = deleteUnitRef.current;
      if (!runtimeDelete) {
        reportRuntimeUnavailable("deleteUnit");
        return;
      }
      void Promise.resolve(
        runtimeDelete(toRuntimeUnitType(unitType), id)
      ).catch((err) => {
        reportRuntimeFailure("deleteUnit", err);
      });
    };

    const deployUnitAt = (
      unitType: RuntimeUnitType,
      className: string,
      latitude: number,
      longitude: number,
      name = className
    ) => {
      const runtimeDeploy = deployUnitRef.current;
      if (!runtimeDeploy) {
        reportRuntimeUnavailable("deployUnit");
        return;
      }
      void Promise.resolve(
        runtimeDeploy({
          unit_type: unitType,
          class_name: className,
          latitude,
          longitude,
          name,
        })
      ).catch((err) => {
        reportRuntimeFailure("deployUnit", err);
      });
    };

    const commitRuntimeRoute = (plot: {
      unitId: string;
      type: "aircraft" | "ship";
    }) => {
      const u =
        plot.type === "aircraft"
          ? gameRef.current.currentScenario.getAircraft(plot.unitId)
          : gameRef.current.currentScenario.getShip(plot.unitId);
      if (!u) return;
      const route = u.desiredRoute.map(([latitude, longitude]) => [
        latitude,
        longitude,
      ]);
      const runtimeMove = moveUnitRef.current;
      if (!runtimeMove) {
        reportRuntimeUnavailable("submitRoute");
        return;
      }
      void Promise.resolve(runtimeMove(plot.type, plot.unitId, route)).catch(
        (err) => {
          reportRuntimeFailure("submitRoute", err);
        }
      );
    };

    // LEFT_DOWN: if a unit is hit and we're not placing/erasing/plotting,
    // start a drag session. Disabling the left-button camera control lets
    // the cursor "carry" the unit smoothly without rotating the globe.
    ssHandler.setInputAction((evt: { position: Cartesian2 }) => {
      if (placementRef.current) return;
      if (routePlotRef.current) return;
      if (gameRef.current.eraserMode) return;
      const hit = pickUnit(evt.position);
      if (!hit) return;
      if (!setUnitPositionRef.current) {
        reportRuntimeUnavailable("moveUnit");
        return;
      }
      dragRef.current = { unitId: hit.unit.id, type: hit.type };
      viewer.scene.screenSpaceCameraController.enableRotate = false;
      viewer.scene.screenSpaceCameraController.enableTranslate = false;
      viewer.canvas.style.cursor = "grabbing";
    }, ScreenSpaceEventType.LEFT_DOWN);

    // LEFT_UP: always restore camera and clear drag state.
    ssHandler.setInputAction(() => {
      if (dragRef.current) {
        const drag = dragRef.current;
        if (
          drag.latitude !== undefined &&
          drag.longitude !== undefined &&
          setUnitPositionRef.current
        ) {
          void Promise.resolve(
            setUnitPositionRef.current({
              unit_type: toRuntimeUnitType(drag.type),
              unit_id: drag.unitId,
              latitude: drag.latitude,
              longitude: drag.longitude,
            })
          ).catch((err) => {
            reportRuntimeFailure("moveUnit", err);
          });
        }
        dragRef.current = null;
        viewer.scene.screenSpaceCameraController.enableRotate = true;
        viewer.scene.screenSpaceCameraController.enableTranslate = true;
        viewer.canvas.style.cursor = placementRef.current ? "crosshair" : "";
      }
    }, ScreenSpaceEventType.LEFT_UP);

    // LEFT_CLICK: placement / route plot / eraser / select. Order matters:
    // route-plot mode wins over selection so clicking on map adds a waypoint.
    ssHandler.setInputAction((evt: { position: Cartesian2 }) => {
      // Route plotting: each click adds a waypoint to the unit's
      // desiredRoute; the live polyline renders via the CallbackProperty
      // installed when plotting started.
      const plot = routePlotRef.current;
      if (plot) {
        const ll = screenToLonLat(evt.position);
        if (!ll) return;
        if (plot.type === "aircraft") {
          gameRef.current.moveAircraft(plot.unitId, ll[1], ll[0]);
        } else {
          gameRef.current.moveShip(plot.unitId, ll[1], ll[0]);
        }
        return;
      }
      const place = placementRef.current;
      if (place) {
        const ll = screenToLonLat(evt.position);
        if (!ll) return;
        const [lon2, lat2] = ll;
        const cls = place.className ?? place.type;
        deployUnitAt(toRuntimeUnitType(place.type), cls, lat2, lon2);
        placementRef.current = null;
        setPlacement(null);
        return;
      }
      const found = pickUnit(evt.position);
      // Eraser: click on unit deletes it; click on empty clears selection.
      if (gameRef.current.eraserMode) {
        if (found) {
          removeUnitById(found.type, found.unit.id);
          if (selectedUnitRef.current?.unit.id === found.unit.id) {
            scenarioEntities.setSelected(null);
            selectedUnitRef.current = null;
            setSelectedUnit(null);
          }
        }
        return;
      }
      if (found) {
        scenarioEntities.setSelected(found.unit.id);
        selectedUnitRef.current = found;
        setSelectedUnit(found);
      } else {
        scenarioEntities.setSelected(null);
        selectedUnitRef.current = null;
        setSelectedUnit(null);
      }
    }, ScreenSpaceEventType.LEFT_CLICK);

    // RIGHT_CLICK: open a context menu. Two modes by hit-test:
    //  - hit a unit  -> auto-select + unit action menu (Clear Route / Delete)
    //  - empty map   -> add-unit menu at the picked lon/lat
    // We use RIGHT_CLICK rather than RIGHT_DOWN/UP because some browser /
    // extension setups (mouse-gesture extensions) intercept right-button drag
    // events; RIGHT_CLICK fires after a clean right-click and is reliable.
    ssHandler.setInputAction((evt: { position: Cartesian2 }) => {
      if (placementRef.current) return;
      if (routePlotRef.current) return;
      // Always clear any leftover cascade submenu when (re)opening the
      // first-stage context menu, so it doesn't appear unanchored next to
      // a freshly opened menu at a different screen location.
      setClassChooser(null);
      setUnitContextView("actions");
      // Cesium gives canvas-local coordinates; MUI Menu anchorPosition is
      // viewport-based (position: fixed). When embedded in the tactical
      // layout, the canvas is offset by the left sidebar, so we must add
      // the canvas's bounding-rect origin to get correct cursor anchoring.
      const rect = viewer.canvas.getBoundingClientRect();
      const viewportX = evt.position.x + rect.left;
      const viewportY = evt.position.y + rect.top;
      const hit = pickUnit(evt.position);
      if (hit) {
        // 右键命中单位即选中：与常见 GIS 工具一致，同时弹出
        // CesiumUnitInfoCard，免去菜单上与左键点击冲突的「选中」冲突项。
        entitiesRef.current?.setSelected(hit.unit.id);
        selectedUnitRef.current = hit;
        setSelectedUnit(hit);
        setContextMenu({
          kind: "unit",
          screenX: viewportX,
          screenY: viewportY,
          unit: hit,
        });
        return;
      }
      const ll = screenToLonLat(evt.position);
      if (!ll) return;
      setContextMenu({
        kind: "add",
        screenX: viewportX,
        screenY: viewportY,
        lat: ll[1],
        lon: ll[0],
      });
    }, ScreenSpaceEventType.RIGHT_CLICK);

    // LEFT_DOUBLE_CLICK: commit a click-plotted route. Default behaviour is
    // zoom-to which we explicitly suppress when a route is being plotted.
    ssHandler.setInputAction(() => {
      const plot = routePlotRef.current;
      if (!plot) return;
      const u =
        plot.type === "aircraft"
          ? gameRef.current.currentScenario.getAircraft(plot.unitId)
          : gameRef.current.currentScenario.getShip(plot.unitId);
      if (u && u.desiredRoute.length > 0) {
        commitRuntimeRoute(plot);
      }
      if (routeEntityRef.current) {
        viewer.entities.remove(routeEntityRef.current);
        routeEntityRef.current = null;
      }
      routePlotRef.current = null;
      setRoutePlotting(null);
      viewer.canvas.style.cursor = "";
    }, ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

    return () => {
      window.clearInterval(syncIntervalId);
      scenarioEntities.destroy();
      entitiesRef.current = null;
      ssHandler.destroy();
      document.removeEventListener("contextmenu", preventNativeContextMenu, {
        capture: true,
      } as EventListenerOptions);
      window.removeEventListener("contextmenu", preventNativeContextMenu, {
        capture: true,
      } as EventListenerOptions);
      removeMoveEnd();
      viewer.destroy();
      viewerRef.current = null;
    };
    // intentionally empty deps: viewer is a one-shot heavy GPU resource; latest
    // props are read via gameRef / setCoordsRef updated each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const viewer = viewerRef.current;
    const nextIs3D = activeSceneMode === "3d";
    setIs3D(nextIs3D);
    onSceneModeChange?.(activeSceneMode);
    if (!viewer) return;
    if (nextIs3D && viewer.scene.mode !== SceneMode.SCENE3D) {
      viewer.scene.morphTo3D(0.6);
    }
    if (!nextIs3D && viewer.scene.mode !== SceneMode.SCENE2D) {
      viewer.scene.morphTo2D(0.6);
    }
  }, [activeSceneMode, onSceneModeChange]);

  // Replace the imagery layer whenever the user picks a new base map.
  // We add the new layer first, fade alpha 0 -> 1 over ~300ms, then drop the
  // older layers. This avoids a sub-second white flash from removeAll().
  useEffect(() => {
    const FADE_MS = 300;
    const applyLayer = () => {
      const v = viewerRef.current;
      if (!v) return;
      const layers = v.imageryLayers;
      const newLayer = layers.addImageryProvider(imageryProviderFor(baseLayer));
      // Some Cesium versions set alpha via direct property; fall back to 1.
      try {
        newLayer.alpha = 0;
      } catch {
        /* noop */
      }
      const start = performance.now();
      const tick = (now: number) => {
        const k = Math.min(1, (now - start) / FADE_MS);
        try {
          newLayer.alpha = k;
        } catch {
          /* noop */
        }
        if (k < 1) {
          requestAnimationFrame(tick);
        } else {
          // Remove every layer that is not the freshly added one.
          // length-mutates while we iterate, so go from the bottom.
          for (let i = layers.length - 1; i >= 0; i--) {
            const l = layers.get(i);
            if (l !== newLayer) layers.remove(l, true);
          }
        }
      };
      requestAnimationFrame(tick);
    };
    if (!viewerRef.current) {
      // First mount: viewer is created in the same render pass; defer once.
      Promise.resolve().then(applyLayer);
      return;
    }
    applyLayer();
  }, [baseLayer]);

  // Crosshair cursor + Esc-to-cancel while a placement is active.
  useEffect(() => {
    const viewer = viewerRef.current;
    const canvas = viewer?.cesiumWidget?.canvas as
      | HTMLCanvasElement
      | undefined;
    if (!placement) {
      if (canvas) canvas.style.cursor = "";
      return;
    }
    if (canvas) canvas.style.cursor = "crosshair";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        placementRef.current = null;
        setPlacement(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      if (canvas) canvas.style.cursor = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [placement, setPlacement]);

  const handleClosePopup = () => {
    entitiesRef.current?.setSelected(null);
    selectedUnitRef.current = null;
    setSelectedUnit(null);
  };

  return (
    <>
      <div
        ref={containerRef}
        id="cesium-map"
        style={{
          position: embedded ? "absolute" : "fixed",
          top: 0,
          left: showToolbar && !embedded ? TOOLBAR_WIDTH : 0,
          right: 0,
          bottom: 0,
        }}
      />
      <div
        id="cesium-overlay"
        style={{
          // No zIndex here: a non-auto z-index on this wrapper would create
          // a stacking context and trap MUI Menu / Popper portals (rendered
          // into <body>) below the toolbar. The cesium-map sibling above
          // has fixed positioning at the same z-level; DOM order keeps this
          // overlay rendered on top of the canvas naturally.
          position: embedded ? "absolute" : "fixed",
          inset: 0,
          pointerEvents: "none",
        }}
      >
        <div style={{ pointerEvents: "auto" }}>
          <BottomInfoDisplay mobileView={mobileView} />
        </div>
        {selectedUnit && (
          <div
            data-testid="cesium-unit-popup"
            style={{
              pointerEvents: "auto",
              position: embedded ? "absolute" : "fixed",
              top: 16,
              left: (showToolbar && !embedded ? TOOLBAR_WIDTH : 0) + 12,
              zIndex: 20000,
            }}
          >
            <CesiumUnitInfoCard
              selection={selectedUnit}
              scenario={game.currentScenario}
              onClose={handleClosePopup}
            />
          </div>
        )}
      </div>
      {/* Right-click context menu, anchored to the cursor's screen position. */}
      <Menu
        open={Boolean(contextMenu)}
        onClose={() => {
          setContextMenu(null);
          setClassChooser(null);
          setUnitContextView("actions");
        }}
        anchorReference="anchorPosition"
        anchorPosition={
          contextMenu
            ? { top: contextMenu.screenY + 8, left: contextMenu.screenX + 8 }
            : undefined
        }
        slotProps={{
          paper: {
            sx: {
              minWidth:
                contextMenu?.kind === "unit" && unitContextView === "weapons"
                  ? 560
                  : 180,
              maxWidth: "calc(100vw - 24px)",
            },
          },
        }}
      >
        {contextMenu?.kind === "unit" &&
          unitContextView === "weapons" &&
          canCarryWeapons(contextMenu.unit.type) && (
            <Box
              sx={{
                width: 540,
                maxWidth: "calc(100vw - 40px)",
                backgroundColor: "#282c34",
                color: "white",
                p: 1,
              }}
            >
              <ListSubheader
                disableSticky
                sx={{
                  bgcolor: "transparent",
                  color: "#cfd8dc",
                  lineHeight: "28px",
                  px: 0.5,
                }}
              >
                {t("toolbar.weapons.title")} ·{" "}
                {localizeUnitName(contextMenu.unit.unit.name)}
              </ListSubheader>
              <WeaponTable
                unitWithWeapon={
                  contextMenu.unit.unit as Aircraft | Ship | Facility
                }
                handleAddWeapon={(unitId, cls) =>
                  addWeaponToUnit(contextMenu.unit, unitId, cls)
                }
                handleDeleteWeapon={(unitId, weaponId) =>
                  deleteWeaponFromUnit(contextMenu.unit, unitId, weaponId)
                }
                handleUpdateWeaponQuantity={(unitId, weaponId, inc) =>
                  updateWeaponQuantityForUnit(
                    contextMenu.unit,
                    unitId,
                    weaponId,
                    inc
                  )
                }
                handleCloseOnMap={() => {
                  setContextMenu(null);
                  setUnitContextView("actions");
                }}
              />
              <MenuItem
                onClick={() => setUnitContextView("actions")}
                sx={{
                  mt: 1,
                  borderRadius: 1,
                  color: "white",
                  justifyContent: "center",
                }}
              >
                {t("toolbar.weapons.back")}
              </MenuItem>
            </Box>
          )}
        {contextMenu?.kind === "unit" && unitContextView === "actions" && (
          <ListSubheader sx={{ lineHeight: "28px", fontSize: 11 }}>
            {t("toolbar.context.title")} ·{" "}
            {localizeUnitName(contextMenu.unit.unit.name)}
          </ListSubheader>
        )}
        {contextMenu?.kind === "unit" &&
          unitContextView === "actions" &&
          canPlotUnitRoute(contextMenu.unit.type) && (
            <MenuItem
              onClick={() => {
                if (contextMenu.kind !== "unit") return;
                const c = contextMenu;
                setContextMenu(null);
                toggleRoutePlotForUnit(c.unit);
              }}
            >
              {routePlotting === contextMenu.unit.unit.id
                ? t("toolbar.route.finish")
                : t("toolbar.route.plot")}
            </MenuItem>
          )}
        {contextMenu?.kind === "unit" &&
          unitContextView === "actions" &&
          (contextMenu.unit.type === "aircraft" ||
            contextMenu.unit.type === "ship") && (
            <MenuItem
              onClick={() => {
                if (contextMenu.kind !== "unit") return;
                const c = contextMenu;
                setContextMenu(null);
                clearUnitRoute(
                  c.unit.unit.id,
                  c.unit.type as "aircraft" | "ship"
                );
              }}
            >
              {t("toolbar.route.clear")}
            </MenuItem>
          )}
        {contextMenu?.kind === "unit" &&
          unitContextView === "actions" &&
          (contextMenu.unit.type === "aircraft" ||
            contextMenu.unit.type === "ship" ||
            contextMenu.unit.type === "facility" ||
            contextMenu.unit.type === "airbase") && (
            <MenuItem
              onClick={() => {
                if (contextMenu.kind !== "unit") return;
                const c = contextMenu;
                setContextMenu(null);
                toggleObjectiveForUnit(c.unit);
              }}
              sx={{ color: "warning.main" }}
            >
              {/* 仅该 4 种单位可设为胜负判定的关键目标。 */}
              {(() => {
                const s = game.currentScenario;
                const u =
                  contextMenu.unit.type === "aircraft"
                    ? s.getAircraft(contextMenu.unit.unit.id)
                    : contextMenu.unit.type === "ship"
                      ? s.getShip(contextMenu.unit.unit.id)
                      : contextMenu.unit.type === "facility"
                        ? s.getFacility(contextMenu.unit.unit.id)
                        : s.getAirbase(contextMenu.unit.unit.id);
                return u?.isObjective ? "☆ 取消关键单位" : "★ 设为关键单位";
              })()}
            </MenuItem>
          )}
        {contextMenu?.kind === "unit" &&
          unitContextView === "actions" &&
          canCarryWeapons(contextMenu.unit.type) && (
            <MenuItem onClick={() => setUnitContextView("weapons")}>
              {t("toolbar.weapons.open")}
            </MenuItem>
          )}
        {contextMenu?.kind === "unit" && unitContextView === "actions" && (
          <MenuItem
            onClick={() => {
              if (contextMenu.kind !== "unit") return;
              const c = contextMenu;
              setContextMenu(null);
              if (!onDeleteUnit) {
                reportRuntimeUnavailable("deleteUnit");
                return;
              }
              void Promise.resolve(
                onDeleteUnit(toRuntimeUnitType(c.unit.type), c.unit.unit.id)
              )
                .then(() => {
                  if (selectedUnitRef.current?.unit.id === c.unit.unit.id) {
                    entitiesRef.current?.setSelected(null);
                    selectedUnitRef.current = null;
                    setSelectedUnit(null);
                  }
                })
                .catch((err) => {
                  reportRuntimeFailure("deleteUnit", err);
                });
            }}
            sx={{ color: "error.main" }}
          >
            {t("toolbar.context.delete")}
          </MenuItem>
        )}
        {/* Add-unit mode: 5 unit types; each uses the first class in its db
            and is dropped at the right-clicked lon/lat. */}
        {contextMenu?.kind === "add" && (
          <ListSubheader sx={{ lineHeight: "28px", fontSize: 11 }}>
            {t("toolbar.addAt.title", {
              lat: contextMenu.lat.toFixed(3),
              lon: contextMenu.lon.toFixed(3),
            })}
          </ListSubheader>
        )}
        {contextMenu?.kind === "add" && (
          <MenuItem
            onMouseEnter={(e) => {
              if (contextMenu.kind !== "add") return;
              const c = contextMenu;
              const anchor = e.currentTarget as HTMLElement;
              setClassChooser({
                anchorEl: anchor,
                options: AircraftDb.map((a) => a.className),
                labelOf: labelFromDict(aircraftLabels),
                onPick: (cls) => {
                  if (onDeployUnit) {
                    void Promise.resolve(
                      onDeployUnit({
                        unit_type: "aircraft",
                        class_name: cls,
                        name: cls,
                        latitude: c.lat,
                        longitude: c.lon,
                      })
                    ).catch((err) => {
                      reportRuntimeFailure("deployUnit", err);
                    });
                  } else {
                    reportRuntimeUnavailable("deployUnit");
                  }
                },
              });
            }}
          >
            {t("toolbar.addAt.aircraft")} ▸
          </MenuItem>
        )}
        {contextMenu?.kind === "add" && (
          <MenuItem
            onMouseEnter={(e) => {
              if (contextMenu.kind !== "add") return;
              const c = contextMenu;
              const anchor = e.currentTarget as HTMLElement;
              setClassChooser({
                anchorEl: anchor,
                options: ShipDb.map((s) => s.className),
                labelOf: labelFromDict(shipLabels),
                onPick: (cls) => {
                  if (onDeployUnit) {
                    void Promise.resolve(
                      onDeployUnit({
                        unit_type: "ship",
                        class_name: cls,
                        name: cls,
                        latitude: c.lat,
                        longitude: c.lon,
                      })
                    ).catch((err) => {
                      reportRuntimeFailure("deployUnit", err);
                    });
                  } else {
                    reportRuntimeUnavailable("deployUnit");
                  }
                },
              });
            }}
          >
            {t("toolbar.addAt.ship")} ▸
          </MenuItem>
        )}
        {contextMenu?.kind === "add" && (
          <MenuItem
            onMouseEnter={(e) => {
              if (contextMenu.kind !== "add") return;
              const c = contextMenu;
              const anchor = e.currentTarget as HTMLElement;
              setClassChooser({
                anchorEl: anchor,
                options: FacilityDb.map((f) => f.className),
                labelOf: labelFromDict(facilityLabels),
                onPick: (cls) => {
                  if (onDeployUnit) {
                    void Promise.resolve(
                      onDeployUnit({
                        unit_type: "facility",
                        class_name: cls,
                        name: cls,
                        latitude: c.lat,
                        longitude: c.lon,
                      })
                    ).catch((err) => {
                      reportRuntimeFailure("deployUnit", err);
                    });
                  } else {
                    reportRuntimeUnavailable("deployUnit");
                  }
                },
              });
            }}
          >
            {t("toolbar.addAt.facility")} ▸
          </MenuItem>
        )}
        {contextMenu?.kind === "add" && (
          <MenuItem
            onMouseEnter={(e) => {
              if (contextMenu.kind !== "add") return;
              const c = contextMenu;
              const anchor = e.currentTarget as HTMLElement;
              setClassChooser({
                anchorEl: anchor,
                options: AirbaseDb.map((a) => a.name),
                labelOf: localizeAirbaseName,
                onPick: (cls) => {
                  if (onDeployUnit) {
                    void Promise.resolve(
                      onDeployUnit({
                        unit_type: "airbase",
                        class_name: cls,
                        name: cls,
                        latitude: c.lat,
                        longitude: c.lon,
                      })
                    ).catch((err) => {
                      reportRuntimeFailure("deployUnit", err);
                    });
                  } else {
                    reportRuntimeUnavailable("deployUnit");
                  }
                },
              });
            }}
          >
            {t("toolbar.addAt.airbase")} ▸
          </MenuItem>
        )}
        {contextMenu?.kind === "add" && (
          <MenuItem
            onMouseEnter={(e) => {
              if (contextMenu.kind !== "add") return;
              const c = contextMenu;
              const anchor = e.currentTarget as HTMLElement;
              setClassChooser({
                anchorEl: anchor,
                options: OBSTACLE_TEMPLATES.map((item) => item.className),
                labelOf: labelFromDict(obstacleLabels),
                onPick: (cls) => {
                  const template =
                    OBSTACLE_TEMPLATES.find((item) => item.className === cls) ??
                    OBSTACLE_TEMPLATES[0];
                  if (onDeployUnit) {
                    void Promise.resolve(
                      onDeployUnit({
                        unit_type: "obstacle",
                        class_name: template.className,
                        name: template.className,
                        latitude: c.lat,
                        longitude: c.lon,
                        radius_nm: template.radiusNm,
                        obstacle_type: template.obstacleType,
                        movement_penalty: template.movementPenalty,
                        detection_penalty: template.detectionPenalty,
                        communication_penalty: template.communicationPenalty,
                        affected_domains: ["aircraft", "ship"],
                      })
                    ).catch((err) => {
                      reportRuntimeFailure("deployUnit", err);
                    });
                  } else {
                    reportRuntimeUnavailable("deployUnit");
                  }
                },
              });
            }}
          >
            {t("toolbar.addAt.obstacle")} ›
          </MenuItem>
        )}
        {contextMenu?.kind === "add" && (
          <MenuItem
            onMouseEnter={() => setClassChooser(null)}
            onClick={() => {
              if (contextMenu.kind !== "add") return;
              const c = contextMenu;
              setContextMenu(null);
              setClassChooser(null);
              if (onDeployUnit) {
                void Promise.resolve(
                  onDeployUnit({
                    unit_type: "reference_point",
                    class_name: "RP",
                    name: "RP",
                    latitude: c.lat,
                    longitude: c.lon,
                  })
                ).catch((err) => {
                  reportRuntimeFailure("deployUnit", err);
                });
              } else {
                reportRuntimeUnavailable("deployUnit");
              }
            }}
          >
            {t("toolbar.addAt.referencePoint")}
          </MenuItem>
        )}
      </Menu>
      {/* Second-stage class chooser. Cascades to the right of the parent menu,
          opened on hover of the first-stage item. The Modal root is made
          pointer-events:none so the backdrop never blocks hovering over the
          parent menu items; only the Paper itself receives pointer events. */}
      <Menu
        open={Boolean(classChooser)}
        onClose={() => setClassChooser(null)}
        anchorEl={classChooser?.anchorEl ?? null}
        anchorOrigin={{ vertical: "top", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
        disableAutoFocus
        disableEnforceFocus
        disableRestoreFocus
        hideBackdrop
        slotProps={{
          root: { sx: { pointerEvents: "none" } },
          paper: {
            sx: { maxHeight: 360, minWidth: 200, pointerEvents: "auto" },
          },
        }}
      >
        {classChooser?.options.map((opt) => (
          <MenuItem
            key={opt}
            onClick={() => {
              const cc = classChooser;
              setClassChooser(null);
              setContextMenu(null);
              cc?.onPick(opt);
            }}
            sx={{ fontSize: 13 }}
          >
            {classChooser?.labelOf ? classChooser.labelOf(opt) : opt}
          </MenuItem>
        ))}
      </Menu>
      {/* Mission creator dialog. */}
      <Dialog
        open={missionCreatorVisible}
        onClose={() => setMissionCreatorVisible(false)}
        maxWidth="md"
        fullWidth
      >
        <MissionCreatorCard
          dialogMode
          aircraft={game.currentScenario.aircraft.filter(
            (a) => game.godMode || a.sideId === game.currentSideId
          )}
          referencePoints={game.currentScenario.referencePoints.filter(
            (r) => game.godMode || r.sideId === game.currentSideId
          )}
          targets={(
            [
              ...game.currentScenario.facilities,
              ...game.currentScenario.ships,
              ...game.currentScenario.airbases,
              ...game.currentScenario.aircraft,
            ] as Target[]
          ).filter((u) =>
            game.godMode
              ? true
              : (u as { sideId?: string }).sideId !== game.currentSideId
          )}
          createPatrolMission={(
            name: string,
            units: string[],
            referencePoints: string[]
          ) => {
            if (onCreatePatrolMission) {
              void Promise.resolve(
                onCreatePatrolMission(name, units, referencePoints)
              )
                .then(() => setMissionCreatorVisible(false))
                .catch((err) => {
                  reportRuntimeFailure("createPatrolMission", err);
                });
              return;
            }
            reportRuntimeUnavailable("createPatrolMission");
          }}
          createStrikeMission={(
            name: string,
            attackers: string[],
            targets: string[]
          ) => {
            if (onCreateStrikeMission) {
              void Promise.resolve(
                onCreateStrikeMission(name, attackers, targets)
              )
                .then(() => setMissionCreatorVisible(false))
                .catch((err) => {
                  reportRuntimeFailure("createStrikeMission", err);
                });
              return;
            }
            reportRuntimeUnavailable("createStrikeMission");
          }}
          handleCloseOnMap={() => setMissionCreatorVisible(false)}
        />
      </Dialog>
      {/* Mission editor dialog. */}
      <Dialog
        open={Boolean(
          visibleMissionEditorMissionId &&
            game.currentScenario.missions.some(
              (mission) => mission.id === visibleMissionEditorMissionId
            )
        )}
        onClose={() => setVisibleMissionEditorMissionId(null)}
        maxWidth="md"
        fullWidth
      >
        {visibleMissionEditorMissionId && (
          <MissionEditorCard
            dialogMode
            missions={game.currentScenario.missions}
            selectedMissionId={visibleMissionEditorMissionId}
            aircraft={game.currentScenario.aircraft}
            referencePoints={game.currentScenario.referencePoints}
            targets={
              [
                ...game.currentScenario.facilities,
                ...game.currentScenario.ships,
                ...game.currentScenario.airbases,
                ...game.currentScenario.aircraft,
              ] as Target[]
            }
            updatePatrolMission={(
              missionId: string,
              name: string,
              units: string[],
              referencePoints: string[]
            ) => {
              if (onUpdatePatrolMission) {
                void Promise.resolve(
                  onUpdatePatrolMission(missionId, name, units, referencePoints)
                )
                  .then(() => setVisibleMissionEditorMissionId(null))
                  .catch((err) => {
                    reportRuntimeFailure("updatePatrolMission", err);
                  });
                return;
              }
              reportRuntimeUnavailable("updatePatrolMission");
            }}
            updateStrikeMission={(
              missionId: string,
              name: string,
              units: string[],
              targets: string[]
            ) => {
              if (onUpdateStrikeMission) {
                void Promise.resolve(
                  onUpdateStrikeMission(missionId, name, units, targets)
                )
                  .then(() => setVisibleMissionEditorMissionId(null))
                  .catch((err) => {
                    reportRuntimeFailure("updateStrikeMission", err);
                  });
                return;
              }
              reportRuntimeUnavailable("updateStrikeMission");
            }}
            deleteMission={(missionId: string) => {
              const mission = game.currentScenario.missions.find(
                (item) => item.id === missionId
              );
              if (!mission) return;
              if (!window.confirm(`确认删除任务「${mission.name}」？`)) return;

              if (!onDeleteMission) {
                reportRuntimeUnavailable("deleteMission");
                return;
              }
              setVisibleMissionEditorMissionId(null);
              void Promise.resolve(onDeleteMission(missionId)).catch((err) => {
                reportRuntimeFailure("deleteMission", err);
              });
            }}
            handleCloseOnMap={() => setVisibleMissionEditorMissionId(null)}
          />
        )}
      </Dialog>
    </>
  );
}
