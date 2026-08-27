// @ts-check
import { defineConfig } from 'astro/config'
import preact from '@astrojs/preact'
import tailwind from '@astrojs/tailwind'

// Preact rather than React (SITE_PRD §1.5, §6.11). There is one island on this
// page, nothing to amortise a view-library runtime against, and an acceptance
// criterion of Lighthouse >= 95 on a page whose entire thesis is that waiting is
// the enemy. React arrived in an earlier revision as a side effect of choosing a
// shadcn component source, and was recorded as an independent decision it was
// not.
export default defineConfig({
  site: 'https://joshedwards237.github.io',
  base: '/Amanuensis',
  output: 'static',
  trailingSlash: 'ignore',
  integrations: [preact(), tailwind({ applyBaseStyles: false })],
  build: { inlineStylesheets: 'auto' },
  // No external origin may appear in the built output. §5.2 is a hard
  // constraint and §12.2 tests it with two controls: a page advertising zero
  // runtime network that fetches a stylesheet from a CDN is refuted by its own
  // devtools panel. Fonts are self-hosted; see site/public/fonts/README.md.
  vite: { build: { assetsInlineLimit: 0 } },
})
