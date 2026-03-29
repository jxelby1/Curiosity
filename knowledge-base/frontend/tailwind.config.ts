import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx,mdx}'
  ],
  theme: {
    extend: {
      colors: {
        ink: '#1f2622',
        paper: '#f7f2e7',
        moss: '#3f6d59',
        brass: '#9a7a42',
        steel: '#51625a'
      },
      fontFamily: {
        display: ['Canela', 'Iowan Old Style', 'Palatino Linotype', 'Book Antiqua', 'serif'],
        sans: ['Avenir Next', 'Neue Haas Grotesk Text Pro', 'IBM Plex Sans', 'Segoe UI', 'sans-serif'],
      },
      boxShadow: {
        panel: '0 24px 55px rgba(20, 26, 24, 0.11)'
      }
    }
  },
  plugins: []
};

export default config;
