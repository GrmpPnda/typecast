/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        tc: {
          page: "rgb(var(--tc-bg-page-rgb) / <alpha-value>)",
          base: "rgb(var(--tc-bg-base-rgb) / <alpha-value>)",
          overlay: "rgb(var(--tc-bg-overlay-rgb) / <alpha-value>)",
          raised: "rgb(var(--tc-bg-raised-rgb) / <alpha-value>)",
          hover: "rgb(var(--tc-bg-hover-rgb) / <alpha-value>)",
          active: "rgb(var(--tc-bg-active-rgb) / <alpha-value>)",
          input: "var(--tc-input-bg)",
          accent: "rgb(var(--tc-accent-base-rgb) / <alpha-value>)",
          "accent-hover": "var(--tc-accent-hover)",
          "accent-subtle": "var(--tc-accent-subtle)",
          secondary: "rgb(var(--tc-secondary-base-rgb) / <alpha-value>)",
          "secondary-hover": "rgb(var(--tc-secondary-hover-rgb) / <alpha-value>)",
          "secondary-subtle": "var(--tc-secondary-subtle)",
          "error-subtle": "var(--tc-error-subtle)",
          "success-subtle": "var(--tc-success-subtle)",
          // Solid status fills, for indicators like connection dots. The text
          // and border equivalents live under textColor/borderColor below.
          success: "rgb(var(--tc-success-text-rgb) / <alpha-value>)",
          error: "rgb(var(--tc-error-text-rgb) / <alpha-value>)",
          warning: "var(--tc-warning-text)",
          muted: "var(--tc-text-muted)",
        },
      },
      textColor: {
        tc: {
          primary: "var(--tc-text-primary)",
          secondary: "var(--tc-text-secondary)",
          tertiary: "var(--tc-text-tertiary)",
          muted: "var(--tc-text-muted)",
          accent: "rgb(var(--tc-accent-text-rgb) / <alpha-value>)",
          "secondary-accent": "rgb(var(--tc-secondary-text-rgb) / <alpha-value>)",
          success: "rgb(var(--tc-success-text-rgb) / <alpha-value>)",
          error: "rgb(var(--tc-error-text-rgb) / <alpha-value>)",
          warning: "var(--tc-warning-text)",
        },
      },
      borderColor: {
        tc: {
          default: "rgb(var(--tc-border-default-rgb) / <alpha-value>)",
          subtle: "rgb(var(--tc-border-subtle-rgb) / <alpha-value>)",
          strong: "rgb(var(--tc-border-strong-rgb) / <alpha-value>)",
          input: "var(--tc-input-border)",
          accent: "rgb(var(--tc-accent-base-rgb) / <alpha-value>)",
          error: "rgb(var(--tc-error-text-rgb) / <alpha-value>)",
          success: "rgb(var(--tc-success-text-rgb) / <alpha-value>)",
          secondary: "rgb(var(--tc-secondary-base-rgb) / <alpha-value>)",
        },
      },
      boxShadowColor: {
        tc: {
          accent: "var(--tc-accent-shadow)",
        },
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
