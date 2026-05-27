/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg:      '#0c0c0e',
        surf:    '#131316',
        border:  '#1e1e24',
        accent:  '#e8a020',
        accent2: '#3d9eff',
        txt:     '#b8b8c8',
        muted:   '#484858',
        good:    '#27ae60',
        bad:     '#c0392b',
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'Consolas', 'monospace'],
        syne: ['Syne', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
