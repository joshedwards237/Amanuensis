/**
 * The shape the export writes and the widget reads (SITE_PRD §6.1, §7.1).
 *
 * Kept in one file so the contract has a single definition. The export is the
 * producer; if these drift, `scripts/verify_site_claims.py` catches it as a
 * golden diff rather than the page silently rendering `undefined`.
 */

export interface Stage {
  /** Column stem in `history.db` — `vad`, `transcribe`, `guard`, … */
  key: string
  /**
   * What the page calls it. Differs from `key` in exactly one place: the trim
   * stage's column is `vad_ms`. The schema is named after the mechanism and the
   * page after the effect, and since the widget shows the literal row, the
   * mismatch is carried rather than quietly renamed.
   */
  label: string
  ms: number
  /**
   * Inside `g1_ms` — hotkey release to text fully present. `capture` is not,
   * because the time the user spent speaking is theirs. `restore` is not,
   * because it happens after the text is already on screen.
   */
  in_g1: boolean
}

export interface Session {
  id: string
  recorded_on: string
  duration_s: number
  engine: string
  tier: string
  transcript: string
  /** What the model emitted, before the rules pass. Null on pre-Phase-3 rows. */
  raw_transcript: string | null
  /** Rules that actually fired, e.g. `collapse_whitespace`. */
  fired_entries: string[]
  stages: Stage[]
  g1_ms: number
  restore_ms: number
  guard: {
    outcome: string | null
    coverage: number | null
    retained_seconds: number | null
  }
  /** The literal allowlisted row. The receipt (§6.6). */
  row: Record<string, unknown>
}

export interface Peaks {
  /** Normalised 0..1 amplitude envelope. */
  peaks: number[]
  release_at_s: number
  duration_s: number
}

export interface Band {
  label: string
  n: number
  publishable: boolean
  p50_ms?: number
  p95_ms?: number
}

export interface Claims {
  rows_total: number
  rows_excluded: number
  headline_band: string
  targets: { p50_ms: number; p95_ms: number }
  bands: Record<string, Band>
  postprocess: { n: number; p50_ms: number | null; p95_ms: number | null }
}

/** Playback rate. `Infinity` is reduced motion: every step lands at once. */
export type Rate = 1 | 20 | typeof Infinity

export type Phase = 'idle' | 'capture' | 'release' | 'done'
