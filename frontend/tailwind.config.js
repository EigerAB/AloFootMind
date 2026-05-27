/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        pitch: {
          green: '#1a472a',
          light: '#2d6a4f',
        }
      }
    },
  },
  plugins: [],
}
