export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#e6fbf7',
          100: '#c2f5ec',
          200: '#9deedb',
          300: '#6fe5c8',
          400: '#33d6b5',
          500: '#00c2a8',
          600: '#00a892',
          700: '#008a79',
          800: '#0a6e61',
          900: '#0b5b50',
          950: '#05352f',
        },
        'brand-bg': '#080C14',
        'brand-surface': '#0F1520',
        'brand-surface-2': '#131A28',
        'brand-border': '#1A2035',
        'brand-border-strong': '#2B3654',
        'brand-text': '#F4F6FA',
        'brand-text-muted': '#8B95A8',
        'brand-accent': '#F0A500',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
}