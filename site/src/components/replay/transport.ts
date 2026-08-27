/**
 * The replay's clock. SITE_PRD §6.11.
 *
 * This is the part of the widget most likely to be got wrong, so the shape is
 * stated up front: **one clock abstraction over two sources, with rate as a
 * parameter.**
 *
 * Two sources, because the two phases are measured by different things. During
 * capture the authority is the audio element — if playback stutters, the
 * playhead must stutter with it, or the waveform stops meaning anything. After
 * release there is no audio at all: the gap between the key coming up and the
 * text landing is silent by definition. So the release phase runs on
 * `requestAnimationFrame`, and — decisively — the 1/20x replay must run with no
 * audio present whatsoever, because §6.10 requires it to keep working when the
 * audio asset 404s. A transport welded to `HTMLAudioElement` cannot satisfy
 * that.
 *
 * Rate as a parameter rather than three implementations, because §6.3's 1x
 * fill, §6.4's 1/20x fill and §6.8's reduced-motion "discrete steps at their
 * completion times" are one function at three rates — including infinity. Three
 * Strategy objects that differ only by a divisor would be three places for the
 * ordering claim to drift.
 *
 * Durations are data. Every millisecond here arrives from the session JSON;
 * none is written down. That is not tidiness — a CSS keyframe cannot express a
 * duration the export computed, and a hardcoded one would be exactly the class
 * of number the page exists to refuse.
 */

import type { Rate, Stage } from './types'

/** A stage plus where it sits on the cumulative timeline, in real ms. */
export interface Interval {
  stage: Stage
  /** Real ms from release to this stage starting. */
  startMs: number
  /** Real ms from release to this stage completing. */
  endMs: number
}

/**
 * Lay the g1 stages end to end.
 *
 * The page's headline claim — that the transcript is on disk before it is on
 * screen — is a claim about *ordering*, not about relative widths. Cumulative
 * offsets make it expressible: `persist.endMs <= inject.startMs` is the
 * sentence, checkable. A bare list of proportional widths renders the same
 * static picture and cannot state it.
 */
export function intervals(stages: Stage[]): Interval[] {
  let cursor = 0
  const out: Interval[] = []
  for (const stage of stages) {
    if (!stage.in_g1) continue
    const startMs = cursor
    cursor += stage.ms
    out.push({ stage, startMs, endMs: cursor })
  }
  return out
}

/** Total real elapsed ms across the g1 stages. */
export function totalMs(list: Interval[]): number {
  return list.length === 0 ? 0 : (list[list.length - 1] as Interval).endMs
}

/**
 * Fraction of a stage's bar that should be filled at a given real-elapsed time.
 *
 * Linear, and deliberately so: this represents elapsed time, and easing it
 * would misrepresent the measurement. A stage that has not started reads 0, a
 * finished one reads 1, and a zero-duration stage reads 1 the instant its start
 * is reached rather than dividing by zero.
 */
export function fillOf(interval: Interval, elapsedMs: number): number {
  const span = interval.endMs - interval.startMs
  if (elapsedMs <= interval.startMs) return 0
  if (span <= 0 || elapsedMs >= interval.endMs) return 1
  return (elapsedMs - interval.startMs) / span
}

export interface TransportOptions {
  /** Real duration to traverse, in ms. */
  durationMs: number
  /** 1 = real time. 20 = 1/20x. Infinity = land on the end state at once. */
  rate: Rate
  /** Called with real-elapsed ms, every frame. */
  onTick: (elapsedMs: number) => void
  onDone: () => void
  /** Injectable for tests; defaults to rAF-backed wall clock. */
  now?: () => number
}

export interface Transport {
  start: () => void
  stop: () => void
}

/**
 * Drive `onTick` from 0 to `durationMs` in real-ms terms, slowed by `rate`.
 *
 * `onTick` always receives **real** elapsed milliseconds, never wall-clock ones.
 * The rate divides how fast wall-clock advances the real clock, so every
 * consumer reasons in the units the database recorded and nothing downstream
 * has to know the replay was slowed. That is what keeps §6.4's guarantee
 * honest: at 1/20x the bars are still drawn against real durations, so the
 * widths remain strictly proportional and only the wall-clock time taken to
 * paint them changes.
 */
export function createTransport(options: TransportOptions): Transport {
  const { durationMs, rate, onTick, onDone } = options
  const now = options.now ?? (() => performance.now())
  let frame = 0
  let startedAt = 0
  let running = false

  const step = (): void => {
    if (!running) return
    const wall = now() - startedAt
    const elapsed = wall / rate
    if (elapsed >= durationMs) {
      onTick(durationMs)
      running = false
      onDone()
      return
    }
    onTick(elapsed)
    frame = requestAnimationFrame(step)
  }

  return {
    start(): void {
      if (running) return
      // Infinity is reduced motion: there is no interpolation to show, so the
      // end state is the only honest frame. Not a shortcut — an animation a
      // viewer asked not to see is not information they should have to wait for.
      if (rate === Infinity) {
        onTick(durationMs)
        onDone()
        return
      }
      running = true
      startedAt = now()
      frame = requestAnimationFrame(step)
    },
    stop(): void {
      running = false
      if (frame) cancelAnimationFrame(frame)
    },
  }
}
