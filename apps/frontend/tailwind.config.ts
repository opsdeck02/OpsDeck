import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
    "../../packages/contracts/src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#ffffff",
        foreground: "#114d86",
        card: "hsl(0 0% 100%)",
        border: "#b7b7b2",
        muted: "#e6f2ff",
        mutedForeground: "#114d86",
        primary: "#114d86",
        primaryForeground: "#ffffff",
        accent: "#3a8dde",
        accentForeground: "#ffffff",
        success: "#3a8dde",
        warning: "#b7b7b2",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui"],
      },
      boxShadow: {
        panel: "0 18px 45px -22px rgba(17, 77, 134, 0.28)",
      },
      backgroundImage: {
        "hero-grid":
          "radial-gradient(circle at top left, rgba(58, 141, 222, 0.16), transparent 28%), radial-gradient(circle at bottom right, rgba(17, 77, 134, 0.13), transparent 34%)",
      },
    },
  },
  plugins: [],
};

export default config;
