export interface ThemeColors {
  // Surfaces
  bgPage: string;
  bgBase: string;
  bgOverlay: string;
  bgRaised: string;
  bgHover: string;
  bgActive: string;

  // Text
  textPrimary: string;
  textSecondary: string;
  textTertiary: string;
  textMuted: string;

  // Borders
  borderDefault: string;
  borderSubtle: string;
  borderStrong: string;

  // Accent (primary brand)
  accentBase: string;
  accentHover: string;
  accentText: string;
  accentSubtle: string;
  accentShadow: string;

  // Secondary accent (comments/feedback)
  secondaryBase: string;
  secondaryHover: string;
  secondaryText: string;
  secondarySubtle: string;

  // Semantic
  successText: string;
  successSubtle: string;
  errorText: string;
  errorSubtle: string;
  warningText: string;

  // Special surfaces
  inputBg: string;
  inputBorder: string;
  scrollbarThumb: string;
  scrollbarTrack: string;
}

export interface ThemePreset {
  id: string;
  name: string;
  dark: ThemeColors;
  light: ThemeColors;
}

export const themes: ThemePreset[] = [
  {
    id: "default",
    name: "Default",
    dark: {
      bgPage: "#030712",       // gray-950
      bgBase: "#111827",       // gray-900
      bgOverlay: "#1f2937",    // gray-800
      bgRaised: "#1f2937",     // gray-800
      bgHover: "#374151",      // gray-700
      bgActive: "#4b5563",     // gray-600

      textPrimary: "#f3f4f6",  // gray-100
      textSecondary: "#d1d5db", // gray-300
      textTertiary: "#9ca3af", // gray-400
      textMuted: "#6b7280",    // gray-500

      borderDefault: "#1f2937", // gray-800
      borderSubtle: "#374151",  // gray-700
      borderStrong: "#4b5563",  // gray-600

      accentBase: "#4f46e5",    // indigo-600
      accentHover: "#4338ca",   // indigo-700
      accentText: "#a5b4fc",    // indigo-300
      accentSubtle: "rgba(99, 102, 241, 0.15)",
      accentShadow: "rgba(49, 46, 129, 0.3)",

      secondaryBase: "#b45309",  // amber-700
      secondaryHover: "#d97706", // amber-600
      secondaryText: "#fcd34d",  // amber-300
      secondarySubtle: "rgba(251, 191, 36, 0.2)",

      successText: "#86efac",   // green-300
      successSubtle: "rgba(34, 197, 94, 0.1)",
      errorText: "#fca5a5",     // red-300
      errorSubtle: "rgba(239, 68, 68, 0.1)",
      warningText: "#fde047",   // yellow-300

      inputBg: "#111827",
      inputBorder: "#374151",
      scrollbarThumb: "#4b5563",
      scrollbarTrack: "#1f2937",
    },
    light: {
      bgPage: "#ffffff",
      bgBase: "#f9fafb",       // gray-50
      bgOverlay: "#ffffff",
      bgRaised: "#ffffff",
      bgHover: "#f3f4f6",      // gray-100
      bgActive: "#e5e7eb",     // gray-200

      textPrimary: "#111827",  // gray-900
      textSecondary: "#374151", // gray-700
      textTertiary: "#6b7280", // gray-500
      textMuted: "#9ca3af",    // gray-400

      borderDefault: "#e5e7eb", // gray-200
      borderSubtle: "#f3f4f6",  // gray-100
      borderStrong: "#d1d5db",  // gray-300

      accentBase: "#4f46e5",
      accentHover: "#4338ca",
      accentText: "#4f46e5",
      accentSubtle: "rgba(79, 70, 229, 0.08)",
      accentShadow: "rgba(79, 70, 229, 0.15)",

      secondaryBase: "#d97706",
      secondaryHover: "#b45309",
      secondaryText: "#92400e",
      secondarySubtle: "rgba(217, 119, 6, 0.1)",

      successText: "#16a34a",
      successSubtle: "rgba(22, 163, 74, 0.08)",
      errorText: "#dc2626",
      errorSubtle: "rgba(220, 38, 38, 0.08)",
      warningText: "#ca8a04",

      inputBg: "#ffffff",
      inputBorder: "#d1d5db",
      scrollbarThumb: "#d1d5db",
      scrollbarTrack: "#f3f4f6",
    },
  },
  {
    id: "solarized",
    name: "Solarized",
    dark: {
      bgPage: "#002b36",
      bgBase: "#073642",
      bgOverlay: "#094552",
      bgRaised: "#094552",
      bgHover: "#0a5a6b",
      bgActive: "#0c6f82",

      textPrimary: "#fdf6e3",
      textSecondary: "#eee8d5",
      textTertiary: "#93a1a1",
      textMuted: "#657b83",

      borderDefault: "#094552",
      borderSubtle: "#0a5a6b",
      borderStrong: "#586e75",

      accentBase: "#268bd2",
      accentHover: "#1a6ba8",
      accentText: "#93c7ef",
      accentSubtle: "rgba(38, 139, 210, 0.15)",
      accentShadow: "rgba(38, 139, 210, 0.2)",

      secondaryBase: "#b58900",
      secondaryHover: "#cb9a00",
      secondaryText: "#e6c34d",
      secondarySubtle: "rgba(181, 137, 0, 0.15)",

      successText: "#859900",
      successSubtle: "rgba(133, 153, 0, 0.1)",
      errorText: "#dc322f",
      errorSubtle: "rgba(220, 50, 47, 0.1)",
      warningText: "#cb4b16",

      inputBg: "#073642",
      inputBorder: "#586e75",
      scrollbarThumb: "#586e75",
      scrollbarTrack: "#073642",
    },
    light: {
      bgPage: "#fdf6e3",
      bgBase: "#eee8d5",
      bgOverlay: "#fdf6e3",
      bgRaised: "#fdf6e3",
      bgHover: "#e8e1cc",
      bgActive: "#ddd6c1",

      textPrimary: "#073642",
      textSecondary: "#586e75",
      textTertiary: "#657b83",
      textMuted: "#93a1a1",

      borderDefault: "#e8e1cc",
      borderSubtle: "#eee8d5",
      borderStrong: "#ddd6c1",

      accentBase: "#268bd2",
      accentHover: "#1a6ba8",
      accentText: "#268bd2",
      accentSubtle: "rgba(38, 139, 210, 0.1)",
      accentShadow: "rgba(38, 139, 210, 0.15)",

      secondaryBase: "#b58900",
      secondaryHover: "#a07800",
      secondaryText: "#7a5e00",
      secondarySubtle: "rgba(181, 137, 0, 0.1)",

      successText: "#859900",
      successSubtle: "rgba(133, 153, 0, 0.08)",
      errorText: "#dc322f",
      errorSubtle: "rgba(220, 50, 47, 0.08)",
      warningText: "#cb4b16",

      inputBg: "#fdf6e3",
      inputBorder: "#ddd6c1",
      scrollbarThumb: "#c4bcaa",
      scrollbarTrack: "#eee8d5",
    },
  },
  {
    id: "nord",
    name: "Nord",
    dark: {
      bgPage: "#2e3440",
      bgBase: "#3b4252",
      bgOverlay: "#434c5e",
      bgRaised: "#434c5e",
      bgHover: "#4c566a",
      bgActive: "#5a657a",

      textPrimary: "#eceff4",
      textSecondary: "#d8dee9",
      textTertiary: "#a3b1c2",
      textMuted: "#7b889b",

      borderDefault: "#434c5e",
      borderSubtle: "#4c566a",
      borderStrong: "#5a657a",

      accentBase: "#5e81ac",
      accentHover: "#4e6f96",
      accentText: "#88c0d0",
      accentSubtle: "rgba(94, 129, 172, 0.15)",
      accentShadow: "rgba(94, 129, 172, 0.2)",

      secondaryBase: "#d08770",
      secondaryHover: "#c77b63",
      secondaryText: "#ebcb8b",
      secondarySubtle: "rgba(208, 135, 112, 0.15)",

      successText: "#a3be8c",
      successSubtle: "rgba(163, 190, 140, 0.1)",
      errorText: "#bf616a",
      errorSubtle: "rgba(191, 97, 106, 0.1)",
      warningText: "#ebcb8b",

      inputBg: "#3b4252",
      inputBorder: "#4c566a",
      scrollbarThumb: "#4c566a",
      scrollbarTrack: "#3b4252",
    },
    light: {
      bgPage: "#eceff4",
      bgBase: "#e5e9f0",
      bgOverlay: "#eceff4",
      bgRaised: "#ffffff",
      bgHover: "#d8dee9",
      bgActive: "#c8d0de",

      textPrimary: "#2e3440",
      textSecondary: "#3b4252",
      textTertiary: "#4c566a",
      textMuted: "#7b889b",

      borderDefault: "#d8dee9",
      borderSubtle: "#e5e9f0",
      borderStrong: "#c8d0de",

      accentBase: "#5e81ac",
      accentHover: "#4e6f96",
      accentText: "#5e81ac",
      accentSubtle: "rgba(94, 129, 172, 0.1)",
      accentShadow: "rgba(94, 129, 172, 0.15)",

      secondaryBase: "#d08770",
      secondaryHover: "#c77b63",
      secondaryText: "#a3553f",
      secondarySubtle: "rgba(208, 135, 112, 0.1)",

      successText: "#6b8f56",
      successSubtle: "rgba(163, 190, 140, 0.1)",
      errorText: "#bf616a",
      errorSubtle: "rgba(191, 97, 106, 0.08)",
      warningText: "#b58a3a",

      inputBg: "#ffffff",
      inputBorder: "#d8dee9",
      scrollbarThumb: "#c8d0de",
      scrollbarTrack: "#e5e9f0",
    },
  },
  {
    id: "highcontrast",
    name: "High Contrast",
    dark: {
      bgPage: "#000000",
      bgBase: "#0a0a0a",
      bgOverlay: "#141414",
      bgRaised: "#1a1a1a",
      bgHover: "#262626",
      bgActive: "#333333",

      textPrimary: "#ffffff",
      textSecondary: "#e5e5e5",
      textTertiary: "#b3b3b3",
      textMuted: "#808080",

      borderDefault: "#333333",
      borderSubtle: "#262626",
      borderStrong: "#4d4d4d",

      accentBase: "#6366f1",
      accentHover: "#818cf8",
      accentText: "#c7d2fe",
      accentSubtle: "rgba(99, 102, 241, 0.2)",
      accentShadow: "rgba(99, 102, 241, 0.3)",

      secondaryBase: "#f59e0b",
      secondaryHover: "#fbbf24",
      secondaryText: "#fde68a",
      secondarySubtle: "rgba(245, 158, 11, 0.2)",

      successText: "#4ade80",
      successSubtle: "rgba(74, 222, 128, 0.15)",
      errorText: "#f87171",
      errorSubtle: "rgba(248, 113, 113, 0.15)",
      warningText: "#facc15",

      inputBg: "#0a0a0a",
      inputBorder: "#4d4d4d",
      scrollbarThumb: "#4d4d4d",
      scrollbarTrack: "#141414",
    },
    light: {
      bgPage: "#ffffff",
      bgBase: "#ffffff",
      bgOverlay: "#ffffff",
      bgRaised: "#ffffff",
      bgHover: "#f0f0f0",
      bgActive: "#e0e0e0",

      textPrimary: "#000000",
      textSecondary: "#1a1a1a",
      textTertiary: "#4d4d4d",
      textMuted: "#808080",

      borderDefault: "#cccccc",
      borderSubtle: "#e0e0e0",
      borderStrong: "#999999",

      accentBase: "#4338ca",
      accentHover: "#3730a3",
      accentText: "#4338ca",
      accentSubtle: "rgba(67, 56, 202, 0.1)",
      accentShadow: "rgba(67, 56, 202, 0.2)",

      secondaryBase: "#b45309",
      secondaryHover: "#92400e",
      secondaryText: "#78350f",
      secondarySubtle: "rgba(180, 83, 9, 0.1)",

      successText: "#15803d",
      successSubtle: "rgba(21, 128, 61, 0.08)",
      errorText: "#b91c1c",
      errorSubtle: "rgba(185, 28, 28, 0.08)",
      warningText: "#a16207",

      inputBg: "#ffffff",
      inputBorder: "#999999",
      scrollbarThumb: "#999999",
      scrollbarTrack: "#e0e0e0",
    },
  },
];

export type ThemeMode = "dark" | "light";

export interface ThemeOverrides {
  accentBase?: string;
  accentHover?: string;
  bgPage?: string;
  bgBase?: string;
}

export interface ThemeConfig {
  presetId: string;
  mode: ThemeMode;
  overrides?: ThemeOverrides;
}

export const DEFAULT_THEME_CONFIG: ThemeConfig = {
  presetId: "default",
  mode: "dark",
};

export function resolveTheme(config: ThemeConfig): ThemeColors {
  const preset = themes.find((t) => t.id === config.presetId) || themes[0];
  const base = config.mode === "dark" ? preset.dark : preset.light;
  if (!config.overrides) return base;
  return { ...base, ...config.overrides };
}

function hexToChannels(hex: string): string | null {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex.trim());
  if (!m) return null;
  return `${parseInt(m[1], 16)} ${parseInt(m[2], 16)} ${parseInt(m[3], 16)}`;
}

export function applyThemeToDOM(colors: ThemeColors): void {
  const root = document.documentElement;
  for (const [key, value] of Object.entries(colors)) {
    const cssVar = `--tc-${key.replace(/([A-Z])/g, "-$1").toLowerCase()}`;
    root.style.setProperty(cssVar, value);
    // Also expose an "r g b" channel form for solid hex colors so Tailwind
    // opacity modifiers (e.g. bg-tc-overlay/60) can compose alpha.
    const channels = hexToChannels(value);
    if (channels) {
      root.style.setProperty(`${cssVar}-rgb`, channels);
    }
  }
}
