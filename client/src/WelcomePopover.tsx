import React from "react";
import { useTranslation } from "react-i18next";
import {
  Popover,
  Box,
  Typography,
  Chip,
  Card,
  CardHeader,
  IconButton,
  CardContent,
  Link,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import { colorPalette } from "@/utils/constants";
import LoginButton from "@/gui/map/toolbar/Login";

interface WelcomePopoverProps {
  open: boolean;
  onClose: () => void;
}

const closeButtonStyle = {
  bottom: 5.5,
};

const cardStyle = {
  backgroundColor: colorPalette.lightGray,
};

const cardHeaderStyle = {
  backgroundColor: colorPalette.white,
  color: "black",
  height: "24px",
};

const WelcomePopover: React.FC<WelcomePopoverProps> = ({ open, onClose }) => {
  const { t } = useTranslation();
  const anchorPosition = {
    top: window.innerHeight / 2,
    left: window.innerWidth / 2,
  };

  return (
    <Popover
      open={open}
      onClose={onClose}
      anchorReference="anchorPosition"
      anchorPosition={anchorPosition}
      transformOrigin={{ vertical: "center", horizontal: "center" }}
      slotProps={{
        paper: { sx: { width: 750, maxWidth: "90vw", p: 0 } },
      }}
    >
      <Card sx={cardStyle}>
        <CardHeader
          sx={cardHeaderStyle}
          action={
            <IconButton
              type="button"
              sx={closeButtonStyle}
              onClick={onClose}
              aria-label={t("common.close")}
            >
              <CloseIcon color="error" />
            </IconButton>
          }
        />
        <CardContent sx={{ display: "flex", minHeight: 300 }}>
          {/* LEFT SIDE */}
          <Box
            sx={{
              flex: 1,
              p: 3,
              borderRight: 1,
              borderColor: "divider",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Typography variant="h5" gutterBottom>
              {t("welcome.title")}
            </Typography>
            <Typography gutterBottom>{t("welcome.intro")}</Typography>
            <Typography gutterBottom>
              {t("welcome.classification")}
            </Typography>
          </Box>

          {/* RIGHT SIDE */}
          <Box
            sx={{
              flex: 1,
              p: 3,
              display: "flex",
              flexDirection: "column",
              gap: 2,
              justifyContent: "center",
            }}
          >
            <Chip
              key={"build-scenario"}
              label={t("welcome.buildScenario")}
              clickable
              variant="outlined"
              sx={{ alignSelf: "stretch", py: 1 }}
              onClick={onClose}
            />
            <LoginButton />
            <Typography variant="body2">
              {t("welcome.privacyAgreement")}{" "}
              <Link
                href="http://panopticon-ai.com/privacy"
                target="_blank"
                rel="noopener"
                underline="hover"
              >
                {t("welcome.privacyPolicy")}
              </Link>
            </Typography>
          </Box>
        </CardContent>
      </Card>
    </Popover>
  );
};

export default WelcomePopover;
