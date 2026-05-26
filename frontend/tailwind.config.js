/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        serif: ['"Songti SC"', '"Source Han Serif SC"', 'serif'],
      },
      colors: {
        brand: {
          50: '#f0f6ff',
          500: '#0066ff',
          600: '#0052cc',
          700: '#003d99',
        },
      },
    },
  },
  plugins: [],
};
