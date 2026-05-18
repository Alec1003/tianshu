import { useContext } from "react";
import { useTranslation } from "react-i18next";
import { Chip } from "@mui/material";
import { unixToLocalDateTime } from "@/utils/dateTimeFunctions";
import { colorPalette } from "@/utils/constants";
import { ScenarioTimeContext } from "@/gui/contextProviders/contexts/ScenarioTimeContext";

const scenarioTimeDisplayStyle = {
  backgroundColor: colorPalette.lightGray,
  color: "#000",
  fontSize: "12px",
  fontStyle: "normal",
  fontWeight: 400,
};

export default function ScenarioTimeDisplay() {
  const currentScenarioTime = useContext(ScenarioTimeContext);
  const { t } = useTranslation();

  return (
    <Chip
      label={t("map.currentTime", {
        time: unixToLocalDateTime(currentScenarioTime),
      })}
      style={scenarioTimeDisplayStyle}
    />
  );
}
