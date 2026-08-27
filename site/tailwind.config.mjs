/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,ts,tsx}'],
  // The palette lives in tokens.css as custom properties, not here. Tailwind
  // cannot express the three-way theme structure §12.4 criterion 17 requires
  // (bare :root, prefers-color-scheme guarded against an explicit light choice,
  // and [data-theme] winning over both) without duplicating every colour into a
  // dark: variant — which is the "defined only inside a media query" failure the
  // criterion exists to prevent. Tailwind is here for layout utilities; colour
  // comes from var().
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)',
        panel: 'var(--panel)',
        ink: 'var(--ink)',
        muted: 'var(--muted)',
        rule: 'var(--rule)',
        link: 'var(--link)',
        accent: 'var(--accent)',
      },
      fontFamily: {
        sans: 'var(--font-sans)',
        mono: 'var(--font-mono)',
      },
      maxWidth: {
        measure: 'var(--measure)',
        'measure-wide': 'var(--measure-wide)',
      },
    },
  },
  plugins: [],
}
