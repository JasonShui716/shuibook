import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["'Noto Serif SC'", "serif"],
        body: ["'Noto Sans SC'", "sans-serif"],
      },
      colors: {
        ink: {
          900: "#0f172a",
          700: "#334155",
          600: "#475569",
          300: "#cbd5f5",
        },
        cream: {
          50: "#fbf7f3",
          100: "#f4ece5",
        },
        coral: {
          400: "#f07f5a",
          500: "#ea6a45",
        },
        jade: {
          500: "#2f8f6e",
        },
      },
      boxShadow: {
        soft: "0 12px 30px rgba(15, 23, 42, 0.12)",
      },
      backgroundImage: {
        "mesh": "radial-gradient(circle at 10% 20%, rgba(240, 127, 90, 0.25) 0%, transparent 40%), radial-gradient(circle at 80% 10%, rgba(47, 143, 110, 0.25) 0%, transparent 45%), linear-gradient(120deg, #fbf7f3 0%, #f4ece5 100%)",
      },
    },
  },
  plugins: [],
};

export default config;
