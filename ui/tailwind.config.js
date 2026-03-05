/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        page: '#fdfcf8',
        ink: '#2c2c2c',
        'coherence-stable': '#4a90d9',
        'coherence-regen': '#d4a017',
      },
      fontFamily: {
        ernie: ['Ernie', 'Caveat', 'cursive'],
        journal: ['Georgia', 'serif'],
      },
      opacity: {
        ghost: '0.05',
        faint: '0.15',
        pencil: '0.20',
        active: '0.60',
      },
    },
  },
  plugins: [],
};
