import { useCallback, useEffect, useMemo, useState } from "react";
import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";

import { ThemeModeContext } from "@/gui/contextProviders/contexts/ThemeModeContext";
import {
  getTianShuTheme,
  type TianShuThemeMode,
} from "@/gui/theme/tianshuTheme";
import { readStorageItem, writeStorageItem } from "@/lib/legacyStorage";

const STORAGE_KEY = "tianshu.themeMode";

function detectInitialMode(): TianShuThemeMode {
  if (typeof window === "undefined") return "dark";
  const stored = readStorageItem(STORAGE_KEY);
  if (stored === "dark" || stored === "light") return stored;
  // Default to dark (operations) regardless of OS preference; TianShu is
  // a tactical platform that favors dark mode out of the box.
  return "dark";
}

export const ThemeModeProvider = ({
  children,
}: {
  children: React.ReactNode;
}) => {
  const [mode, setModeState] = useState<TianShuThemeMode>(detectInitialMode);

  useEffect(() => {
    if (typeof window !== "undefined") {
      writeStorageItem(STORAGE_KEY, mode);
    }
    if (typeof document !== "undefined") {
      const root = document.documentElement;
      root.classList.toggle("dark", mode === "dark");
      root.dataset.theme = mode;
      root.style.colorScheme = mode;
    }
  }, [mode]);

  const setMode = useCallback((next: TianShuThemeMode) => {
    setModeState(next);
  }, []);

  const toggleMode = useCallback(() => {
    setModeState((prev) => (prev === "dark" ? "light" : "dark"));
  }, []);

  const ctx = useMemo(
    () => ({ mode, setMode, toggleMode }),
    [mode, setMode, toggleMode]
  );

  const theme = useMemo(() => getTianShuTheme(mode), [mode]);

  return (
    <ThemeModeContext.Provider value={ctx}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </ThemeModeContext.Provider>
  );
};
