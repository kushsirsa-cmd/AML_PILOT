import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "sans-serif"], mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"] },
      colors: { ink: { 950: "#0a0f1f", 900: "#0f172a", 800: "#1a2238" }, brand: { 50: "#eef2ff", 100: "#e0e7ff", 500: "#635bff", 600: "#5249e6", 700: "#4338ca" } },
      boxShadow: { card: "0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.06)" },
    },
  },
  plugins: [],
};
export default config;
