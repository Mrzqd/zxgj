/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#15120d',
        sand: '#f4ecdc',
        clay: '#b8663b',
        moss: '#4d6a4b',
        linen: '#fffaf0',
      },
      boxShadow: {
        card: '0 20px 60px rgba(72, 50, 32, 0.16)',
      },
      fontFamily: {
        display: ['"Noto Serif SC"', 'serif'],
        body: ['"Noto Sans SC"', 'sans-serif'],
      },
    },
  },
  plugins: [],
};

