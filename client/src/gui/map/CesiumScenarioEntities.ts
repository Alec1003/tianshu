import {
  Cartesian2,
  Cartesian3,
  Color,
  ColorMaterialProperty,
  Entity,
  HorizontalOrigin,
  LabelStyle,
  Math as CesiumMath,
  PolylineDashMaterialProperty,
  VerticalOrigin,
  Viewer,
} from "cesium";

import Aircraft from "@/game/units/Aircraft";
import Airbase from "@/game/units/Airbase";
import Facility from "@/game/units/Facility";
import ReferencePoint from "@/game/units/ReferencePoint";
import Scenario from "@/game/Scenario";
import Ship from "@/game/units/Ship";
import {
  isOperationalDetailVisible,
  isScenarioObjectVisible,
  type ScenarioMapUnit,
  type ScenarioVisibility,
} from "@/game/scenarioVisibility";
import { NAUTICAL_MILES_TO_METERS } from "@/utils/constants";

import { localizeUnitName } from "@/i18n/entityNames";
import FlightIconSvg from "@/gui/assets/svg/flight_black_24dp.svg";
import RadarIconSvg from "@/gui/assets/svg/radar_black_24dp.svg";
import FlightTakeoffSvg from "@/gui/assets/svg/flight_takeoff_black_24dp.svg";
import DirectionsBoatSvg from "@/gui/assets/svg/directions_boat_black_24dp.svg";
import PinDropSvg from "@/gui/assets/svg/pin_drop_24dp_E8EAED.svg";
import WeaponSvg from "@/gui/assets/svg/keyboard_double_arrow_up_black_24dp.svg";

// ---------------------------------------------------------------------------
// SVG colorize cache.
// Cesium Billboard.color is a GPU multiply tint: black SVGs * any color = black.
// So we manually pre-render each (svgUrl, color) into a colored PNG dataURL.
// ---------------------------------------------------------------------------

const iconCache = new Map<string, string>();
const iconPending = new Map<string, Promise<string>>();

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = (e) => reject(e);
    img.src = src;
  });
}

async function colorizeIcon(svgUrl: string, color: string): Promise<string> {
  const key = `${svgUrl}|${color}`;
  const cached = iconCache.get(key);
  if (cached) return cached;
  const inflight = iconPending.get(key);
  if (inflight) return inflight;

  const promise = (async () => {
    const img = await loadImage(svgUrl);
    const w = img.naturalWidth || 24;
    const h = img.naturalHeight || 24;
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("2D canvas context unavailable");
    // 1) flood-fill desired color
    ctx.fillStyle = color;
    ctx.fillRect(0, 0, w, h);
    // 2) intersect with SVG alpha mask, producing a colored silhouette
    ctx.globalCompositeOperation = "destination-in";
    ctx.drawImage(img, 0, 0, w, h);
    const dataUrl = canvas.toDataURL("image/png");
    iconCache.set(key, dataUrl);
    iconPending.delete(key);
    return dataUrl;
  })();
  iconPending.set(key, promise);
  return promise;
}

function getColorizedIconSync(svgUrl: string, color: string): string | null {
  return iconCache.get(`${svgUrl}|${color}`) ?? null;
}

// ---------------------------------------------------------------------------
// Unit -> icon mapping (mirrors OL FeatureLayerStyles.ts choices)
// ---------------------------------------------------------------------------

type UnitType = "aircraft" | "facility" | "airbase" | "ship" | "referencePoint";

const ICONS: Record<UnitType, string> = {
  aircraft: FlightIconSvg,
  facility: RadarIconSvg,
  airbase: FlightTakeoffSvg,
  ship: DirectionsBoatSvg,
  referencePoint: PinDropSvg,
};

// Concrete union of unit shapes a popup might render. Kept distinct from
// the renderable unit union so consumers
// that need full data can narrow on `type`.
export type ScenarioUnit =
  | { type: "aircraft"; unit: Aircraft }
  | { type: "ship"; unit: Ship }
  | { type: "facility"; unit: Facility }
  | { type: "airbase"; unit: Airbase }
  | { type: "referencePoint"; unit: ReferencePoint };

interface TypedUnit {
  unit: ScenarioMapUnit;
  type: UnitType;
}

export interface CesiumScenarioRenderOptions {
  showRoutes?: boolean;
  showRanges?: boolean;
}

// ---------------------------------------------------------------------------
// Controller: diff scenario units against existing Cesium entities.
// ---------------------------------------------------------------------------

// Unit IDs become Cesium entity IDs verbatim for the icon billboard.
// Routes / ranges / weapons use a prefixed keyspace so picks can route back.
const ROUTE_PREFIX = "route:";
const RANGE_PREFIX = "range:";
const WEAPON_PREFIX = "weapon:";

const SELECTED_SCALE = 1.4;
const DEFAULT_SCALE = 1;

export class CesiumScenarioEntities {
  private readonly viewer: Viewer;
  private readonly entities = new Map<string, Entity>();
  // routes / ranges live in their own keyspace because a single unit can have
  // both an icon entity and a route polyline simultaneously.
  private readonly routes = new Map<string, Entity>();
  private readonly ranges = new Map<string, Entity>();
  // Flying / in-flight weapons (scenario.weapons), keyed by weapon.id.
  private readonly weaponEntities = new Map<string, Entity>();
  // Latest typed snapshot of units, indexed by id. Refreshed each sync().
  // Used by `lookupUnit` to satisfy popup queries without re-walking Scenario.
  private readonly unitIndex = new Map<string, ScenarioUnit>();
  private selectedId: string | null = null;

  constructor(viewer: Viewer) {
    this.viewer = viewer;
  }

  /** Resolve a Cesium entity id (icon, route:, range:) back to a typed unit. */
  lookupUnit(entityId: string | null | undefined): ScenarioUnit | null {
    if (!entityId) return null;
    const bare = entityId.startsWith(ROUTE_PREFIX)
      ? entityId.slice(ROUTE_PREFIX.length)
      : entityId.startsWith(RANGE_PREFIX)
        ? entityId.slice(RANGE_PREFIX.length)
        : entityId;
    return this.unitIndex.get(bare) ?? null;
  }

  /** Highlight a unit's billboard. Pass `null` to clear. */
  setSelected(id: string | null): void {
    if (this.selectedId === id) return;
    const prev = this.selectedId;
    this.selectedId = id;
    // Apply scale change immediately; subsequent sync() also honors selectedId.
    if (prev) {
      const e = this.entities.get(prev);
      if (e?.billboard) (e.billboard.scale as unknown) = DEFAULT_SCALE;
    }
    if (id) {
      const e = this.entities.get(id);
      if (e?.billboard) (e.billboard.scale as unknown) = SELECTED_SCALE;
    }
  }

  getSelectedId(): string | null {
    return this.selectedId;
  }

  private collect(scenario: Scenario): TypedUnit[] {
    const tag = <T extends ScenarioMapUnit>(
      arr: T[],
      type: UnitType
    ): TypedUnit[] => arr.map((unit) => ({ unit, type }));
    return [
      ...tag<Aircraft>(scenario.aircraft, "aircraft"),
      ...tag<Ship>(scenario.ships, "ship"),
      ...tag<Facility>(scenario.facilities, "facility"),
      ...tag<Airbase>(scenario.airbases, "airbase"),
      ...tag<ReferencePoint>(scenario.referencePoints, "referencePoint"),
    ];
  }

  async sync(
    scenario: Scenario,
    visibility: ScenarioVisibility = {
      godMode: true,
      currentSideId: "",
    },
    renderOptions: CesiumScenarioRenderOptions = {}
  ): Promise<void> {
    const { showRoutes = true, showRanges = true } = renderOptions;
    const all = this.collect(scenario);
    const visibleUnits = all.filter(({ unit }) =>
      isScenarioObjectVisible(scenario, unit, visibility)
    );

    // Refresh typed unit index for popup lookup.
    this.unitIndex.clear();
    for (const aircraft of scenario.aircraft.filter((unit) =>
      isScenarioObjectVisible(scenario, unit, visibility)
    )) {
      this.unitIndex.set(aircraft.id, { type: "aircraft", unit: aircraft });
    }
    for (const ship of scenario.ships.filter((unit) =>
      isScenarioObjectVisible(scenario, unit, visibility)
    )) {
      this.unitIndex.set(ship.id, { type: "ship", unit: ship });
    }
    for (const facility of scenario.facilities.filter((unit) =>
      isScenarioObjectVisible(scenario, unit, visibility)
    )) {
      this.unitIndex.set(facility.id, { type: "facility", unit: facility });
    }
    for (const airbase of scenario.airbases.filter((unit) =>
      isScenarioObjectVisible(scenario, unit, visibility)
    )) {
      this.unitIndex.set(airbase.id, { type: "airbase", unit: airbase });
    }
    for (const rp of scenario.referencePoints.filter((unit) =>
      isScenarioObjectVisible(scenario, unit, visibility)
    )) {
      this.unitIndex.set(rp.id, { type: "referencePoint", unit: rp });
    }

    // Pre-warm icon cache for every (svg, color) combo seen this frame without
    // blocking the first map paint. The current sync can use the raw SVG and a
    // later sync swaps in the colorized PNG once it is ready.
    const combos = new Map<string, [string, string]>();
    for (const { unit, type } of visibleUnits) {
      const svg = ICONS[type];
      const key = `${svg}|${unit.sideColor}`;
      if (!combos.has(key)) combos.set(key, [svg, unit.sideColor]);
    }
    for (const weapon of scenario.weapons.filter((unit) =>
      isScenarioObjectVisible(scenario, unit, visibility)
    )) {
      const key = `${WeaponSvg}|${weapon.sideColor}`;
      if (!combos.has(key)) combos.set(key, [WeaponSvg, weapon.sideColor]);
    }
    void Promise.all(
      Array.from(combos.values()).map(([svg, color]) =>
        colorizeIcon(svg, color)
      )
    ).catch((err) => console.error("[Cesium] icon prewarm failed:", err));

    // Diff: build set of ids still present, create/update entities.
    const wantIds = new Set<string>();
    for (const { unit, type } of visibleUnits) {
      wantIds.add(unit.id);
      const iconUrl =
        getColorizedIconSync(ICONS[type], unit.sideColor) ?? ICONS[type];
      const position = Cartesian3.fromDegrees(unit.longitude, unit.latitude);
      // OL Icon.rotation is clockwise radians from north; Cesium Billboard.rotation
      // is counter-clockwise radians from alignedAxis (default +Y / screen up).
      const heading = "heading" in unit ? unit.heading : undefined;
      const rotation = heading != null ? -CesiumMath.toRadians(heading) : 0;
      const labelColor = Color.fromCssColorString(unit.sideColor);
      const scale =
        this.selectedId === unit.id ? SELECTED_SCALE : DEFAULT_SCALE;

      const existing = this.entities.get(unit.id);
      if (existing) {
        // mutate existing entity in-place (cesium auto-wraps to ConstantProperty)
        // typed as Property | undefined; cast through unknown for primitive assigns
        (existing.position as unknown) = position;
        if (existing.billboard) {
          (existing.billboard.image as unknown) = iconUrl;
          (existing.billboard.rotation as unknown) = rotation;
          (existing.billboard.scale as unknown) = scale;
        }
        if (existing.label) {
          (existing.label.text as unknown) = localizeUnitName(unit.name);
          (existing.label.fillColor as unknown) = labelColor;
        }
      } else {
        const entity = this.viewer.entities.add({
          id: unit.id,
          position,
          billboard: {
            image: iconUrl,
            rotation,
            scale,
            verticalOrigin: VerticalOrigin.CENTER,
            horizontalOrigin: HorizontalOrigin.CENTER,
          },
          label: {
            text: localizeUnitName(unit.name),
            font: "12px Roboto, Helvetica, Arial, sans-serif",
            fillColor: labelColor,
            outlineColor: Color.BLACK,
            outlineWidth: 1,
            style: LabelStyle.FILL_AND_OUTLINE,
            verticalOrigin: VerticalOrigin.TOP,
            horizontalOrigin: HorizontalOrigin.CENTER,
            pixelOffset: new Cartesian2(0, 14),
            showBackground: false,
          },
        });
        this.entities.set(unit.id, entity);
      }
    }

    // Remove entities for units no longer present in scenario.
    for (const [id, entity] of this.entities) {
      if (!wantIds.has(id)) {
        this.viewer.entities.remove(entity);
        this.entities.delete(id);
      }
    }
    if (this.selectedId && !wantIds.has(this.selectedId)) {
      this.selectedId = null;
    }

    if (showRoutes) {
      this.syncRoutes(scenario, visibility);
    } else {
      this.clearRoutes();
    }
    if (showRanges) {
      this.syncRanges(scenario, visibility);
    } else {
      this.clearRanges();
    }
    this.syncWeapons(scenario, visibility);
  }

  private clearRoutes(): void {
    for (const entity of this.routes.values()) {
      this.viewer.entities.remove(entity);
    }
    this.routes.clear();
  }

  private clearRanges(): void {
    for (const entity of this.ranges.values()) {
      this.viewer.entities.remove(entity);
    }
    this.ranges.clear();
  }

  // In-flight weapons (scenario.weapons): icon billboard rotated by heading,
  // colored by sideColor. No label (would clutter swarms) and no range ring.
  // Pickable as `weapon:<id>` but lookupUnit returns null (popup ignores it).
  private syncWeapons(
    scenario: Scenario,
    visibility: ScenarioVisibility
  ): void {
    const want = new Set<string>();
    for (const weapon of scenario.weapons.filter((unit) =>
      isScenarioObjectVisible(scenario, unit, visibility)
    )) {
      want.add(weapon.id);
      const iconUrl =
        getColorizedIconSync(WeaponSvg, weapon.sideColor) ?? WeaponSvg;
      const position = Cartesian3.fromDegrees(
        weapon.longitude,
        weapon.latitude
      );
      const rotation =
        weapon.heading != null ? -CesiumMath.toRadians(weapon.heading) : 0;
      const existing = this.weaponEntities.get(weapon.id);
      if (existing && existing.billboard) {
        (existing.position as unknown) = position;
        (existing.billboard.image as unknown) = iconUrl;
        (existing.billboard.rotation as unknown) = rotation;
      } else {
        const entity = this.viewer.entities.add({
          id: `${WEAPON_PREFIX}${weapon.id}`,
          position,
          billboard: {
            image: iconUrl,
            rotation,
            scale: 0.75,
            verticalOrigin: VerticalOrigin.CENTER,
            horizontalOrigin: HorizontalOrigin.CENTER,
          },
        });
        this.weaponEntities.set(weapon.id, entity);
      }
    }
    for (const [id, entity] of this.weaponEntities) {
      if (!want.has(id)) {
        this.viewer.entities.remove(entity);
        this.weaponEntities.delete(id);
      }
    }
  }

  // Route polylines: aircraft + ship `route: number[][]` (each waypoint is
  // [lat, lon] per OL `RouteLayer.generateRouteWaypoints`). We start the line
  // at the unit's current position and dash it in `sideColor`.
  private syncRoutes(scenario: Scenario, visibility: ScenarioVisibility): void {
    const movers: { id: string; sideColor: string; positions: Cartesian3[] }[] =
      [];
    const collect = (unit: Aircraft | Ship) => {
      if (!isOperationalDetailVisible(scenario, unit, visibility)) return;
      if (!unit.route || unit.route.length === 0) return;
      const positions = [
        Cartesian3.fromDegrees(unit.longitude, unit.latitude),
        ...unit.route.map((wp) => Cartesian3.fromDegrees(wp[1], wp[0])),
      ];
      movers.push({ id: unit.id, sideColor: unit.sideColor, positions });
    };
    scenario.aircraft.forEach(collect);
    scenario.ships.forEach(collect);

    const want = new Set<string>();
    for (const m of movers) {
      want.add(m.id);
      const color = Color.fromCssColorString(m.sideColor);
      const material = new PolylineDashMaterialProperty({
        color,
        dashLength: 16,
      });
      const existing = this.routes.get(m.id);
      if (existing && existing.polyline) {
        (existing.polyline.positions as unknown) = m.positions;
        (existing.polyline.material as unknown) = material;
      } else {
        const entity = this.viewer.entities.add({
          id: `route:${m.id}`,
          polyline: {
            positions: m.positions,
            width: 2,
            material,
          },
        });
        this.routes.set(m.id, entity);
      }
    }
    for (const [id, entity] of this.routes) {
      if (!want.has(id)) {
        this.viewer.entities.remove(entity);
        this.routes.delete(id);
      }
    }
  }

  // Threat / detection range rings: aircraft + ship + facility expose
  // `getDetectionRange()` in nautical miles. Cesium ellipse sized in meters.
  private syncRanges(scenario: Scenario, visibility: ScenarioVisibility): void {
    const ranged = [
      ...scenario.aircraft,
      ...scenario.ships,
      ...scenario.facilities,
    ];

    const want = new Set<string>();
    for (const u of ranged.filter((unit) =>
      isOperationalDetailVisible(scenario, unit, visibility)
    )) {
      const rangeNm = u.getDetectionRange();
      if (!rangeNm || rangeNm <= 0) continue;
      want.add(u.id);
      const radius = rangeNm * NAUTICAL_MILES_TO_METERS;
      const position = Cartesian3.fromDegrees(u.longitude, u.latitude);
      const stroke = Color.fromCssColorString(u.sideColor).withAlpha(0.9);
      const fill = new ColorMaterialProperty(stroke.withAlpha(0.08));
      const existing = this.ranges.get(u.id);
      if (existing && existing.ellipse) {
        (existing.position as unknown) = position;
        (existing.ellipse.semiMajorAxis as unknown) = radius;
        (existing.ellipse.semiMinorAxis as unknown) = radius;
        (existing.ellipse.material as unknown) = fill;
        (existing.ellipse.outlineColor as unknown) = stroke;
      } else {
        const entity = this.viewer.entities.add({
          id: `range:${u.id}`,
          position,
          ellipse: {
            semiMajorAxis: radius,
            semiMinorAxis: radius,
            material: fill,
            outline: true,
            outlineColor: stroke,
            outlineWidth: 1,
            height: 0,
          },
        });
        this.ranges.set(u.id, entity);
      }
    }
    for (const [id, entity] of this.ranges) {
      if (!want.has(id)) {
        this.viewer.entities.remove(entity);
        this.ranges.delete(id);
      }
    }
  }

  destroy(): void {
    for (const entity of this.entities.values()) {
      this.viewer.entities.remove(entity);
    }
    for (const entity of this.routes.values()) {
      this.viewer.entities.remove(entity);
    }
    for (const entity of this.ranges.values()) {
      this.viewer.entities.remove(entity);
    }
    for (const entity of this.weaponEntities.values()) {
      this.viewer.entities.remove(entity);
    }
    this.entities.clear();
    this.routes.clear();
    this.ranges.clear();
    this.weaponEntities.clear();
    this.unitIndex.clear();
    this.selectedId = null;
  }
}
