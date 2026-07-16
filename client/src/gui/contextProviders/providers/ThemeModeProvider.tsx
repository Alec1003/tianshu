import { useCallback, useEffect, useMemo, useState } from "react";
import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";

import { ThemeModeContext } from "@/gui/contextProviders/contexts/ThemeModeContext";
import {
  getTianShuTheme,
  type TianShuThemeMode,
} from "@/gui/theme/tianshuTheme";
import { writeStorageItem } from "@/lib/legacyStorage";

const STORAGE_KEY = "tianshu.themeMode";

function detectInitialMode(): TianShuThemeMode {
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
    void next;
    setModeState("dark");
  }, []);

  const toggleMode = useCallback(() => {
    setModeState("dark");
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
