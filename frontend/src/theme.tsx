import { createContext, useCallback, useContext, useEffect, useState } from "react";
import {
  ThemeConfig,
  ThemeMode,
  ThemeOverrides,
  DEFAULT_THEME_CONFIG,
  applyThemeToDOM,
  resolveTheme,
} from "./themes";

interface ThemeContextValue {
  config: ThemeConfig;
  mode: ThemeMode;
  setPreset: (presetId: string) => void;
  setMode: (mode: ThemeMode) => void;
  toggleMode: () => void;
  setOverrides: (overrides: ThemeOverrides | undefined) => void;
}

const STORAGE_KEY = "typecast_theme";

function loadConfig(): ThemeConfig {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return JSON.parse(stored);
  } catch {}
  return DEFAULT_THEME_CONFIG;
}

function saveConfig(config: ThemeConfig): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
}

const ThemeContext = createContext<ThemeContextValue>({
  config: DEFAULT_THEME_CONFIG,
  mode: "dark",
  setPreset: () => {},
  setMode: () => {},
  toggleMode: () => {},
  setOverrides: () => {},
});

export function useTheme() {
  return useContext(ThemeContext);
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfig] = useState<ThemeConfig>(loadConfig);

  useEffect(() => {
    const colors = resolveTheme(config);
    applyThemeToDOM(colors);
    saveConfig(config);
    document.documentElement.setAttribute("data-theme-mode", config.mode);
  }, [config]);

  const setPreset = useCallback((presetId: string) => {
    setConfig((prev) => ({ ...prev, presetId, overrides: undefined }));
  }, []);

  const setMode = useCallback((mode: ThemeMode) => {
    setConfig((prev) => ({ ...prev, mode }));
  }, []);

  const toggleMode = useCallback(() => {
    setConfig((prev) => ({ ...prev, mode: prev.mode === "dark" ? "light" : "dark" }));
  }, []);

  const setOverrides = useCallback((overrides: ThemeOverrides | undefined) => {
    setConfig((prev) => ({ ...prev, overrides }));
  }, []);

  return (
    <ThemeContext.Provider value={{ config, mode: config.mode, setPreset, setMode, toggleMode, setOverrides }}>
      {children}
    </ThemeContext.Provider>
  );
}
