/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F6F3EC",
        panel: "#FFFDF8",
        ink: "#171714",
        "ink-soft": "#34342E",
        muted: "#726F65",
        line: "#E3DED2",
        "line-strong": "#CFC8B8",
        clay: "#AB4E28",
        "clay-soft": "#F1DFD2",
        moss: "#3D5C49",
        "moss-soft": "#E0E8DF",
        amber: "#A66A19",
        "amber-soft": "#F5E8CE",
        danger: "#9C3628",
        "danger-soft": "#F6DED9",
        night: "#151512",
        "night-soft": "#23231E",
      },
      fontFamily: {
        sans: ["Manrope Variable", "Manrope", "system-ui", "sans-serif"],
        display: ["Instrument Serif", "Georgia", "serif"],
      },
      borderRadius: {
        card: "18px",
      },
      boxShadow: {
        lift: "0 18px 50px -32px rgba(23, 23, 20, 0.35)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
      },
      animation: {
        "fade-up": "fade-up 420ms cubic-bezier(0.22, 1, 0.36, 1) both",
        "pulse-soft": "pulse-soft 2.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
