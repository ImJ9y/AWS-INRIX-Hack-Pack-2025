/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: {
        DEFAULT: "1rem",
        lg: "2rem"
      },
      screens: {
        "2xl": "1120px"
      }
    },
    extend: {
      colors: {
        bg: "#FFFFFF",
        ink: "#111827",
        "ink-muted": "#6B7280",
        border: "#E5E7EB",
        accent: "#111827",
        success: "#16A34A",
        warn: "#F59E0B",
        danger: "#DC2626"
      },
      fontFamily: {
        sans: ["'DM Sans'", "system-ui", "-apple-system", "BlinkMacSystemFont", "'Segoe UI'", "sans-serif"]
      },
      boxShadow: {
        sm: "0 1px 2px rgba(15, 23, 42, 0.04)",
        md: "0 8px 24px rgba(15, 23, 42, 0.08)"
      },
      borderRadius: {
        xl: "1rem",
        "2xl": "1.25rem"
      },
      keyframes: {
        shimmer: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" }
        }
      },
      animation: {
        shimmer: "shimmer 1.4s ease-in-out infinite"
      }
    }
  },
  plugins: []
};
