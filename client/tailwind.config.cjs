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
          bg: "#0B0F14",
          panel: "#111827",
          elevated: "#1A2233",
          cyan: "#4CC9F0",
          blue: "#4895EF",
          red: "#EF233C",
          green: "#06D6A0",
          text: "#E5E7EB",
          muted: "#94A3B8",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        "hud-cyan":
          "0 0 0 1px rgba(76,201,240,0.35), 0 0 36px rgba(76,201,240,0.16)",
        "hud-red":
          "0 0 0 1px rgba(239,35,60,0.34), 0 0 32px rgba(239,35,60,0.14)",
        "hud-green":
          "0 0 0 1px rgba(6,214,160,0.3), 0 0 28px rgba(6,214,160,0.14)",
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
