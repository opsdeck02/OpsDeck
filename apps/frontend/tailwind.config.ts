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
        background: "#f6f8fb",
        foreground: "#172033",
        card: "#ffffff",
        border: "#d8dee8",
        muted: "#eef3f8",
        mutedForeground: "#667085",
        primary: "#164f86",
        primaryForeground: "#ffffff",
        accent: "#2f80d1",
        accentForeground: "#ffffff",
        success: "#1f9d6a",
        warning: "#c47a18",
        pressure: {
          blue: "#164f86",
          amber: "#c47a18",
          red: "#c73737",
          grey: "#667085",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui"],
      },
      boxShadow: {
        panel: "0 20px 50px -34px rgba(23, 32, 51, 0.32)",
        nerve: "0 24px 80px -40px rgba(199, 55, 55, 0.45)",
      },
      backgroundImage: {
        "hero-grid":
          "radial-gradient(circle at top left, rgba(47, 128, 209, 0.14), transparent 30%), radial-gradient(circle at bottom right, rgba(199, 55, 55, 0.08), transparent 34%)",
      },
    },
  },
  plugins: [],
};

export default config;
