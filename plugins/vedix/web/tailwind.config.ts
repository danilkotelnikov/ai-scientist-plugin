import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Vedix brand palette — deliberately conservative so the manuscript
        // preview keeps focus on the page content, not the chrome.
        brand: {
          50: "#f4f5fb",
          500: "#3a3f7a",
          700: "#262a52",
          900: "#11132a",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
