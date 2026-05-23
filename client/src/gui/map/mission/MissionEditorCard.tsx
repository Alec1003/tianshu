import React, { useEffect, useState, useContext } from "react";
import Draggable from "react-draggable";
import Card from "@mui/material/Card";
import CardHeader from "@mui/material/CardHeader";
import CloseIcon from "@mui/icons-material/Close";
import {
  Button,
  CardContent,
  FormControl,
  IconButton,
  Stack,
  Typography,
} from "@mui/material";
import PatrolMission from "@/game/mission/PatrolMission";
import Aircraft from "@/game/units/Aircraft";
import ReferencePoint from "@/game/units/ReferencePoint";
import StrikeMission from "@/game/mission/StrikeMission";
import type { Target } from "@/game/Target";
import SelectField from "@/gui/shared/ui/SelectField";
import TextField from "@/gui/shared/ui/TextField";
import type { Mission } from "@/game/Game";
import { ToastContext } from "@/gui/contextProviders/contexts/ToastContext";
import { localizeUnitName } from "@/i18n/entityNames";

interface MissionEditorCardProps {
  dialogMode?: boolean;
  missions: Mission[];
  selectedMissionId: string;
  aircraft: Aircraft[];
  referencePoints: ReferencePoint[];
  targets: Target[];
  updatePatrolMission: (
    missionId: string,
    missionName: string,
    assignedUnits: string[],
    referencePoints: string[]
  ) => void;
  updateStrikeMission: (
    missionId: string,
    missionName: string,
    assignedUnits: string[],
    targetIds: string[]
  ) => void;
  deleteMission: (missionId: string) => void;
  handleCloseOnMap: () => void;
}

const missionTypes = ["Patrol", "Strike"];

const cardContentStyle = {
  display: "flex",
  flexDirection: "column",
  rowGap: "10px",
};

const closeButtonStyle = {
  bottom: 5.5,
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

const cardHeaderStyle = {
  backgroundColor: "#07111d",
  borderBottom: "1px solid rgba(76,201,240,0.16)",
  color: "#e5e7eb",
  height: "50px",
};

const bottomButtonsStackStyle = {
  display: "flex",
  justifyContent: "center",
};

const editorButtonStyle = {
  color: "#ffffff",
};

const fieldStyle = {
  mb: 2,
  borderRadius: 2,
  bgcolor: "rgba(15,23,42,0.86)",
  color: "#e5e7eb",
  "& .MuiOutlinedInput-root": { borderRadius: 2 },
  "& .MuiOutlinedInput-notchedOutline": {
    borderColor: "rgba(76,201,240,0.22)",
  },
  "&:hover .MuiOutlinedInput-notchedOutline": {
    borderColor: "rgba(76,201,240,0.38)",
  },
  "& .MuiSvgIcon-root": { color: "#94a3b8" },
  "& .MuiInputBase-input": { color: "#e5e7eb" },
};

const labelStyle = {
  color: "#94a3b8",
};

const parseSelectedMissionType = (selectedMission: Mission): string => {
  return selectedMission instanceof PatrolMission ? "Patrol" : "Strike";
};

const missionTypeLabel = (missionType: string): string => {
  return missionType === "Patrol" ? "巡逻任务" : "打击任务";
};

function sortByLocalizedName<T extends { name: string }>(items: T[]) {
  return [...items].sort((a, b) =>
    localizeUnitName(a.name).localeCompare(localizeUnitName(b.name), "zh-Hans")
  );
}

const MissionEditorCard = (props: MissionEditorCardProps) => {
  const nodeRef = React.useRef(null);
  const [selectedMission, setSelectedMission] = useState<Mission>(
    props.missions.find((mission) => mission.id === props.selectedMissionId) ||
      props.missions[0]
  );
  const [selectedMissionType, setSelectedMissionType] = useState<string>(
    parseSelectedMissionType(selectedMission)
  );
  const [selectedAircraft, setSelectedAircraft] = useState<string[]>(
    selectedMission.assignedUnitIds
  );
  const [selectedReferencePoints, setSelectedReferencePoints] = useState<
    string[]
  >(
    selectedMission instanceof PatrolMission
      ? selectedMission.assignedArea.map((point) => point.id)
      : []
  );
  const [selectedTargets, setSelectedTargets] = useState<string[]>(
    selectedMission instanceof StrikeMission
      ? selectedMission.assignedTargetIds
      : []
  );
  const [missionName, setMissionName] = useState<string>(selectedMission.name);
  const toastContext = useContext(ToastContext);

  useEffect(() => {
    const newSelectedMission =
      props.missions.find(
        (mission) => mission.id === props.selectedMissionId
      ) || props.missions[0];

    if (newSelectedMission) {
      setSelectedMission(newSelectedMission);
      setMissionName(newSelectedMission.name);
      setSelectedAircraft(newSelectedMission.assignedUnitIds);

      if (newSelectedMission instanceof PatrolMission) {
        setSelectedReferencePoints(
          newSelectedMission.assignedArea.map((point) => point.id)
        );
        setSelectedTargets([]);
      } else if (newSelectedMission instanceof StrikeMission) {
        setSelectedTargets(newSelectedMission.assignedTargetIds);
        setSelectedReferencePoints([]);
      }

      setSelectedMissionType(parseSelectedMissionType(newSelectedMission));
    }
  }, [props.selectedMissionId, props.missions]);

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
      selectedMission instanceof PatrolMission &&
      selectedReferencePoints.length < 3
    ) {
      toastContext?.addToast("请至少选择三个参考点定义巡逻区域", "error");
      return false;
    }
    if (
      selectedMission instanceof StrikeMission &&
      selectedTargets.length === 0
    ) {
      toastContext?.addToast("请至少选择一个打击目标", "error");
      return false;
    }
    return true;
  };

  const handleDeleteMission = () => {
    props.deleteMission(selectedMission.id);
    props.handleCloseOnMap();
  };

  const handleUpdateMission = () => {
    if (!validateMissionPropertiesInput()) return;
    if (selectedMissionType === "Patrol") {
      props.updatePatrolMission(
        selectedMission.id,
        missionName,
        selectedAircraft,
        selectedReferencePoints
      );
    } else if (selectedMissionType === "Strike") {
      props.updateStrikeMission(
        selectedMission.id,
        missionName,
        selectedAircraft,
        selectedTargets
      );
    }
    props.handleCloseOnMap();
  };

  const handleClose = () => {
    props.handleCloseOnMap();
  };

  const handleMissionChange = (newSelectedMission: string) => {
    const searchedSelectedMission = props.missions.find(
      (mission) => mission.id === newSelectedMission
    );

    if (!searchedSelectedMission) return;

    setSelectedMission(searchedSelectedMission);
    setMissionName(searchedSelectedMission.name);
    setSelectedAircraft(searchedSelectedMission.assignedUnitIds);

    if (searchedSelectedMission instanceof PatrolMission) {
      setSelectedReferencePoints(
        searchedSelectedMission.assignedArea.map((point) => point.id)
      );
      setSelectedTargets([]);
    } else if (searchedSelectedMission instanceof StrikeMission) {
      setSelectedTargets(searchedSelectedMission.assignedTargetIds);
      setSelectedReferencePoints([]);
    }

    setSelectedMissionType(parseSelectedMissionType(searchedSelectedMission));
  };

  const patrolMissionEditorContent = (
    sortedReferencePoints: ReferencePoint[]
  ) => {
    return (
      <FormControl fullWidth sx={{ mb: 2 }}>
        <SelectField
          id="mission-editor-area-selector"
          labelId="mission-editor-area-selector-label"
          label="巡逻区域"
          labelSx={labelStyle}
          sx={fieldStyle}
          selectItems={sortedReferencePoints.map((item) => {
            return {
              name: localizeUnitName(item.name),
              value: item.id,
            };
          })}
          value={selectedReferencePoints}
          onChange={(value) => {
            setSelectedReferencePoints(value as string[]);
          }}
          multiple
        />
      </FormControl>
    );
  };

  const StrikeMissionEditorContent = (sortedTargets: Target[]) => {
    return (
      <FormControl fullWidth sx={{ mb: 2 }}>
        <SelectField
          id="mission-editor-target-selector"
          labelId="mission-editor-target-selector-label"
          label="打击目标"
          labelSx={labelStyle}
          sx={fieldStyle}
          selectItems={sortedTargets.map((item) => {
            return {
              name: localizeUnitName(item.name),
              value: item.id,
            };
          })}
          value={selectedTargets}
          onChange={(value) => {
            setSelectedTargets([value] as string[]);
          }}
        />
      </FormControl>
    );
  };

  const cardContent = () => {
    const missionIds = props.missions.map((mission) => mission.id);
    const missionNames = props.missions.map((mission) =>
      localizeUnitName(mission.name)
    );
    const sortedAircraft = sortByLocalizedName(props.aircraft);
    const sortedReferencePoints = sortByLocalizedName(props.referencePoints);
    const sortedTargets = sortByLocalizedName(props.targets);

    let missionSpecificComponent = null;
    if (selectedMissionType === "Patrol") {
      missionSpecificComponent = patrolMissionEditorContent(
        sortedReferencePoints
      );
    } else if (selectedMissionType === "Strike") {
      missionSpecificComponent = StrikeMissionEditorContent(sortedTargets);
    }

    return (
      <CardContent sx={cardContentStyle}>
        {/** Missions Select Field */}
        <FormControl fullWidth sx={{ mb: 2 }}>
          <SelectField
            id="mission-editor-mission-selector"
            label="任务"
            labelId="mission-editor-mission-selector-label"
            labelSx={labelStyle}
            sx={fieldStyle}
            selectItems={missionNames.map((item, index) => {
              return {
                name: item,
                value: missionIds[index],
              };
            })}
            value={selectedMission.id}
            onChange={(value) => {
              handleMissionChange(value as string);
            }}
          />
        </FormControl>
        {/** Mission Type Select Field */}
        <FormControl fullWidth sx={{ mb: 2 }}>
          <SelectField
            id="mission-editor-type-selector"
            label="任务类型"
            labelId="mission-editor-type-selector-label"
            labelSx={labelStyle}
            sx={fieldStyle}
            disabled
            selectItems={missionTypes.map((item) => {
              return {
                name: missionTypeLabel(item),
                value: item,
              };
            })}
            value={selectedMissionType}
            onChange={() => {}}
          />
        </FormControl>
        {/** Mission Name Text Field */}
        <TextField
          id="mission-name"
          label="任务名称"
          sx={fieldStyle}
          InputLabelProps={{ sx: labelStyle }}
          value={missionName}
          onChange={(event) => {
            setMissionName(event.target.value);
          }}
        />
        {/** Mission Unit Select Field */}
        <FormControl fullWidth sx={{ mb: 2 }}>
          <SelectField
            id="mission-editor-unit-selector"
            label="执行单位"
            labelId="mission-editor-unit-selector-label"
            labelSx={labelStyle}
            sx={fieldStyle}
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
        {/* Form Action/Buttons */}
        <Stack sx={bottomButtonsStackStyle} direction="row" spacing={2}>
          <Button
            fullWidth
            variant="contained"
            color="primary"
            onClick={handleUpdateMission}
            sx={editorButtonStyle}
          >
            保存修改
          </Button>
          <Button
            fullWidth
            variant="contained"
            color="error"
            onClick={handleDeleteMission}
            sx={editorButtonStyle}
          >
            删除任务
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
            type="button"
            sx={closeButtonStyle}
            onClick={handleClose}
            aria-label="关闭"
          >
            <CloseIcon color="error" />
          </IconButton>
        }
        title={
          <Typography variant="body1" component="h1" sx={{ pl: 1 }}>
            编辑任务
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

export default MissionEditorCard;
