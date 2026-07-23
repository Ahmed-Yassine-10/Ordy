import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ordy: {
          ink: "#0f1115",
          accent: "#ff5a3c",
        },
      },
    },
  },
  plugins: [],
};

export default config;
