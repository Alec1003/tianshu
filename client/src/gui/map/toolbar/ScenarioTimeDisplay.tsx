import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Chip } from "@mui/material";
import { unixToLocalDateTime } from "@/utils/dateTimeFunctions";
import { colorPalette } from "@/utils/constants";

const scenarioTimeDisplayStyle = {
  backgroundColor: colorPalette.lightGray,
  color: "#000",
  fontSize: "12px",
  fontStyle: "normal",
  fontWeight: 400,
};

export default function ScenarioTimeDisplay() {
  const [currentTime, setCurrentTime] = useState(() =>
    Math.floor(Date.now() / 1000)
  );
  const { t } = useTranslation();

  useEffect(() => {
    const id = window.setInterval(() => {
      setCurrentTime(Math.floor(Date.now() / 1000));
    }, 1000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <Chip
      label={t("map.currentTime", {
        time: unixToLocalDateTime(currentTime),
      })}
      style={scenarioTimeDisplayStyle}
    />
  );
}
