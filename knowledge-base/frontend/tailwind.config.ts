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
        ink: '#101321',
        paper: '#f4f7ee',
        moss: '#7ca982',
        brass: '#c7a04f',
        steel: '#455a64'
      },
      boxShadow: {
        panel: '0 10px 30px rgba(16, 19, 33, 0.12)'
      }
    }
  },
  plugins: []
};

export default config;
