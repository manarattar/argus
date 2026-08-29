import type { Config } from 'tailwindcss';

/**
 * The design system is a small, deliberate set of tokens rather than Tailwind's
 * full palette. Analysts read this interface for hours; the visual language has
 * to stay quiet so that the one thing that should shout - a risk rating, a
 * failed step, an unresolved challenge - actually does.
 *
 * Colour carries meaning here and nothing else. The four risk levels are the
 * only saturated colours in the product, which is why an Elevated badge reads
 * instantly without a legend.
 */
const config: Config = {
  darkMode: 'class',
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Surfaces, defined as CSS variables so the theme switch is one class.
        canvas: 'rgb(var(--canvas) / <alpha-value>)',
        surface: 'rgb(var(--surface) / <alpha-value>)',
        raised: 'rgb(var(--raised) / <alpha-value>)',
        line: 'rgb(var(--line) / <alpha-value>)',
        'line-strong': 'rgb(var(--line-strong) / <alpha-value>)',
        ink: 'rgb(var(--ink) / <alpha-value>)',
        'ink-muted': 'rgb(var(--ink-muted) / <alpha-value>)',
        'ink-subtle': 'rgb(var(--ink-subtle) / <alpha-value>)',
        accent: 'rgb(var(--accent) / <alpha-value>)',
        'accent-soft': 'rgb(var(--accent-soft) / <alpha-value>)',

        // Risk levels. The only saturated colours in the system.
        low: 'rgb(var(--low) / <alpha-value>)',
        moderate: 'rgb(var(--moderate) / <alpha-value>)',
        elevated: 'rgb(var(--elevated) / <alpha-value>)',
        high: 'rgb(var(--high) / <alpha-value>)',
      },
      fontFamily: {
        sans: [
          'ui-sans-serif',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'Inter',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
        mono: [
          'ui-monospace',
          'SFMono-Regular',
          'Cascadia Mono',
          'Menlo',
          'Consolas',
          'monospace',
        ],
      },
      fontSize: {
        // A tight scale. Dense interfaces need fewer sizes, not more.
        '2xs': ['0.6875rem', { lineHeight: '1rem', letterSpacing: '0.01em' }],
        xs: ['0.75rem', { lineHeight: '1.125rem' }],
        sm: ['0.8125rem', { lineHeight: '1.25rem' }],
        base: ['0.875rem', { lineHeight: '1.4375rem' }],
        lg: ['1rem', { lineHeight: '1.5rem' }],
        xl: ['1.125rem', { lineHeight: '1.625rem' }],
        '2xl': ['1.375rem', { lineHeight: '1.875rem', letterSpacing: '-0.01em' }],
        '3xl': ['1.75rem', { lineHeight: '2.125rem', letterSpacing: '-0.02em' }],
        '4xl': ['2.25rem', { lineHeight: '2.5rem', letterSpacing: '-0.025em' }],
      },
      borderRadius: {
        // Restrained. Heavy rounding reads as consumer software.
        DEFAULT: '4px',
        md: '5px',
        lg: '7px',
      },
      boxShadow: {
        card: '0 1px 2px rgb(15 23 42 / 0.04), 0 1px 1px rgb(15 23 42 / 0.03)',
        pop: '0 8px 24px -6px rgb(15 23 42 / 0.16), 0 2px 6px -2px rgb(15 23 42 / 0.08)',
      },
      keyframes: {
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(3px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.6s infinite',
        'fade-up': 'fade-up 180ms ease-out',
      },
    },
  },
  plugins: [],
};

export default config;
