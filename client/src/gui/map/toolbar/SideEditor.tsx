import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Card from "@mui/material/Card";
import {
  Button,
  CardContent,
  Select,
  Stack,
  Box,
  MenuItem,
  FormControl,
  FormGroup,
  FormControlLabel,
  IconButton,
  Modal,
  Switch,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import TextField from "@/gui/shared/ui/TextField";
import Side from "@/game/Side";
import { SIDE_COLOR } from "@/utils/colors";
import EntityIcon from "@/gui/map/toolbar/EntityIcon";
import SelectField from "@/gui/shared/ui/SelectField";
import { SideDoctrine, DoctrineType } from "@/game/Doctrine";
import { localizeSideName } from "@/i18n/entityNames";

// Maps doctrine enum values (which are English sentences) to i18n keys so the
// switch labels can be displayed in the user's language.
const doctrineI18nKey = (k: string): string => {
  switch (k) {
    case DoctrineType.AIRCRAFT_ATTACK_HOSTILE:
      return "sideEditor.doctrine.aircraftAttackHostile";
    case DoctrineType.AIRCRAFT_CHASE_HOSTILE:
      return "sideEditor.doctrine.aircraftChaseHostile";
    case DoctrineType.AIRCRAFT_RTB_WHEN_OUT_OF_RANGE:
      return "sideEditor.doctrine.aircraftRtbWhenOutOfRange";
    case DoctrineType.AIRCRAFT_RTB_WHEN_STRIKE_MISSION_COMPLETE:
      return "sideEditor.doctrine.aircraftRtbWhenStrikeComplete";
    case DoctrineType.SAM_ATTACK_HOSTILE:
      return "sideEditor.doctrine.samAttackHostile";
    case DoctrineType.SHIP_ATTACK_HOSTILE:
      return "sideEditor.doctrine.shipAttackHostile";
    default:
      return k;
  }
};

interface SideEditorProps {
  open: boolean;
  anchorEl: HTMLElement | null;
  side: Side | undefined;
  sides: Side[];
  hostiles: string[];
  allies: string[];
  doctrine: SideDoctrine;
  updateSide: (
    sideId: string,
    sideName: string,
    sideColor: SIDE_COLOR,
    sideHostiles: string[],
    sideAllies: string[],
    sideDoctrine: SideDoctrine
  ) => void;
  addSide: (
    sideName: string,
    sideColor: SIDE_COLOR,
    sideHostiles: string[],
    sideAllies: string[],
    sideDoctrine: SideDoctrine
  ) => void;
  deleteSide: (sideId: string) => void;
  handleCloseOnMap: () => void;
}

const cardContentStyle = {
  display: "flex",
  flexDirection: "column",
  rowGap: "14px",
  px: 2.5,
  py: 2.5,
};

const cardStyle = {
  backgroundColor: "rgba(7, 17, 29, 0.96)",
  color: "#e2e8f0",
  border: "1px solid rgba(103, 232, 249, 0.18)",
  boxShadow:
    "0 24px 64px rgba(2, 6, 23, 0.6), inset 0 1px 0 rgba(103, 232, 249, 0.08)",
  borderRadius: "16px",
  backdropFilter: "blur(24px)",
  width: "min(560px, calc(100vw - 32px))",
  maxHeight: "calc(100vh - 48px)",
  overflow: "auto",
};

const bottomButtonsStackStyle = {
  display: "flex",
  justifyContent: "center",
  mt: 0.5,
};

const editorButtonStyle = {
  color: "#cffafe",
  borderRadius: "10px",
  textTransform: "none" as const,
  fontWeight: 600,
  letterSpacing: "0.02em",
  py: 1,
  boxShadow: "none",
  border: "1px solid rgba(103, 232, 249, 0.32)",
  backgroundColor: "rgba(103, 232, 249, 0.14)",
  "&:hover": {
    backgroundColor: "rgba(103, 232, 249, 0.22)",
    borderColor: "rgba(103, 232, 249, 0.55)",
    boxShadow: "0 0 24px rgba(103, 232, 249, 0.18)",
  },
};

const dangerButtonStyle = {
  color: "#fecaca",
  borderRadius: "10px",
  textTransform: "none" as const,
  fontWeight: 600,
  letterSpacing: "0.02em",
  py: 1,
  boxShadow: "none",
  border: "1px solid rgba(248, 113, 113, 0.32)",
  backgroundColor: "rgba(248, 113, 113, 0.12)",
  "&:hover": {
    backgroundColor: "rgba(248, 113, 113, 0.2)",
    borderColor: "rgba(248, 113, 113, 0.55)",
    boxShadow: "0 0 24px rgba(248, 113, 113, 0.18)",
  },
};

const darkTextFieldStyle = {
  mb: 0,
  borderRadius: "10px",
  "& .MuiOutlinedInput-root": {
    borderRadius: "10px",
    backgroundColor: "rgba(8, 21, 35, 0.65)",
    color: "#e2e8f0",
    "& fieldset": {
      borderColor: "rgba(103, 232, 249, 0.18)",
    },
    "&:hover fieldset": {
      borderColor: "rgba(103, 232, 249, 0.38)",
    },
    "&.Mui-focused fieldset": {
      borderColor: "rgba(103, 232, 249, 0.7)",
      boxShadow: "0 0 0 2px rgba(103, 232, 249, 0.12)",
    },
  },
  "& .MuiInputLabel-root": {
    color: "#94a3b8",
  },
  "& .MuiInputLabel-root.Mui-focused": {
    color: "#a5f3fc",
  },
  "& .MuiFormHelperText-root": {
    color: "#fca5a5",
    ml: 0.5,
  },
};

const darkSelectFieldStyle = {
  borderRadius: "10px",
  backgroundColor: "rgba(8, 21, 35, 0.65)",
  color: "#e2e8f0",
  "& .MuiOutlinedInput-notchedOutline": {
    borderColor: "rgba(103, 232, 249, 0.18)",
  },
  "&:hover .MuiOutlinedInput-notchedOutline": {
    borderColor: "rgba(103, 232, 249, 0.38)",
  },
  "&.Mui-focused .MuiOutlinedInput-notchedOutline": {
    borderColor: "rgba(103, 232, 249, 0.7)",
    boxShadow: "0 0 0 2px rgba(103, 232, 249, 0.12)",
  },
  "& .MuiSelect-icon": {
    color: "#a5f3fc",
  },
};

const darkCompactSelectStyle = {
  ...darkSelectFieldStyle,
  minWidth: 78,
  height: 56,
};

const darkFieldLabelStyle = {
  color: "#94a3b8",
  "&.Mui-focused": {
    color: "#a5f3fc",
  },
};

const darkSelectMenuProps = {
  PaperProps: {
    sx: {
      backgroundColor: "rgba(7, 17, 29, 0.96)",
      color: "#e2e8f0",
      border: "1px solid rgba(103, 232, 249, 0.2)",
      boxShadow:
        "0 24px 64px rgba(2, 6, 23, 0.6), inset 0 1px 0 rgba(103, 232, 249, 0.08)",
      borderRadius: "10px",
      backdropFilter: "blur(20px)",
      "& .MuiMenuItem-root": {
        color: "#e2e8f0",
        "&:hover": {
          backgroundColor: "rgba(103, 232, 249, 0.1)",
        },
        "&.Mui-selected": {
          backgroundColor: "rgba(103, 232, 249, 0.2)",
          "&:hover": {
            backgroundColor: "rgba(103, 232, 249, 0.28)",
          },
        },
      },
    },
  },
};

const doctrineSwitchStyle = {
  m: 0,
  py: 0.5,
  color: "#e2e8f0",
  "& .MuiFormControlLabel-label": {
    color: "#cbd5e1",
    fontSize: "0.875rem",
    ml: 0.5,
  },
  "& .MuiSwitch-switchBase.Mui-checked": {
    color: "#67e8f9",
  },
  "& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track": {
    backgroundColor: "#22d3ee",
    opacity: 0.55,
  },
};

const SideEditor = (props: SideEditorProps) => {
  const { t } = useTranslation();
  const sanitizeSideIds = (
    ids: string[],
    sides: Side[],
    selfId?: string
  ): string[] => {
    const seen = new Set<string>();
    const result: string[] = [];
    ids.forEach((id) => {
      if (!id || id === selfId || seen.has(id)) return;
      if (!sides.some((side) => side.id === id)) return;
      seen.add(id);
      result.push(id);
    });
    return result;
  };
  const [sideName, setSideName] = useState(props.side?.name ?? "");
  const [sideNameDirty, setSideNameDirty] = useState(false);
  const [sideColor, setSideColor] = useState<SIDE_COLOR>(
    props.side?.color ?? SIDE_COLOR.BLUE
  );
  const [sideNameError, setSideNameError] = useState(false);
  const [sideRelationshipsError, setSideRelationshipsError] = useState(false);
  const [sideHostiles, setSideHostiles] = useState<string[]>(
    sanitizeSideIds(props.hostiles, props.sides, props.side?.id)
  );
  const [sideAllies, setSideAllies] = useState<string[]>(
    sanitizeSideIds(props.allies, props.sides, props.side?.id)
  );
  const [sideDoctrine, setSideDoctrine] = useState<SideDoctrine>(
    props.doctrine
  );

  useEffect(() => {
    setSideName(props.side?.name ?? "");
    setSideNameDirty(false);
    setSideColor(props.side?.color ?? SIDE_COLOR.BLUE);
    setSideHostiles(
      sanitizeSideIds(props.hostiles, props.sides, props.side?.id)
    );
    setSideAllies(sanitizeSideIds(props.allies, props.sides, props.side?.id));
    setSideDoctrine(props.doctrine);
  }, [props.side, props.hostiles, props.allies, props.doctrine, props.sides]);

  const otherSides = props.sides.filter(
    (side: Side) =>
      (props.side?.id && side.id !== props.side?.id) || !props.side
  );

  const validateSidePropertiesInput = () => {
    if (sideName === "") {
      setSideNameError(true);
      return false;
    }
    if (sideHostiles.some((hostile) => sideAllies.includes(hostile))) {
      setSideRelationshipsError(true);
      return false;
    }
    setSideNameError(false);
    setSideRelationshipsError(false);
    return true;
  };

  const handleDeleteSide = () => {
    if (!props.side) return;
    props.deleteSide(props.side.id);
    props.handleCloseOnMap();
  };

  const handleUpdateSide = () => {
    if (!validateSidePropertiesInput() || !props.side) return;
    props.updateSide(
      props.side.id,
      sideNameDirty ? sideName : props.side.name,
      sideColor,
      sideHostiles,
      sideAllies,
      sideDoctrine
    );
    props.handleCloseOnMap();
  };

  const handleAddSide = () => {
    if (!validateSidePropertiesInput()) return;
    props.addSide(sideName, sideColor, sideHostiles, sideAllies, sideDoctrine);
    props.handleCloseOnMap();
  };

  const handleClose = () => {
    props.handleCloseOnMap();
  };

  const handleDoctrineChange = (doctrineType: string, value: boolean) => {
    setSideDoctrine((prevState) => ({
      ...prevState,
      [doctrineType]: value,
    }));
  };

  const cardContent = () => {
    return (
      <CardContent sx={cardContentStyle}>
        <Box
          sx={{
            mx: -2.5,
            mt: -2.5,
            mb: 0.25,
            px: 2.5,
            py: 1.75,
            borderBottom: "1px solid rgba(103, 232, 249, 0.14)",
            background:
              "linear-gradient(180deg, rgba(103, 232, 249, 0.08), rgba(8, 21, 35, 0))",
          }}
        >
          <Box sx={{ alignItems: "flex-start", display: "flex", gap: 2 }}>
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Box
                id="side-editor-title"
                sx={{ color: "#e2e8f0", fontSize: 15, fontWeight: 700 }}
              >
                {props.side ? "编辑阵营" : "新增阵营"}
              </Box>
              <Box sx={{ mt: 0.5, color: "#64748b", fontSize: 12 }}>
                配置阵营颜色、敌友关系与自动交战规则
              </Box>
            </Box>
            <IconButton
              aria-label="关闭阵营编辑器"
              onClick={handleClose}
              size="small"
              sx={{
                border: "1px solid rgba(148, 163, 184, 0.18)",
                color: "#94a3b8",
                backgroundColor: "rgba(15, 23, 42, 0.5)",
                "&:hover": {
                  backgroundColor: "rgba(248, 113, 113, 0.12)",
                  borderColor: "rgba(248, 113, 113, 0.32)",
                  color: "#fca5a5",
                },
              }}
            >
              <CloseIcon fontSize="small" />
            </IconButton>
          </Box>
        </Box>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "flex-start" }}>
          {/** Side Name Text Field */}
          <TextField
            id="side-name"
            label={t("sideEditor.name")}
            value={sideNameDirty ? sideName : localizeSideName(sideName)}
            onChange={(event) => {
              setSideName(event.target.value);
              setSideNameDirty(true);
            }}
            error={sideNameError}
            helperText={sideNameError ? t("sideEditor.nameRequired") : ""}
            fullWidth
            sx={darkTextFieldStyle}
          />
          {/** Side Color Select Field */}
          {/** Side Color Preview */}
          <Select
            value={sideColor}
            onChange={(e) => setSideColor(e.target.value as SIDE_COLOR)}
            sx={darkCompactSelectStyle}
            MenuProps={darkSelectMenuProps}
            inputProps={{ "aria-label": "阵营颜色" }}
            renderValue={() => (
              <Box
                display="flex"
                alignItems="center"
                justifyContent="center"
                gap={1}
              >
                <EntityIcon
                  type="circle"
                  color={sideColor}
                  width={20}
                  height={20}
                />
              </Box>
            )}
          >
            {Object.entries(SIDE_COLOR).map(([name, color]) => (
              <MenuItem
                key={color}
                value={color}
                sx={{
                  "&:hover": {
                    backgroundColor: "rgba(103, 232, 249, 0.1)",
                  },
                  "&.Mui-selected": {
                    backgroundColor: "rgba(103, 232, 249, 0.2)",
                    "&:hover": {
                      backgroundColor: "rgba(103, 232, 249, 0.28)",
                    },
                  },
                }}
              >
                <EntityIcon
                  type="circle"
                  color={color}
                  width={20}
                  height={20}
                />
              </MenuItem>
            ))}
          </Select>
        </Stack>
        <Box
          sx={{
            display: "grid",
            gap: 1.5,
            gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" },
          }}
        >
          <FormControl
            fullWidth
            sx={{ mb: 0.5 }}
            error={sideRelationshipsError}
          >
            <SelectField
              id="hostiles-selector"
              labelId="hostiles-selector-label"
              label={t("sideEditor.enemies")}
              labelSx={darkFieldLabelStyle}
              selectItems={otherSides.map((side: Side) => {
                return {
                  name: localizeSideName(side.name),
                  value: side.id,
                };
              })}
              value={sideHostiles}
              onChange={(value) => {
                setSideHostiles(value as string[]);
              }}
              sx={darkSelectFieldStyle}
              MenuProps={darkSelectMenuProps}
              multiple
            />
          </FormControl>
          <FormControl
            fullWidth
            sx={{ mb: 0.5 }}
            error={sideRelationshipsError}
          >
            <SelectField
              id="allies-selector"
              labelId="allies-selector-label"
              label={t("sideEditor.allies")}
              labelSx={darkFieldLabelStyle}
              selectItems={otherSides.map((side: Side) => {
                return {
                  name: localizeSideName(side.name),
                  value: side.id,
                };
              })}
              value={sideAllies}
              onChange={(value) => {
                setSideAllies(value as string[]);
              }}
              sx={darkSelectFieldStyle}
              MenuProps={darkSelectMenuProps}
              multiple
            />
          </FormControl>
        </Box>
        {sideRelationshipsError ? (
          <Box sx={{ mt: -0.5, color: "#fca5a5", fontSize: 12 }}>
            同一阵营不能同时设为敌方和友方。
          </Box>
        ) : null}
        <FormGroup
          sx={{
            mt: 0.5,
            px: 1.5,
            py: 1.25,
            borderRadius: "12px",
            border: "1px solid rgba(103, 232, 249, 0.14)",
            backgroundColor: "rgba(8, 21, 35, 0.5)",
            display: "grid",
            gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" },
            columnGap: 1.5,
          }}
        >
          {/** Doctrine Switches */}
          {Object.entries(sideDoctrine).map(([key, value]) => {
            return (
              <FormControlLabel
                key={key}
                control={
                  <Switch
                    checked={value}
                    onChange={(event) => {
                      handleDoctrineChange(key, event.target.checked);
                    }}
                    size="small"
                  />
                }
                label={t(doctrineI18nKey(key))}
                sx={doctrineSwitchStyle}
              />
            );
          })}
        </FormGroup>
        {/* Form Action/Buttons */}
        <Stack sx={bottomButtonsStackStyle} direction="row" spacing={1.5}>
          {!props.side ? (
            <Button
              fullWidth
              variant="contained"
              disableElevation
              onClick={handleAddSide}
              sx={editorButtonStyle}
            >
              {t("sideEditor.add")}
            </Button>
          ) : (
            <>
              <Button
                fullWidth
                variant="contained"
                disableElevation
                onClick={handleDeleteSide}
                sx={dangerButtonStyle}
              >
                {t("sideEditor.delete")}
              </Button>
              <Button
                fullWidth
                variant="contained"
                disableElevation
                onClick={handleUpdateSide}
                sx={editorButtonStyle}
              >
                {t("sideEditor.update")}
              </Button>
            </>
          )}
        </Stack>
      </CardContent>
    );
  };

  return (
    <Modal
      aria-labelledby="side-editor-title"
      open={props.open}
      onClose={handleClose}
      sx={{ zIndex: 1300 }}
    >
      <Box
        sx={{
          alignItems: "center",
          display: "flex",
          inset: 0,
          justifyContent: "center",
          p: 2,
          position: "fixed",
          backgroundColor: "rgba(1, 4, 10, 0.66)",
          backdropFilter: "blur(6px)",
        }}
      >
        <Card aria-modal="true" role="dialog" sx={cardStyle}>
          {cardContent()}
        </Card>
      </Box>
    </Modal>
  );
};

export default SideEditor;
