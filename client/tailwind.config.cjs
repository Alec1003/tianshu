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
          bg: "#04070D",
          panel: "#0A1018",
          elevated: "#101923",
          control: "#111C28",
          line: "rgba(148,163,184,0.14)",
          border: "rgba(148,163,184,0.14)",
          active: "rgba(103,199,216,0.34)",
          accent: "#67C7D8",
          cyan: "#67C7D8",
          blue: "#6D91C6",
          red: "#C75B4A",
          amber: "#D6A449",
          green: "#69B982",
          text: "#E5E7EB",
          muted: "#CBD5E1",
          quiet: "#9AA6B5",
          faint: "#687586",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        "hud-cyan":
          "0 0 0 1px rgba(103,199,216,0.24), 0 12px 32px rgba(0,0,0,0.18)",
        "hud-red":
          "0 0 0 1px rgba(199,91,74,0.28), 0 12px 32px rgba(0,0,0,0.18)",
        "hud-green":
          "0 0 0 1px rgba(105,185,130,0.26), 0 12px 32px rgba(0,0,0,0.18)",
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
