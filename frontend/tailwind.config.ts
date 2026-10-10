import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#0a0e14',
        surface: '#111722',
        raised: '#182030',
        line: '#263146',
        ink: '#e9eef6',
        muted: '#93a1b8',
        faint: '#64748b',
        brand: { DEFAULT: '#34d399', strong: '#10b981', soft: '#34d3991f' },
        accent: { DEFAULT: '#a78bfa', soft: '#a78bfa1f' },
        danger: { DEFAULT: '#f87171', soft: '#f871711f' },
        warn: { DEFAULT: '#fbbf24', soft: '#fbbf241f' },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      fontSize: {
        display: ['3.5rem', { lineHeight: '1.05', letterSpacing: '-0.03em', fontWeight: '700' }],
        title: ['1.75rem', { lineHeight: '1.2', letterSpacing: '-0.02em', fontWeight: '650' }],
        heading: ['1.0625rem', { lineHeight: '1.4', fontWeight: '600' }],
      },
      borderRadius: { card: '0.875rem' },
      boxShadow: {
        card: '0 1px 0 0 rgb(255 255 255 / 0.03) inset, 0 8px 24px -12px rgb(0 0 0 / 0.6)',
        glow: '0 0 0 1px rgb(52 211 153 / 0.35), 0 8px 32px -8px rgb(52 211 153 / 0.35)',
      },
      backgroundImage: {
        'brand-gradient': 'linear-gradient(135deg, #34d399 0%, #22d3ee 50%, #a78bfa 100%)',
      },
    },
  },
  plugins: [],
}

export default config
