import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        night: "#191C34",
        panel: "#22264A",
        line: "#353A66",
        paper: "#ECE9F5",
        mute: "#A7A4C9",
        dusk: "#9592CF",
        lamp: "#F2B544",
        lampdeep: "#D99A26",
        ember: "#E5675A",
        sage: "#7FC8A0",
      },
      fontFamily: {
        display: ['"Barlow Condensed"', "system-ui", "sans-serif"],
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;
