import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Divider,
  IconButton,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import RouteIcon from "@mui/icons-material/Route";
import ClearIcon from "@mui/icons-material/Clear";
import RocketLaunchIcon from "@mui/icons-material/RocketLaunch";
import StarIcon from "@mui/icons-material/Star";
import StarBorderIcon from "@mui/icons-material/StarBorder";

import Aircraft from "@/game/units/Aircraft";
import Airbase from "@/game/units/Airbase";
import Facility from "@/game/units/Facility";
import Ship from "@/game/units/Ship";
import Weapon from "@/game/units/Weapon";
import Scenario from "@/game/Scenario";
import type { Mission } from "@/game/Game";
import type { ScenarioUnit } from "@/gui/map/CesiumScenarioEntities";
import {
  localizeClassName,
  localizeSideName,
  localizeUnitName,
} from "@/i18n/entityNames";
import WeaponTable from "@/gui/map/feature/shared/WeaponTable";

interface CesiumUnitInfoCardProps {
  selection: ScenarioUnit;
  scenario: Scenario;
  onClose: () => void;
  // Optional route actions; only provided for aircraft / ship in CesiumScenarioMap.
  onPlotRoute?: () => void;
  onClearRoute?: () => void;
  routePlotting?: boolean;
  // Optional weapon-loadout handlers. When all three are provided (and the
  // selection is an aircraft / ship / facility), the card exposes a "Weapons"
  // toggle that opens an inline WeaponTable for adding, removing and
  // adjusting quantities — mirroring the OL feature popup capabilities.
  onAddWeapon?: (unitId: string, weaponClassName: string) => Weapon[];
  onDeleteWeapon?: (unitId: string, weaponId: string) => Weapon[];
  onUpdateWeaponQuantity?: (
    unitId: string,
    weaponId: string,
    increment: number
  ) => Weapon[];
  // 关键单位切换：仅 aircraft/ship/facility/airbase 支持。提供时在详情卡
  // 按钮区多一个切换按钮，Toggle 后调用方需自行 bumpScenario。
  onToggleObjective?: () => void;
}

// Side-by-side label/value row. Empty values fall back to N/A so the card
// retains a consistent grid even for sparsely populated reference points.
function Row({ label, value }: { label: string; value: string }) {
  return (
    <Stack direction="row" spacing={1} sx={{ minWidth: 0 }}>
      <Typography
        variant="caption"
        sx={{ width: 88, color: "text.secondary", flexShrink: 0 }}
      >
        {label}
      </Typography>
      <Typography
        variant="caption"
        sx={{
          fontWeight: 500,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {value}
      </Typography>
    </Stack>
  );
}

const fmt = (n: number, digits = 2) =>
  Number.isFinite(n) ? n.toFixed(digits) : "-";

function missionTypeLabel(mission: Mission): string {
  return "assignedTargetIds" in mission ? "打击任务" : "巡逻任务";
}

function missionDetailLabel(mission: Mission): string {
  return "assignedTargetIds" in mission ? "任务目标" : "巡逻区域";
}

function resolveMissionDetail(scenario: Scenario, mission: Mission): string {
  if ("assignedTargetIds" in mission) {
    const targetNames = mission.assignedTargetIds.map((targetId) => {
      const target =
        scenario.getFacility(targetId) ??
        scenario.getShip(targetId) ??
        scenario.getAirbase(targetId) ??
        scenario.getAircraft(targetId) ??
        scenario.getReferencePoint(targetId);

      return target ? localizeUnitName(target.name) : targetId;
    });
    return targetNames.length > 0 ? targetNames.join("、") : "未设置";
  }

  const areaNames = mission.assignedArea.map((point) =>
    localizeUnitName(point.name)
  );
  return areaNames.length > 0 ? areaNames.join("、") : "未设置";
}

export default function CesiumUnitInfoCard({
  selection,
  scenario,
  onClose,
  onPlotRoute,
  onClearRoute,
  routePlotting,
  onAddWeapon,
  onDeleteWeapon,
  onUpdateWeaponQuantity,
  onToggleObjective,
}: CesiumUnitInfoCardProps) {
  const { t } = useTranslation();
  const { type, unit } = selection;
  // "default" shows the read-only summary; "weapons" swaps in the loadout
  // editor (reused from the OL feature popup).
  const [view, setView] = useState<"default" | "weapons">("default");
  // Unit kinds that can carry weapons. Reference points / airbases cannot.
  const supportsWeapons =
    type === "aircraft" || type === "ship" || type === "facility";
  // 参考点不入胜负判定范围；airbase 可作为关键设施目标。
  const supportsObjective =
    type === "aircraft" ||
    type === "ship" ||
    type === "facility" ||
    type === "airbase";
  const isObjective = supportsObjective
    ? Boolean((unit as Aircraft | Ship | Facility | Airbase).isObjective)
    : false;
  const canEditWeapons =
    supportsWeapons &&
    Boolean(onAddWeapon && onDeleteWeapon && onUpdateWeaponQuantity);
  const rawSideName = scenario.getSideName(
    (unit as { sideId?: string }).sideId ?? null
  );
  const sideName = localizeSideName(rawSideName);
  const position = `${fmt(unit.latitude, 3)}, ${fmt(unit.longitude, 3)}`;
  const assignedMission = scenario.getMissionByAssignedUnitId(unit.id);

  // Per-type details. We deliberately keep each branch tight; the card is a
  // read-only summary, not a full entity editor.
  const extraRows: { label: string; value: string }[] = [];
  extraRows.push({
    label: "任务",
    value: assignedMission
      ? `${missionTypeLabel(assignedMission)} · ${localizeUnitName(
          assignedMission.name
        )} · ${assignedMission.active ? "启用" : "停用"}`
      : "无",
  });
  if (assignedMission) {
    extraRows.push({
      label: missionDetailLabel(assignedMission),
      value: resolveMissionDetail(scenario, assignedMission),
    });
  }

  if (type === "aircraft" || type === "ship") {
    const u = unit as Aircraft | Ship;
    extraRows.push({
      label: t("unit.field.class"),
      value: u.className ? localizeClassName(u.className) : t("common.na"),
    });
    extraRows.push({
      label: t("unit.field.heading"),
      value: `${fmt(u.heading, 0)}${t("unit.unit.deg")}`,
    });
    extraRows.push({
      label: t("unit.field.speed"),
      value: `${fmt(u.speed, 0)} ${t("unit.unit.knots")}`,
    });
    extraRows.push({
      label: t("unit.field.fuel"),
      value: `${fmt(u.currentFuel, 0)} / ${fmt(u.maxFuel, 0)}`,
    });
    extraRows.push({
      label: t("unit.field.detectionRange"),
      value: `${fmt(u.getDetectionRange(), 0)} ${t("unit.unit.nm")}`,
    });
    if (type === "aircraft") {
      const a = u as Aircraft;
      extraRows.push({
        label: t("unit.field.altitude"),
        value: `${fmt(a.altitude, 0)} ${t("unit.unit.feet")}`,
      });
      extraRows.push({
        label: t("unit.field.weapons"),
        value: `${a.getTotalWeaponQuantity()} ${t("unit.unit.rounds")}`,
      });
      extraRows.push({
        label: t("unit.field.weaponEngagementRange"),
        value: `${fmt(a.getWeaponEngagementRange(), 0)} ${t("unit.unit.nm")}`,
      });
      extraRows.push({
        label: t("unit.field.rtb"),
        value: a.rtb ? t("common.yes") : t("common.no"),
      });
      if (a.isTanker) {
        extraRows.push({
          label: "Tanker",
          value: `${fmt(a.fuelOffloadCapacity, 0)} / ${fmt(
            a.refuelRange,
            0
          )} ${t("unit.unit.nm")}`,
        });
      }
    }
    if (type === "ship") {
      const s = u as Ship;
      extraRows.push({
        label: t("unit.field.weapons"),
        value: `${s.getTotalWeaponQuantity()} ${t("unit.unit.rounds")}`,
      });
    }
  } else if (type === "facility") {
    const f = unit as Facility;
    extraRows.push({
      label: t("unit.field.class"),
      value: f.className ? localizeClassName(f.className) : t("common.na"),
    });
    extraRows.push({
      label: t("unit.field.detectionRange"),
      value: `${fmt(f.getDetectionRange(), 0)} ${t("unit.unit.nm")}`,
    });
    extraRows.push({
      label: t("unit.field.weapons"),
      value: `${f.getTotalWeaponQuantity()} ${t("unit.unit.rounds")}`,
    });
  } else if (type === "airbase") {
    extraRows.push({
      label: t("unit.field.altitude"),
      value: t("common.na"),
    });
  }

  // Fuel progress bar (aircraft / ship). Visualizes currentFuel / maxFuel so
  // users can spot bingo-fuel without reading the numeric ratio.
  const fuelBar = (() => {
    if (type !== "aircraft" && type !== "ship") return null;
    const u = unit as Aircraft | Ship;
    if (!Number.isFinite(u.maxFuel) || u.maxFuel <= 0) return null;
    const pct = Math.max(0, Math.min(100, (u.currentFuel / u.maxFuel) * 100));
    const color = pct < 20 ? "error" : pct < 50 ? "warning" : "success";
    return (
      <Stack
        direction="row"
        spacing={1}
        sx={{ mt: 0.25, alignItems: "center" }}
      >
        <Typography
          variant="caption"
          sx={{ width: 88, color: "text.secondary", flexShrink: 0 }}
        >
          {" "}
        </Typography>
        <LinearProgress
          variant="determinate"
          value={pct}
          color={color}
          sx={{ flex: 1, height: 6, borderRadius: 3 }}
        />
        <Typography
          variant="caption"
          sx={{ width: 36, textAlign: "right", color: "text.secondary" }}
        >
          {pct.toFixed(0)}%
        </Typography>
      </Stack>
    );
  })();

  return (
    <Card
      sx={{
        // Outer wrapper handles fixed positioning; we just need card sizing.
        // Expand when showing the weapon loadout editor so the WeaponTable
        // (minWidth ~500px) fits without horizontal scrolling.
        width: view === "weapons" ? 560 : 280,
        backgroundColor: "rgba(255,255,255,0.96)",
        boxShadow: 4,
      }}
    >
      <CardHeader
        sx={{
          py: 1,
          px: 1.5,
          backgroundColor: unit.sideColor,
          color: "#fff",
          "& .MuiCardHeader-title": { fontSize: 14, fontWeight: 600 },
          "& .MuiCardHeader-subheader": { fontSize: 12, color: "#f0f0f0" },
        }}
        title={
          isObjective ? (
            <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
              <StarIcon sx={{ fontSize: 14, color: "#ffd54f" }} />
              <span>{localizeUnitName(unit.name)}</span>
            </Stack>
          ) : (
            localizeUnitName(unit.name)
          )
        }
        subheader={
          isObjective
            ? `${t(`unit.type.${type}`)} · 关键单位`
            : t(`unit.type.${type}`)
        }
        action={
          <IconButton
            size="small"
            aria-label={t("common.close")}
            onClick={onClose}
            sx={{ color: "#fff" }}
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        }
      />
      <Divider />
      <CardContent sx={{ py: 1.25, px: 1.5, "&:last-child": { pb: 1.25 } }}>
        {view === "default" && (
          <>
            <Stack spacing={0.5}>
              <Row label={t("unit.field.side")} value={sideName} />
              <Row label={t("unit.field.position")} value={position} />
              {extraRows.map((r) => (
                <Row key={r.label} label={r.label} value={r.value} />
              ))}
              {fuelBar}
            </Stack>
            {(canEditWeapons ||
              ((type === "aircraft" || type === "ship") &&
                (onPlotRoute || onClearRoute))) && <Divider sx={{ my: 1 }} />}
            <Stack
              direction="row"
              spacing={0.75}
              sx={{ flexWrap: "wrap", rowGap: 0.5 }}
            >
              {(type === "aircraft" || type === "ship") && onPlotRoute && (
                <Button
                  size="small"
                  variant={routePlotting ? "contained" : "outlined"}
                  color="primary"
                  startIcon={<RouteIcon fontSize="small" />}
                  onClick={onPlotRoute}
                  sx={{ fontSize: 11, py: 0.25 }}
                >
                  {routePlotting
                    ? t("toolbar.route.finish")
                    : t("toolbar.route.plot")}
                </Button>
              )}
              {(type === "aircraft" || type === "ship") && onClearRoute && (
                <Button
                  size="small"
                  variant="outlined"
                  color="error"
                  startIcon={<ClearIcon fontSize="small" />}
                  onClick={onClearRoute}
                  sx={{ fontSize: 11, py: 0.25 }}
                >
                  {t("toolbar.route.clear")}
                </Button>
              )}
              {canEditWeapons && (
                <Button
                  size="small"
                  variant="outlined"
                  color="secondary"
                  startIcon={<RocketLaunchIcon fontSize="small" />}
                  onClick={() => setView("weapons")}
                  sx={{ fontSize: 11, py: 0.25 }}
                >
                  {t("toolbar.weapons.open")}
                </Button>
              )}
              {supportsObjective && onToggleObjective && (
                <Button
                  size="small"
                  variant={isObjective ? "contained" : "outlined"}
                  color="warning"
                  startIcon={
                    isObjective ? (
                      <StarIcon fontSize="small" />
                    ) : (
                      <StarBorderIcon fontSize="small" />
                    )
                  }
                  onClick={onToggleObjective}
                  sx={{ fontSize: 11, py: 0.25 }}
                  title="标记为关键单位：被击毁后对方立即胜。"
                >
                  {isObjective ? "取消关键" : "设为关键"}
                </Button>
              )}
            </Stack>
            {routePlotting && (
              <Typography
                variant="caption"
                sx={{ mt: 0.5, color: "text.secondary", fontSize: 10 }}
              >
                {t("toolbar.route.hint")}
              </Typography>
            )}
          </>
        )}
        {view === "weapons" && canEditWeapons && supportsWeapons && (
          <Box
            sx={{
              // WeaponTable was authored for the OL dark popover; we recreate
              // that backdrop locally so its white text / icons stay legible.
              backgroundColor: "#282c34",
              color: "white",
              borderRadius: 1,
              p: 1,
              mx: -1,
            }}
          >
            <Typography
              variant="caption"
              sx={{ color: "#cfcfcf", display: "block", mb: 0.5, px: 0.5 }}
            >
              {t("toolbar.weapons.title")}
            </Typography>
            <WeaponTable
              unitWithWeapon={unit as Aircraft | Ship | Facility}
              handleAddWeapon={(unitId, cls) => onAddWeapon!(unitId, cls) ?? []}
              handleDeleteWeapon={(unitId, weaponId) =>
                onDeleteWeapon!(unitId, weaponId) ?? []
              }
              handleUpdateWeaponQuantity={(unitId, weaponId, inc) =>
                onUpdateWeaponQuantity!(unitId, weaponId, inc) ?? []
              }
              handleCloseOnMap={onClose}
            />
            <Stack direction="row" sx={{ mt: 1, justifyContent: "flex-end" }}>
              <Button
                size="small"
                variant="outlined"
                onClick={() => setView("default")}
                sx={{
                  fontSize: 11,
                  py: 0.25,
                  color: "white",
                  borderColor: "rgba(255,255,255,0.5)",
                }}
              >
                {t("toolbar.weapons.back")}
              </Button>
            </Stack>
          </Box>
        )}
      </CardContent>
    </Card>
  );
}
