import { createContext } from "react";
import type { TianShuThemeMode } from "@/gui/theme/tianshuTheme";

interface ThemeModeContextValue {
  mode: TianShuThemeMode;
  toggleMode: () => void;
  setMode: (mode: TianShuThemeMode) => void;
}

// Default value is intentionally a noop pair so consumers outside the
// provider (e.g. legacy code paths or unit tests) don't crash, but won't
// trigger any visible mode change.
export const ThemeModeContext = createContext<ThemeModeContextValue>({
  mode: "dark",
  toggleMode: () => undefined,
  setMode: () => undefined,
});
