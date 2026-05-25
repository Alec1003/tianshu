import { useCallback, useContext, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Box,
  Chip,
  Divider,
  IconButton,
  Menu,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Tooltip,
  Typography,
  useTheme,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import EditIcon from "@mui/icons-material/Edit";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import LightModeIcon from "@mui/icons-material/LightMode";
import FlightIcon from "@mui/icons-material/Flight";
import DirectionsBoatIcon from "@mui/icons-material/DirectionsBoat";
import RadarIcon from "@mui/icons-material/Radar";
import FlightTakeoffIcon from "@mui/icons-material/FlightTakeoff";
import PinDropIcon from "@mui/icons-material/PinDrop";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import PauseIcon from "@mui/icons-material/Pause";
import SkipNextIcon from "@mui/icons-material/SkipNext";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import InsertDriveFileIcon from "@mui/icons-material/InsertDriveFile";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import FileDownloadIcon from "@mui/icons-material/FileDownload";
import LayersIcon from "@mui/icons-material/Layers";
import GroupIcon from "@mui/icons-material/Group";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import VisibilityIcon from "@mui/icons-material/Visibility";
import AssignmentIcon from "@mui/icons-material/Assignment";

import Game from "@/game/Game";
import { SIDE_COLOR } from "@/utils/colors";
import Side from "@/game/Side";
import SideEditor from "@/gui/map/toolbar/SideEditor";
import { ThemeModeContext } from "@/gui/contextProviders/contexts/ThemeModeContext";
import { AircraftDb, FacilityDb, ShipDb, AirbaseDb } from "@/game/db/UnitDb";
import {
  localizeAirbaseName,
  localizeClassName,
  localizeSideName,
} from "@/i18n/entityNames";
import blankScenarioJson from "@/scenarios/blank_scenario.json";
import defaultScenarioJson from "@/scenarios/default_scenario.json";
import SCSScenarioJson from "@/scenarios/SCS.json";
import { randomUUID } from "@/utils/generateUUID";

export type CesiumBaseLayerKey =
  | "lightVector"
  | "darkMatter"
  | "satellite"
  | "sentinel";

export interface CesiumPlacement {
  type: "aircraft" | "ship" | "facility" | "airbase" | "referencePoint";
  className?: string;
}

interface CesiumToolbarProps {
  game: Game;
  baseLayer: CesiumBaseLayerKey;
  onBaseLayerChange: (key: CesiumBaseLayerKey) => void;
  onLoadScenarioJson: (json: string) => void;
  onBeginPlace: (placement: CesiumPlacement) => void;
  placement: CesiumPlacement | null;
  onCancelPlace: () => void;
  scenarioTick: number; // bumped externally to nudge re-render of game-derived UI
  // Mode toggles (eraser / god) and mission creator entry point.
  onToggleEraser: () => void;
  onToggleGodMode: () => void;
  onOpenMissionCreator: () => void;
  onScenarioTimeChange: (time: number) => void;
  onPlay?: () => void | Promise<void>;
  onPause?: () => void | Promise<void>;
  onStep?: () => void | Promise<void>;
  onReset?: () => void | Promise<void>;
}

type ScenarioPreset = {
  currentScenario?: {
    id?: string;
    startTime?: number;
    currentTime?: number;
  };
};

function clonePresetScenarioWithNow(raw: object): ScenarioPreset {
  const cloned = JSON.parse(JSON.stringify(raw)) as ScenarioPreset;
  if (cloned.currentScenario?.id) cloned.currentScenario.id = randomUUID();
  if (cloned.currentScenario) {
    const now = Math.floor(Date.now() / 1000);
    cloned.currentScenario.startTime = now;
    cloned.currentScenario.currentTime = now;
  }
  return cloned;
}

// Section header used between groups. Tight, uppercased, military-style.
function SectionLabel({ title }: { title: string }) {
  return (
    <Typography
      variant="caption"
      sx={{
        px: 1,
        py: 0.25,
        color: "text.secondary",
        letterSpacing: "0.12em",
        fontSize: 10,
        textTransform: "uppercase",
      }}
    >
      {title}
    </Typography>
  );
}

// Square-ish icon button used by every action. Consistent 36x36 hit target.
function ToolButton({
  title,
  icon,
  onClick,
  active,
  disabled,
}: {
  title: string;
  icon: React.ReactNode;
  onClick?: (e: React.MouseEvent<HTMLElement>) => void;
  active?: boolean;
  disabled?: boolean;
}) {
  return (
    <Tooltip title={title} placement="right" arrow>
      <span>
        <IconButton
          onClick={onClick}
          disabled={disabled}
          size="small"
          sx={{
            width: 36,
            height: 36,
            border: 1,
            borderColor: active ? "primary.main" : "divider",
            backgroundColor: active ? "rgba(78,192,122,0.18)" : "transparent",
            color: active ? "primary.main" : "text.primary",
          }}
        >
          {icon}
        </IconButton>
      </span>
    </Tooltip>
  );
}

export default function CesiumToolbar({
  game,
  baseLayer,
  onBaseLayerChange,
  onToggleEraser,
  onToggleGodMode,
  onOpenMissionCreator,
  onLoadScenarioJson,
  onBeginPlace,
  placement,
  onCancelPlace,
  scenarioTick,
  onPlay,
  onPause,
  onStep,
  onReset,
}: Readonly<CesiumToolbarProps>) {
  const { t } = useTranslation();
  const theme = useTheme();
  const { mode, toggleMode } = useContext(ThemeModeContext);

  // Force render whenever scenarioTick changes; capture ref pattern reads game
  // mutable state synchronously. The unused void avoids "unused" warnings.
  void scenarioTick;

  // ---------------------- TIME CONTROL ---------------------------------------
  const [timeControlBusy, setTimeControlBusy] = useState(false);
  const paused = game.scenarioPaused;
  const runTimeControl = useCallback(
    (action: (() => void | Promise<void>) | undefined) => {
      if (!action || timeControlBusy) return;
      setTimeControlBusy(true);
      void Promise.resolve(action()).finally(() => setTimeControlBusy(false));
    },
    [timeControlBusy]
  );

  const togglePlay = useCallback(() => {
    runTimeControl(paused ? onPlay : onPause);
  }, [onPause, onPlay, paused, runTimeControl]);

  const stepOnce = useCallback(() => {
    runTimeControl(onStep);
  }, [onStep, runTimeControl]);

  const restart = useCallback(() => {
    runTimeControl(onReset);
  }, [onReset, runTimeControl]);

  const [speedTick, setSpeedTick] = useState(0);
  const [speedPulse, setSpeedPulse] = useState(false);
  const cycleSpeed = useCallback(() => {
    const SPEEDS = [1, 2, 4, 8, 16, 32, 64];
    const cur = game.currentScenario.timeCompression || 1;
    const idx = SPEEDS.indexOf(cur);
    const next = SPEEDS[(idx + 1) % SPEEDS.length];
    game.currentScenario.timeCompression = next;
    setSpeedTick((n) => n + 1);
    // Trigger a brief scale-up pulse + color flash on the chip.
    setSpeedPulse(true);
    window.setTimeout(() => setSpeedPulse(false), 220);
  }, [game]);
  void speedTick;

  // ---------------------- SCENARIO LOAD MENU --------------------------------
  const [scenarioMenuAnchor, setScenarioMenuAnchor] =
    useState<HTMLElement | null>(null);
  const closeScenarioMenu = () => setScenarioMenuAnchor(null);

  const loadPreset = useCallback(
    (raw: object) => {
      // Bump scenario id so React-keyed code (if any) re-mounts cleanly.
      const cloned = clonePresetScenarioWithNow(raw);
      onLoadScenarioJson(JSON.stringify(cloned));
      closeScenarioMenu();
    },
    [onLoadScenarioJson]
  );

  const importFromFile = useCallback(() => {
    closeScenarioMenu();
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json";
    input.onchange = (event) => {
      const file = (event.target as HTMLInputElement).files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (e) => {
        const txt = e.target?.result as string;
        if (txt) onLoadScenarioJson(txt);
      };
      reader.readAsText(file, "UTF-8");
    };
    input.click();
  }, [onLoadScenarioJson]);

  const exportScenario = useCallback(() => {
    const json = game.exportCurrentScenario();
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(json);
    const ts = new Date().toISOString().replace(/[:.]/g, "_");
    const a = document.createElement("a");
    a.setAttribute("href", dataStr);
    a.setAttribute("download", `aicc_scenario_${ts}.json`);
    document.body.appendChild(a);
    a.click();
    a.remove();
  }, [game]);

  // ---------------------- SIDE ----------------------------------------------
  const [sideMenuAnchor, setSideMenuAnchor] = useState<HTMLElement | null>(
    null
  );
  const closeSideMenu = () => setSideMenuAnchor(null);

  const [createSideOpen, setCreateSideOpen] = useState(false);
  const [newSideName, setNewSideName] = useState("");
  // Side editor (hostiles / allies / doctrine). Reuses OL Popover-based card.
  const [sideEditorAnchor, setSideEditorAnchor] = useState<HTMLElement | null>(
    null
  );
  const [newSideColor, setNewSideColor] = useState<SIDE_COLOR>(SIDE_COLOR.BLUE);

  const sides: Side[] = game.currentScenario.sides;
  const currentSideId = game.currentSideId;
  const currentSideName = useMemo(() => {
    const raw = sides.find((s) => s.id === currentSideId)?.name;
    return raw ? localizeSideName(raw) : "—";
  }, [sides, currentSideId]);

  const switchSide = useCallback(
    (sideId: string) => {
      game.switchCurrentSide(sideId);
      closeSideMenu();
    },
    [game]
  );

  const submitNewSide = useCallback(() => {
    if (!newSideName.trim()) return;
    game.addSide(
      newSideName.trim(),
      newSideColor,
      [],
      [],
      game.currentScenario.getDefaultSideDoctrine()
    );
    if (game.currentScenario.sides.length === 1) {
      game.switchCurrentSide(game.currentScenario.sides[0].id);
    }
    setCreateSideOpen(false);
    setNewSideName("");
  }, [game, newSideName, newSideColor]);

  // ---------------------- ADD UNIT ------------------------------------------
  const [unitMenu, setUnitMenu] = useState<{
    type: CesiumPlacement["type"];
    anchor: HTMLElement;
    classes: string[];
  } | null>(null);

  const openUnitMenu = (
    type: CesiumPlacement["type"],
    anchor: HTMLElement,
    classes: string[]
  ) => {
    if (!currentSideId) {
      // Inline soft warning rather than toast; keeps the toolbar self-contained.
      window.alert(t("toolbar.side.select"));
      return;
    }
    setUnitMenu({ type, anchor, classes });
  };

  const pickUnitClass = (className: string) => {
    if (!unitMenu) return;
    onBeginPlace({ type: unitMenu.type, className });
    setUnitMenu(null);
  };
  const localizePlacementClass = (placementValue: CesiumPlacement) => {
    if (!placementValue.className) return "";
    return placementValue.type === "airbase"
      ? localizeAirbaseName(placementValue.className)
      : localizeClassName(placementValue.className);
  };
  const localizeUnitMenuOption = (option: string) => {
    if (unitMenu?.type === "airbase") return localizeAirbaseName(option);
    return localizeClassName(option);
  };

  // ---------------------- BASE LAYER MENU -----------------------------------
  const [baseMenuAnchor, setBaseMenuAnchor] = useState<HTMLElement | null>(
    null
  );

  // Note: we intentionally do NOT auto-switch base layer when theme changes.
  // CartoDB Dark Matter / Esri imagery may be unreachable in some networks,
  // and forcing them on first mount could leave the user with a blue globe.
  // The user can switch base layer explicitly from the View section below.

  // ---------------------- RENDER --------------------------------------------
  const compression = game.currentScenario.timeCompression || 1;

  return (
    <Paper
      elevation={0}
      sx={{
        position: "absolute",
        top: 0,
        left: 0,
        bottom: 0,
        width: 240,
        zIndex: 1100,
        backgroundColor: "background.paper",
        borderRight: 1,
        borderColor: "divider",
        display: "flex",
        flexDirection: "column",
        overflow: "auto",
        pointerEvents: "auto",
      }}
    >
      {/* Brand */}
      <Box sx={{ px: 1.5, py: 1.5, borderBottom: 1, borderColor: "divider" }}>
        <Typography
          variant="h6"
          sx={{
            fontWeight: 700,
            letterSpacing: "0.18em",
            color: "primary.main",
          }}
        >
          {t("brand.name")}
        </Typography>
        <Typography variant="caption" sx={{ color: "text.secondary" }}>
          {t("brand.tagline")}
        </Typography>
      </Box>

      {/* Active placement banner */}
      {placement && (
        <Box
          sx={{
            px: 1.5,
            py: 0.75,
            borderBottom: 1,
            borderColor: "primary.main",
            backgroundColor: "rgba(78,192,122,0.12)",
            display: "flex",
            flexDirection: "column",
            gap: 0.25,
            animation: "aiccBlink 1.4s ease-in-out infinite",
            "@keyframes aiccBlink": {
              "0%, 100%": { backgroundColor: "rgba(78,192,122,0.12)" },
              "50%": { backgroundColor: "rgba(78,192,122,0.30)" },
            },
          }}
        >
          <Stack direction="row" alignItems="center" spacing={1}>
            <Typography
              variant="caption"
              sx={{ flex: 1, fontWeight: 700, color: "primary.main" }}
            >
              {t(
                `toolbar.unit.add${placement.type
                  .charAt(0)
                  .toUpperCase()}${placement.type.slice(1)}`
              )}
              {placement.className
                ? ` · ${localizePlacementClass(placement)}`
                : ""}
            </Typography>
            <Chip
              size="small"
              label={t("toolbar.placement.cancel")}
              color="primary"
              variant="outlined"
              onClick={onCancelPlace}
            />
          </Stack>
          <Typography
            variant="caption"
            sx={{ color: "text.secondary", fontSize: 10 }}
          >
            {t("toolbar.placement.hint")}
          </Typography>
        </Box>
      )}

      {/* Scenario */}
      <SectionLabel title={t("toolbar.section.scenario")} />
      <Stack direction="row" spacing={0.5} sx={{ px: 1, pb: 1 }}>
        <ToolButton
          title={t("toolbar.scenario.new")}
          icon={<InsertDriveFileIcon fontSize="small" />}
          onClick={() => loadPreset(blankScenarioJson)}
        />
        <ToolButton
          title={t("toolbar.scenario.load")}
          icon={<UploadFileIcon fontSize="small" />}
          onClick={(e) => setScenarioMenuAnchor(e.currentTarget)}
        />
        <ToolButton
          title={t("toolbar.scenario.export")}
          icon={<FileDownloadIcon fontSize="small" />}
          onClick={exportScenario}
        />
      </Stack>
      <Menu
        anchorEl={scenarioMenuAnchor}
        open={Boolean(scenarioMenuAnchor)}
        onClose={closeScenarioMenu}
        anchorOrigin={{ vertical: "top", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
        slotProps={{
          paper: {
            sx: {
              ml: 1,
              maxWidth: "min(240px, calc(100vw - 256px))",
            },
          },
        }}
      >
        <MenuItem onClick={() => loadPreset(defaultScenarioJson)}>
          Demo Scenario
        </MenuItem>
        <MenuItem onClick={() => loadPreset(SCSScenarioJson)}>
          South China Sea Strike
        </MenuItem>
        <Divider />
        <MenuItem onClick={importFromFile}>
          {t("toolbar.scenario.loadFromFile")}
        </MenuItem>
      </Menu>

      <Divider />

      {/* Side */}
      <SectionLabel title={t("toolbar.section.side")} />
      <Stack direction="row" spacing={0.5} sx={{ px: 1, pb: 0.5 }}>
        <ToolButton
          title={t("toolbar.side.select")}
          icon={<GroupIcon fontSize="small" />}
          onClick={(e) => setSideMenuAnchor(e.currentTarget)}
        />
        <ToolButton
          title={t("toolbar.side.create")}
          icon={<AddIcon fontSize="small" />}
          onClick={() => setCreateSideOpen(true)}
        />
        <ToolButton
          title={t("toolbar.side.edit")}
          icon={<EditIcon fontSize="small" />}
          disabled={!currentSideId}
          onClick={(e) => setSideEditorAnchor(e.currentTarget)}
        />
        <Box
          sx={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            px: 1,
            color: "text.secondary",
            fontSize: 12,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {currentSideName}
        </Box>
      </Stack>
      <Menu
        anchorEl={sideMenuAnchor}
        open={Boolean(sideMenuAnchor)}
        onClose={closeSideMenu}
        anchorOrigin={{ vertical: "top", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
        slotProps={{
          paper: {
            sx: {
              ml: 1,
              maxWidth: "min(240px, calc(100vw - 256px))",
            },
          },
        }}
      >
        {sides.length === 0 && <MenuItem disabled>{t("common.na")}</MenuItem>}
        {sides.map((s) => (
          <MenuItem
            key={s.id}
            onClick={() => switchSide(s.id)}
            selected={s.id === currentSideId}
          >
            <Box
              sx={{
                width: 12,
                height: 12,
                backgroundColor: s.color,
                mr: 1,
                border: 1,
                borderColor: "divider",
              }}
            />
            {localizeSideName(s.name)}
          </MenuItem>
        ))}
      </Menu>
      {createSideOpen && (
        <Box
          sx={{
            px: 1.5,
            py: 1,
            display: "flex",
            flexDirection: "column",
            gap: 1,
            borderBottom: 1,
            borderColor: "divider",
            backgroundColor: "background.default",
          }}
        >
          <TextField
            size="small"
            autoFocus
            label={t("toolbar.side.create")}
            value={newSideName}
            onChange={(e) => setNewSideName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitNewSide();
              if (e.key === "Escape") setCreateSideOpen(false);
            }}
          />
          <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap" }}>
            {Object.values(SIDE_COLOR).map((c) => (
              <Box
                key={c}
                onClick={() => setNewSideColor(c)}
                sx={{
                  width: 18,
                  height: 18,
                  backgroundColor: c,
                  cursor: "pointer",
                  border: 2,
                  borderColor:
                    newSideColor === c ? "primary.main" : "transparent",
                }}
              />
            ))}
          </Stack>
          <Stack direction="row" spacing={0.5}>
            <Chip
              size="small"
              label={t("toolbar.side.create")}
              color="primary"
              onClick={submitNewSide}
            />
            <Chip
              size="small"
              label={t("common.close")}
              variant="outlined"
              onClick={() => setCreateSideOpen(false)}
            />
          </Stack>
        </Box>
      )}

      {/* Side editor Popover: hostiles / allies / doctrine for current side. */}
      <SideEditor
        open={Boolean(sideEditorAnchor)}
        anchorEl={sideEditorAnchor}
        side={sides.find((s) => s.id === currentSideId)}
        sides={sides}
        hostiles={
          currentSideId
            ? game.currentScenario.relationships.getHostiles(currentSideId)
            : []
        }
        allies={
          currentSideId
            ? game.currentScenario.relationships.getAllies(currentSideId)
            : []
        }
        doctrine={
          currentSideId
            ? game.currentScenario.getSideDoctrine(currentSideId)
            : game.currentScenario.getDefaultSideDoctrine()
        }
        updateSide={(id, name, color, host, allies, doctrine) => {
          game.updateSide(id, name, color, host, allies, doctrine);
          setSideEditorAnchor(null);
        }}
        addSide={(name, color, host, allies, doctrine) => {
          game.addSide(name, color, host, allies, doctrine);
          setSideEditorAnchor(null);
        }}
        deleteSide={(id) => {
          game.deleteSide(id);
          setSideEditorAnchor(null);
        }}
        handleCloseOnMap={() => setSideEditorAnchor(null)}
      />

      <Divider />

      {/* Units */}
      <SectionLabel title={t("toolbar.section.units")} />
      <Stack
        direction="row"
        spacing={0.5}
        sx={{ px: 1, pb: 1, flexWrap: "wrap", rowGap: 0.5 }}
      >
        <ToolButton
          title={t("toolbar.unit.addAircraft")}
          icon={<FlightIcon fontSize="small" />}
          active={placement?.type === "aircraft"}
          onClick={(e) =>
            openUnitMenu(
              "aircraft",
              e.currentTarget,
              AircraftDb.map((a) => a.className)
            )
          }
        />
        <ToolButton
          title={t("toolbar.unit.addShip")}
          icon={<DirectionsBoatIcon fontSize="small" />}
          active={placement?.type === "ship"}
          onClick={(e) =>
            openUnitMenu(
              "ship",
              e.currentTarget,
              ShipDb.map((s) => s.className)
            )
          }
        />
        <ToolButton
          title={t("toolbar.unit.addFacility")}
          icon={<RadarIcon fontSize="small" />}
          active={placement?.type === "facility"}
          onClick={(e) =>
            openUnitMenu(
              "facility",
              e.currentTarget,
              FacilityDb.map((f) => f.className)
            )
          }
        />
        <ToolButton
          title={t("toolbar.unit.addAirbase")}
          icon={<FlightTakeoffIcon fontSize="small" />}
          active={placement?.type === "airbase"}
          onClick={(e) =>
            openUnitMenu(
              "airbase",
              e.currentTarget,
              AirbaseDb.map((a) => a.name)
            )
          }
        />
        <ToolButton
          title={t("toolbar.unit.addReferencePoint")}
          icon={<PinDropIcon fontSize="small" />}
          active={placement?.type === "referencePoint"}
          onClick={() => {
            if (!currentSideId) {
              window.alert(t("toolbar.side.select"));
              return;
            }
            onBeginPlace({ type: "referencePoint" });
          }}
        />
      </Stack>
      <Menu
        anchorEl={unitMenu?.anchor ?? null}
        open={Boolean(unitMenu)}
        onClose={() => setUnitMenu(null)}
        anchorOrigin={{ vertical: "top", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
        slotProps={{
          paper: {
            sx: {
              maxHeight: "70vh",
              maxWidth: "min(240px, calc(100vw - 256px))",
              ml: 1,
              "& .MuiMenuItem-root": {
                whiteSpace: "normal",
                wordBreak: "break-word",
              },
            },
          },
        }}
      >
        {unitMenu?.classes.map((c) => (
          <MenuItem key={c} onClick={() => pickUnitClass(c)}>
            {localizeUnitMenuOption(c)}
          </MenuItem>
        ))}
      </Menu>

      <Divider />

      {/* Time */}
      <SectionLabel title={t("toolbar.section.time")} />
      <Stack direction="row" spacing={0.5} sx={{ px: 1, pb: 1 }}>
        <ToolButton
          title={paused ? t("toolbar.time.play") : t("toolbar.time.pause")}
          icon={
            paused ? (
              <PlayArrowIcon fontSize="small" />
            ) : (
              <PauseIcon fontSize="small" />
            )
          }
          active={!paused}
          disabled={timeControlBusy || (paused ? !onPlay : !onPause)}
          onClick={togglePlay}
        />
        <ToolButton
          title={t("toolbar.time.step")}
          icon={<SkipNextIcon fontSize="small" />}
          disabled={timeControlBusy || !onStep}
          onClick={stepOnce}
        />
        <ToolButton
          title={t("toolbar.time.restart")}
          icon={<RestartAltIcon fontSize="small" />}
          disabled={timeControlBusy || !onReset}
          onClick={restart}
        />
        <Tooltip title={t("toolbar.time.speed")} placement="right" arrow>
          <Chip
            size="small"
            label={`${compression}x`}
            onClick={cycleSpeed}
            sx={{
              borderRadius: 0.5,
              height: 36,
              alignSelf: "center",
              minWidth: 48,
              fontWeight: 700,
              letterSpacing: "0.06em",
              transition:
                "transform 180ms cubic-bezier(.2,1.4,.4,1), background-color 180ms, color 180ms",
              transform: speedPulse ? "scale(1.18)" : "scale(1)",
              backgroundColor: speedPulse ? "primary.main" : "transparent",
              color: speedPulse ? "background.paper" : "text.primary",
              borderColor: speedPulse ? "primary.main" : "divider",
            }}
            variant="outlined"
          />
        </Tooltip>
      </Stack>

      <Divider />

      {/* Modes: eraser / god mode / missions. Reads game state directly so the
          active highlight reflects toggles done from anywhere. */}
      <SectionLabel title={t("toolbar.section.modes")} />
      <Stack direction="row" spacing={0.5} sx={{ px: 1, pb: 1 }}>
        <ToolButton
          title={t("toolbar.modes.eraser")}
          icon={<DeleteOutlineIcon fontSize="small" />}
          active={game.eraserMode}
          onClick={onToggleEraser}
        />
        <ToolButton
          title={t("toolbar.modes.godMode")}
          icon={<VisibilityIcon fontSize="small" />}
          active={game.godMode}
          onClick={onToggleGodMode}
        />
        <ToolButton
          title={t("toolbar.mission.add")}
          icon={<AssignmentIcon fontSize="small" />}
          onClick={onOpenMissionCreator}
        />
      </Stack>

      <Box sx={{ flexGrow: 1 }} />

      <Divider />

      {/* View */}
      <SectionLabel title={t("toolbar.section.view")} />
      <Stack direction="row" spacing={0.5} sx={{ px: 1, pb: 1.5 }}>
        <ToolButton
          title={
            mode === "dark" ? t("toolbar.theme.light") : t("toolbar.theme.dark")
          }
          icon={
            mode === "dark" ? (
              <LightModeIcon fontSize="small" />
            ) : (
              <DarkModeIcon fontSize="small" />
            )
          }
          onClick={toggleMode}
        />
        <ToolButton
          title={t("map.baseLayer.label")}
          icon={<LayersIcon fontSize="small" />}
          onClick={(e) => setBaseMenuAnchor(e.currentTarget)}
        />
        <Box
          sx={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            px: 1,
            color: "text.secondary",
            fontSize: 11,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {t(`map.baseLayer.${baseLayer}`)}
        </Box>
      </Stack>
      <Menu
        anchorEl={baseMenuAnchor}
        open={Boolean(baseMenuAnchor)}
        onClose={() => setBaseMenuAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "bottom", horizontal: "left" }}
        slotProps={{
          paper: {
            sx: {
              ml: 1,
              maxWidth: "min(240px, calc(100vw - 256px))",
            },
          },
        }}
      >
        {(
          [
            "lightVector",
            "darkMatter",
            "satellite",
            "sentinel",
          ] as CesiumBaseLayerKey[]
        ).map((key) => (
          <MenuItem
            key={key}
            selected={baseLayer === key}
            onClick={() => {
              onBaseLayerChange(key);
              setBaseMenuAnchor(null);
            }}
          >
            {t(`map.baseLayer.${key}`)}
          </MenuItem>
        ))}
      </Menu>

      {/* Theme indicator strip at bottom */}
      <Box
        sx={{
          height: 4,
          backgroundColor: theme.palette.primary.main,
        }}
      />
    </Paper>
  );
}
