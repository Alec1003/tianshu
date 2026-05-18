import { useContext } from "react";
import { useTranslation } from "react-i18next";
import { Chip } from "@mui/material";
import { colorPalette } from "@/utils/constants";
import { MouseMapCoordinatesContext } from "@/gui/contextProviders/contexts/MouseMapCoordinatesContext";

const mouseMapCoordinatesDisplayStyle = {
  backgroundColor: colorPalette.lightGray,
  color: "#000",
  fontSize: "12px",
  fontStyle: "normal",
  fontWeight: 400,
};

export default function MouseMapCoordinatesDisplay() {
  const { latitude, longitude } = useContext(MouseMapCoordinatesContext);
  const { t } = useTranslation();

  return (
    <Chip
      label={t("map.coordinates", {
        lat: latitude.toFixed(2),
        lon: longitude.toFixed(2),
      })}
      style={mouseMapCoordinatesDisplayStyle}
    />
  );
}
