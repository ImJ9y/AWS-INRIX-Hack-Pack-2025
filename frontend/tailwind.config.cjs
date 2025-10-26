/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#2563eb",
          muted: "#dbeafe"
        }
      },
      boxShadow: {
        soft: "0 10px 40px rgba(15, 23, 42, 0.1)"
      }
    }
  },
  plugins: []
};
