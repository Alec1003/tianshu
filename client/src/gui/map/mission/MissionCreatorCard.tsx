import { useRef, useState, useContext } from "react";
import Draggable from "react-draggable";
import Card from "@mui/material/Card";
import Aircraft from "@/game/units/Aircraft";
import ReferencePoint from "@/game/units/ReferencePoint";
import type { Target } from "@/game/Target";
import {
  Button,
  CardContent,
  CardHeader,
  FormControl,
  IconButton,
  Stack,
  Typography,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import SelectField from "@/gui/shared/ui/SelectField";
import TextField from "@/gui/shared/ui/TextField";
import { ToastContext } from "@/gui/contextProviders/contexts/ToastContext";
import { localizeUnitName } from "@/i18n/entityNames";

interface MissionCreatorCardProps {
  aircraft: Aircraft[];
  referencePoints: ReferencePoint[];
  targets: Target[];
  dialogMode?: boolean;
  handleCloseOnMap: () => void;
  createPatrolMission: (
    missionName: string,
    assignedUnits: string[],
    referencePoints: string[]
  ) => void;
  createStrikeMission: (
    missionName: string,
    assignedUnits: string[],
    targetIds: string[]
  ) => void;
}

const cardContentStyle = {
  display: "flex",
  flexDirection: "column",
  rowGap: "10px",
};

const closeButtonStyle = {
  bottom: 5.5,
};

const cardHeaderStyle = {
  backgroundColor: "#07111d",
  borderBottom: "1px solid rgba(76,201,240,0.16)",
  color: "#e5e7eb",
  height: "50px",
};

const cardStyle = {
  minWidth: "400px",
  maxWidth: "400px",
  minHeight: "200px",
  backgroundColor: "#050b13",
  border: "1px solid rgba(76,201,240,0.18)",
  boxShadow: "0 24px 90px rgba(0,0,0,0.46)",
  borderRadius: "16px",
};

const createPlaceholderMissionName = (missionType: "Patrol" | "Strike") => {
  const missionTypeLabel = missionType === "Patrol" ? "巡逻" : "打击";
  return `${missionTypeLabel}任务 #${Math.floor(Math.random() * 1000)}`;
};

function sortByLocalizedName<T extends { name: string }>(items: T[]) {
  return [...items].sort((a, b) =>
    localizeUnitName(a.name).localeCompare(localizeUnitName(b.name), "zh-Hans")
  );
}

const MissionCreatorCard = (props: MissionCreatorCardProps) => {
  const nodeRef = useRef<HTMLDivElement>(null);
  const [selectedMissionType, setSelectedMissionType] = useState<
    "Patrol" | "Strike" // TODO: Create enum for mission types
  >("Patrol");
  const [selectedAircraft, setSelectedAircraft] = useState<string[]>([]);
  const initialTargetId = sortByLocalizedName(props.targets)[0]?.id;
  const [selectedTargets, setSelectedTargets] = useState<string[]>(
    initialTargetId ? [initialTargetId] : []
  );
  const [selectedReferencePoints, setSelectedReferencePoints] = useState<
    string[]
  >([]);
  const [missionName, setMissionName] = useState<string>(
    createPlaceholderMissionName(selectedMissionType)
  );
  const toastContext = useContext(ToastContext);

  const validateMissionPropertiesInput = () => {
    if (missionName === "") {
      toastContext?.addToast("任务名称不能为空", "error");
      return false;
    }
    if (selectedAircraft.length === 0) {
      toastContext?.addToast("请至少选择一个执行单位", "error");
      return false;
    }
    if (
      selectedMissionType === "Patrol" &&
      selectedReferencePoints.length < 3
    ) {
      toastContext?.addToast("请至少选择三个参考点来定义巡逻区域", "error");
      return false;
    }
    if (selectedMissionType === "Strike" && selectedTargets.length === 0) {
      toastContext?.addToast("请至少选择一个打击目标", "error");
      return false;
    }
    return true;
  };

  const handleCreatePatrolMission = () => {
    if (!validateMissionPropertiesInput()) return;
    props.createPatrolMission(
      missionName,
      selectedAircraft,
      selectedReferencePoints
    );
    props.handleCloseOnMap();
  };

  const handleCreateStrikeMission = () => {
    if (!validateMissionPropertiesInput()) return;
    props.createStrikeMission(missionName, selectedAircraft, selectedTargets);
    props.handleCloseOnMap();
  };

  const handleCreateMission = () => {
    if (selectedMissionType === "Patrol") {
      handleCreatePatrolMission();
    } else if (selectedMissionType === "Strike") {
      handleCreateStrikeMission();
    }
  };

  const patrolMissionCreatorContent = (
    sortedReferencePoints: ReferencePoint[]
  ) => {
    return (
      <FormControl fullWidth sx={{ mb: 2 }}>
        <SelectField
          id="mission-creator-area-selector"
          labelId="mission-creator-area-selector-label"
          label="巡逻区域"
          value={selectedReferencePoints}
          selectItems={sortedReferencePoints.map((item) => {
            return {
              name: localizeUnitName(item.name),
              value: item.id,
            };
          })}
          onChange={(value) => {
            setSelectedReferencePoints(value as string[]);
          }}
          multiple
        />
      </FormControl>
    );
  };

  const StrikeMissionCreatorContent = (sortedTargets: Target[]) => {
    return (
      <FormControl fullWidth sx={{ mb: 2 }}>
        <SelectField
          id="mission-creator-target-selector"
          labelId="mission-creator-target-selector-label"
          label="打击目标"
          value={selectedTargets}
          selectItems={sortedTargets.map((item) => {
            return {
              name: localizeUnitName(item.name),
              value: item.id,
            };
          })}
          onChange={(value) => {
            setSelectedTargets([value] as string[]);
          }}
        />
      </FormControl>
    );
  };

  const cardContent = () => {
    const sortedAircraft = sortByLocalizedName(props.aircraft);
    const sortedReferencePoints = sortByLocalizedName(props.referencePoints);
    const sortedTargets = sortByLocalizedName(props.targets);

    let missionSpecificComponent = null;
    if (selectedMissionType === "Patrol") {
      missionSpecificComponent = patrolMissionCreatorContent(
        sortedReferencePoints
      );
    } else if (selectedMissionType === "Strike") {
      missionSpecificComponent = StrikeMissionCreatorContent(sortedTargets);
    }

    return (
      <CardContent sx={cardContentStyle}>
        {/** Mission Type Select Field */}
        <FormControl fullWidth sx={{ mb: 2 }}>
          <SelectField
            id="mission-creator-type-selector"
            selectItems={[
              { name: "巡逻任务", value: "Patrol" },
              { name: "打击任务", value: "Strike" },
            ]}
            labelId="mission-creator-type-selector-label"
            label="任务类型"
            value={selectedMissionType}
            onChange={(value) => {
              setSelectedMissionType(value as "Patrol" | "Strike");
              setMissionName(
                createPlaceholderMissionName(value as "Patrol" | "Strike")
              );
            }}
          />
        </FormControl>
        {/** Mission Name Text Field */}
        <TextField
          id="mission-name"
          label="任务名称"
          value={missionName}
          onChange={(event) => {
            setMissionName(event.target.value);
          }}
        />
        {/** Mission Unit Select Field */}
        <FormControl fullWidth sx={{ mb: 2 }}>
          <SelectField
            id="mission-creator-unit-selector"
            labelId="mission-creator-unit-selector-label"
            label="执行单位"
            selectItems={sortedAircraft.map((item) => {
              return {
                name: localizeUnitName(item.name),
                value: item.id,
              };
            })}
            value={selectedAircraft}
            onChange={(value) => {
              setSelectedAircraft(value as string[]);
            }}
            multiple
          />
        </FormControl>
        {/** Mission Specific Select Fields: Patrol Or Strike */}
        {missionSpecificComponent}
        {/** Create Mission Button */}
        <Stack spacing={2} direction={"row"} sx={{ justifyContent: "center" }}>
          <Button onClick={handleCreateMission} fullWidth variant="contained">
            创建任务
          </Button>
        </Stack>
      </CardContent>
    );
  };

  const resolvedCardStyle = props.dialogMode
    ? {
        ...cardStyle,
        maxWidth: "100%",
        minWidth: "100%",
      }
    : cardStyle;
  const rootStyle = props.dialogMode
    ? {
        position: "relative" as const,
        zIndex: "1001",
      }
    : {
        position: "absolute" as const,
        left: "20em",
        top: "5em",
        zIndex: "1001",
      };
  const card = (
    <Card ref={nodeRef} sx={resolvedCardStyle}>
      <CardHeader
        sx={cardHeaderStyle}
        action={
          <IconButton
            sx={closeButtonStyle}
            onClick={props.handleCloseOnMap}
            aria-label="关闭"
          >
            <CloseIcon color="error" />
          </IconButton>
        }
        title={
          <Typography variant="body1" component="h1" sx={{ pl: 1 }}>
            创建任务
          </Typography>
        }
      />
      {cardContent()}
    </Card>
  );

  return (
    <div style={rootStyle}>
      {props.dialogMode ? (
        card
      ) : (
        <Draggable nodeRef={nodeRef}>{card}</Draggable>
      )}
    </div>
  );
};

export default MissionCreatorCard;
