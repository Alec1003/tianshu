const animate = require("tailwindcss-animate");

/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        tactical: {
          bg: "#050812",
          panel: "#08111C",
          elevated: "#0B1624",
          control: "#0B1826",
          border: "rgba(125,211,252,0.13)",
          active: "rgba(103,232,249,0.34)",
          cyan: "#38BDF8",
          blue: "#60A5FA",
          red: "#EF4444",
          amber: "#F59E0B",
          green: "#22C55E",
          text: "#E5E7EB",
          muted: "#CBD5E1",
          quiet: "#94A3B8",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        "hud-cyan":
          "0 0 0 1px rgba(103,232,249,0.26), 0 0 18px rgba(56,189,248,0.08)",
        "hud-red":
          "0 0 0 1px rgba(239,68,68,0.3), 0 0 18px rgba(239,68,68,0.08)",
        "hud-green":
          "0 0 0 1px rgba(34,197,94,0.28), 0 0 16px rgba(34,197,94,0.08)",
      },
      keyframes: {
        "tactical-pulse": {
          "0%, 100%": { opacity: "0.55", transform: "scale(1)" },
          "50%": { opacity: "1", transform: "scale(1.12)" },
        },
        "scan-line": {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        },
      },
      animation: {
        "tactical-pulse": "tactical-pulse 2.4s ease-in-out infinite",
        "scan-line": "scan-line 5s linear infinite",
      },
    },
  },
  plugins: [animate],
};
