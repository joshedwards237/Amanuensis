/**
 * The label dwell — SITE_PRD §6.4's legibility floor.
 *
 * The problem, stated plainly, because an earlier revision of the spec did not
 * notice it: the 1/20x replay exists because ~230 ms is below the threshold at
 * which a viewer perceives sequence. But the magnification does not recurse.
 * At 1/20x a 223 ms gap becomes 4.46 s, and `guard`, `postprocess` and
 * `persist` are all under 1.5 ms in `history.db` — so a 1 ms stage becomes
 * 20 ms of wall clock, one frame at 60 Hz. **The stages the magnification
 * exists to reveal are exactly the ones it still fails to reveal.**
 *
 * The obvious fixes are both dishonest. A minimum bar *width* misrepresents
 * magnitude, on a page whose entire argument is that its measurements are not
 * massaged. A logarithmic axis does the same thing more politely, and would
 * make "persist completes before inject begins" unreadable as a duration
 * comparison.
 *
 * So: **bar widths stay strictly proportional at every rate; the labels take
 * the floor instead.** As each stage completes, its name and value hold at full
 * contrast for at least `DWELL_MS` of wall clock before the next stage's label
 * takes over. Sequence becomes legible without any bar lying about its
 * duration. Labels may still be advancing after the bars have finished — that
 * is correct, and it is why the caption reports the real total separately.
 *
 * A stage whose bar is sub-pixel is drawn as a minimum-width tick with a dotted
 * continuation, so that "too small to draw" is visibly distinct from "zero" —
 * which matters, because `postprocess` was genuinely zero for the whole of
 * Phases 1 and 2 and is genuinely tiny now, and those are different facts.
 */

import type { Interval } from './transport'

/**
 * Minimum wall-clock ms a completed stage's label holds the foreground.
 *
 * A UI constant, not a measurement — grouped here, away from anything derived
 * from a session row, so the no-literals rule stays checkable by inspection.
 * 250 ms is about the floor at which a reader can register a short label
 * changing without it reading as a flicker.
 */
export const DWELL_MS = 250

export interface DwellState {
  /** Index into the interval list whose label currently holds, or -1. */
  index: number
  /** Wall-clock ms at which it took the foreground. */
  since: number
}

export const initialDwell: DwellState = { index: -1, since: 0 }

/**
 * Advance the highlighted label at most one step per dwell window.
 *
 * Deliberately advances one stage at a time rather than jumping to whichever
 * stage has most recently completed. Jumping would skip the sub-millisecond
 * stages entirely at 1/20x — three of them can complete inside a single dwell
 * window — which is the failure this whole module exists to prevent.
 */
export function advance(
  state: DwellState,
  intervals: Interval[],
  elapsedMs: number,
  wallMs: number,
): DwellState {
  let completed = -1
  for (let i = 0; i < intervals.length; i += 1) {
    if (elapsedMs >= (intervals[i] as Interval).endMs) completed = i
  }
  if (completed <= state.index) return state
  if (state.index >= 0 && wallMs - state.since < DWELL_MS) return state
  return { index: state.index + 1, since: wallMs }
}

/** True once every label has had its dwell — the labels, not the bars, are done. */
export function dwellComplete(state: DwellState, intervals: Interval[]): boolean {
  return state.index >= intervals.length - 1
}

/**
 * Bar width as a percentage of the widest stage.
 *
 * Proportional without exception. `minTickPct` is applied only to a bar that
 * would otherwise round to zero pixels, and the component pairs it with a
 * dotted continuation and the real value, so the tick reads as "smaller than
 * this page can draw" rather than as a measurement.
 */
export function widthPct(ms: number, maxMs: number, minTickPct = 0.6): number {
  if (maxMs <= 0) return 0
  const pct = (ms / maxMs) * 100
  if (ms > 0 && pct < minTickPct) return minTickPct
  return pct
}

/** A bar the page had to draw wider than its measurement, so it can say so. */
export function isBelowFloor(ms: number, maxMs: number, minTickPct = 0.6): boolean {
  if (maxMs <= 0 || ms <= 0) return false
  return (ms / maxMs) * 100 < minTickPct
}
