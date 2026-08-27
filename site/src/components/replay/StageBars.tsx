/**
 * The measurement band — SITE_PRD §6.2, §6.4, §6.5.
 *
 * Bars are `--ink`, deliberately not accent: they are the record, not the
 * event. The accent belongs to what is live or being measured, and a bar that
 * has already been drawn is neither.
 *
 * `postprocess` is rendered like any other stage. An earlier revision of the
 * spec gave it a zero-width bar labelled "not built — Phase 3", which was true
 * of a tree one commit stale: post-processing shipped 2026-08-08 and costs
 * p50 0.43 ms. The stage is now real, tiny, and named — which is a better
 * exhibit than an empty track ever was.
 */

import type { Interval } from './transport'
import { fillOf } from './transport'
import { isBelowFloor, widthPct } from './dwell'
import type { Stage } from './types'

interface Props {
  intervals: Interval[]
  restore: Stage | undefined
  elapsedMs: number
  activeIndex: number
  g1Ms: number
  onJump?: (key: string) => void
}

function format(ms: number): string {
  if (ms === 0) return '0 ms'
  if (ms < 1) return `${ms.toFixed(2)} ms`
  if (ms < 10) return `${ms.toFixed(1)} ms`
  return `${Math.round(ms)} ms`
}

export function StageBars({
  intervals,
  restore,
  elapsedMs,
  activeIndex,
  g1Ms,
  onJump,
}: Props) {
  const maxMs = Math.max(...intervals.map((i) => i.stage.ms), restore?.ms ?? 0, 1)

  return (
    <div class="bars">
      {intervals.map((interval, index) => {
        const { stage } = interval
        const fill = fillOf(interval, elapsedMs)
        const below = isBelowFloor(stage.ms, maxMs)
        const active = index === activeIndex
        const revealed = elapsedMs >= interval.endMs
        return (
          <button
            key={stage.key}
            type="button"
            class={`row${active ? ' is-active' : ''}`}
            onClick={() => onJump?.(stage.key)}
            aria-label={`${stage.label}, ${format(stage.ms)}. Jump to this stage.`}
          >
            <span class="name">{stage.label}</span>
            <span class="track">
              <span
                class="fill"
                style={{
                  width: `${widthPct(stage.ms, maxMs) * fill}%`,
                }}
              />
              {below && <span class="dotted" aria-hidden="true" />}
            </span>
            <span class={`value${revealed ? ' is-shown' : ''}`}>
              {format(stage.ms)}
              {below && <span class="floor" title="smaller than this page can draw to scale"> ·</span>}
            </span>
          </button>
        )
      })}

      <div class="g1">
        <span class="name" />
        <span class="bracket">release → text fully present</span>
        <span class="value is-shown">{format(g1Ms)}</span>
      </div>

      {restore && (
        <div class="row is-outside">
          <span class="name">{restore.label}</span>
          <span class="track">
            <span
              class="hatch"
              style={{ width: `${widthPct(restore.ms, maxMs)}%` }}
            />
          </span>
          <span class="value is-shown">{format(restore.ms)}</span>
        </div>
      )}
      <p class="outside-note">
        Putting your clipboard back happens after your text is already on screen,
        so it sits outside the number.
      </p>
    </div>
  )
}
