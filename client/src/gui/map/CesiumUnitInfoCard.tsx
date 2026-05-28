import { useTranslation } from "react-i18next";
import {
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
import StarIcon from "@mui/icons-material/Star";

import Aircraft from "@/game/units/Aircraft";
import Airbase from "@/game/units/Airbase";
import Facility from "@/game/units/Facility";
import Obstacle from "@/game/units/Obstacle";
import Ship from "@/game/units/Ship";
import Scenario from "@/game/Scenario";
import type { Mission } from "@/game/Game";
import type { ScenarioUnit } from "@/gui/map/CesiumScenarioEntities";
import {
  localizeClassName,
  localizeSideName,
  localizeUnitName,
} from "@/i18n/entityNames";

interface CesiumUnitInfoCardProps {
  selection: ScenarioUnit;
  scenario: Scenario;
  onClose: () => void;
}

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

const obstacleTypeLabels: Record<string, string> = {
  no_go: "禁行区",
  restricted_airspace: "受限空域",
  blocked_area: "阻断区",
  terrain: "复杂地形区",
  weather: "恶劣天气区",
  sensor_shadow: "雷达遮蔽区",
  communication_shadow: "通信遮蔽区",
};

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
}: CesiumUnitInfoCardProps) {
  const { t } = useTranslation();
  const { type, unit } = selection;
  const supportsObjective =
    type === "aircraft" ||
    type === "ship" ||
    type === "facility" ||
    type === "airbase";
  const isObjective = supportsObjective
    ? Boolean((unit as Aircraft | Ship | Facility | Airbase).isObjective)
    : false;
  const rawSideName = scenario.getSideName(
    (unit as { sideId?: string }).sideId ?? null
  );
  const sideName = localizeSideName(rawSideName);
  const position = `${fmt(unit.latitude, 3)}, ${fmt(unit.longitude, 3)}`;
  const assignedMission =
    type === "obstacle"
      ? undefined
      : scenario.getMissionByAssignedUnitId(unit.id);

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
          label: "加油能力",
          value: `${fmt(a.fuelOffloadCapacity, 0)} / ${fmt(
            a.refuelRange,
            0
          )} ${t("unit.unit.nm")}`,
        });
      }
      if (a.isElectronicWarfare) {
        extraRows.push({
          label: "电子战",
          value: `${fmt(a.jammingRange, 0)} ${t("unit.unit.nm")} / ${fmt(
            a.jammingStrength,
            2
          )}`,
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
  } else if (type === "obstacle") {
    const obstacle = unit as Obstacle;
    extraRows.push({
      label: t("unit.field.class"),
      value: obstacle.className
        ? localizeClassName(obstacle.className)
        : t("common.na"),
    });
    extraRows.push({
      label: "类型",
      value:
        obstacleTypeLabels[String(obstacle.obstacleType)] ??
        String(obstacle.obstacleType),
    });
    extraRows.push({
      label: "半径",
      value: `${fmt(obstacle.radiusNm, 1)} ${t("unit.unit.nm")}`,
    });
    extraRows.push({
      label: "机动影响",
      value: `${fmt(obstacle.movementPenalty * 100, 0)}%`,
    });
    extraRows.push({
      label: "探测影响",
      value: `${fmt(obstacle.detectionPenalty * 100, 0)}%`,
    });
    extraRows.push({
      label: "通信影响",
      value: `${fmt(obstacle.communicationPenalty * 100, 0)}%`,
    });
    extraRows.push({
      label: "状态",
      value: obstacle.active ? "启用" : "停用",
    });
  }

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
        width: 280,
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
        <Stack spacing={0.5}>
          <Row label={t("unit.field.side")} value={sideName} />
          <Row label={t("unit.field.position")} value={position} />
          {extraRows.map((r) => (
            <Row key={r.label} label={r.label} value={r.value} />
          ))}
          {fuelBar}
        </Stack>
      </CardContent>
    </Card>
  );
}
