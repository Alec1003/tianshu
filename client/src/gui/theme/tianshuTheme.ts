import { createTheme, type Theme } from "@mui/material/styles";

// TianShu tactical palette.
// Dark = primary (operations) mode. Sand/Light = secondary (briefing) mode.
// Accent ramps stay on neutral metal grays plus a single mil-green primary
// to keep the UI legible over satellite / vector base maps.
const TACTICAL_GREEN = "#4ec07a";
const TACTICAL_GREEN_DIM = "#3aa166";
const ALERT_AMBER = "#e0a536";
const ALERT_RED = "#c4452f";

const DARK = {
  bg: "#0d1117",
  surface: "#161b22",
  surfaceElev: "#1c2330",
  border: "#30363d",
  borderStrong: "#46505c",
  text: "#d1d5db",
  textDim: "#8b95a3",
};

const LIGHT = {
  bg: "#f3f1ea",
  surface: "#ffffff",
  surfaceElev: "#fbfaf3",
  border: "#c8c4b8",
  borderStrong: "#9b9685",
  text: "#1f2328",
  textDim: "#5a5e66",
};

const SHARED_TYPOGRAPHY = {
  fontFamily: [
    '"JetBrains Mono"',
    '"Roboto Mono"',
    "Roboto",
    "Helvetica",
    "Arial",
    "sans-serif",
  ].join(","),
  h6: {
    fontWeight: 600,
    letterSpacing: "0.06em",
    textTransform: "uppercase" as const,
  },
  body2: { fontSize: 12 },
  button: {
    fontWeight: 600,
    letterSpacing: "0.05em",
    textTransform: "uppercase" as const,
  },
};

export const tianshuDarkTheme: Theme = createTheme({
  palette: {
    mode: "dark",
    primary: { main: TACTICAL_GREEN, dark: TACTICAL_GREEN_DIM },
    secondary: { main: ALERT_AMBER },
    error: { main: ALERT_RED },
    background: { default: DARK.bg, paper: DARK.surface },
    text: { primary: DARK.text, secondary: DARK.textDim },
    divider: DARK.border,
  },
  shape: { borderRadius: 2 },
  typography: SHARED_TYPOGRAPHY,
  components: {
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
          border: `1px solid ${DARK.border}`,
        },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: DARK.surfaceElev,
          color: DARK.text,
          border: `1px solid ${DARK.border}`,
          fontSize: 11,
          letterSpacing: "0.04em",
        },
        arrow: { color: DARK.surfaceElev },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          borderRadius: 2,
          color: DARK.text,
          "&:hover": { backgroundColor: "rgba(78,192,122,0.12)" },
        },
      },
    },
  },
});

export const tianshuLightTheme: Theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#2f6f3a", dark: "#1f5026" },
    secondary: { main: "#c4972a" },
    error: { main: "#9c2418" },
    background: { default: LIGHT.bg, paper: LIGHT.surface },
    text: { primary: LIGHT.text, secondary: LIGHT.textDim },
    divider: LIGHT.border,
  },
  shape: { borderRadius: 2 },
  typography: SHARED_TYPOGRAPHY,
  components: {
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
          border: `1px solid ${LIGHT.border}`,
        },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: LIGHT.text,
          color: LIGHT.surface,
          fontSize: 11,
          letterSpacing: "0.04em",
        },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          borderRadius: 2,
          color: LIGHT.text,
          "&:hover": { backgroundColor: "rgba(47,111,58,0.12)" },
        },
      },
    },
  },
});

export type TianShuThemeMode = "dark" | "light";

export function getTianShuTheme(mode: TianShuThemeMode): Theme {
  return mode === "dark" ? tianshuDarkTheme : tianshuLightTheme;
}
