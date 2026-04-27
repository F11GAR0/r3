/** @type {import("tailwindcss").Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f0f7ff",
          100: "#e0f0ff",
          500: "#2563eb",
          600: "#1d4ed8",
          800: "#1e3a5f",
        },
      },
    },
  },
  plugins: [],
};
