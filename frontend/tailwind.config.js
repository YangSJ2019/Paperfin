/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Jellyfin-ish dark palette tuned for paper posters.
        ink: {
          900: "#0b0f17",
          800: "#111827",
          700: "#1f2937",
          600: "#374151",
        },
        accent: {
          DEFAULT: "#7c3aed",
          soft: "#a78bfa",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
