/**
 * The voice band — SITE_PRD §6.2.
 *
 * Inline SVG from a peaks array that ships in the page bundle, so the waveform
 * renders even when the audio asset does not (§6.10). The widget's worst case is
 * degrading from *replay* to *record*, and a record still carries the argument.
 *
 * The release tick is not decoration. Its horizontal position must line up with
 * the left edge of the stage bars below, at every breakpoint — that alignment
 * *is* the claim "the clock starts when your thumb comes up", and it is why the
 * release tick sits at 100% here and the bars begin at the same inline padding.
 */

interface Props {
  /** True when these peaks are a flat stand-in rather than a real recording. */
  placeholder?: boolean
  peaks: number[]
  durationS: number
  releaseAtS: number
  playedS: number
  recording: boolean
}

export function Waveform({
  peaks,
  durationS,
  releaseAtS,
  playedS,
  recording,
  placeholder = false,
}: Props) {
  const width = 1000
  const height = 96
  const mid = height / 2
  const step = peaks.length > 1 ? width / (peaks.length - 1) : width
  const played = durationS > 0 ? Math.min(playedS / durationS, 1) : 0

  const bars = peaks.map((p, i) => {
    const x = i * step
    const h = Math.max(1, p * (height - 8))
    return { x, y: mid - h / 2, h, on: i / Math.max(peaks.length - 1, 1) <= played }
  })

  const releaseX = durationS > 0 ? (releaseAtS / durationS) * width : width

  return (
    <div class="wave">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Waveform of a ${durationS.toFixed(1)} second dictation`}
      >
        {bars.map((b, i) => (
          <rect
            key={i}
            x={b.x}
            y={b.y}
            width={Math.max(step * 0.6, 1)}
            height={b.h}
            fill={b.on ? 'var(--ink)' : 'var(--muted)'}
            opacity={b.on ? 1 : 0.45}
          />
        ))}
        <line
          x1={releaseX}
          x2={releaseX}
          y1={0}
          y2={height}
          stroke="var(--rule)"
          stroke-width="2"
        />
        {played > 0 && played < 1 && (
          <line
            x1={played * width}
            x2={played * width}
            y1={0}
            y2={height}
            stroke="var(--accent)"
            stroke-width="2"
          />
        )}
      </svg>
      {placeholder && (
        <p class="wave-placeholder">
          no recording yet — this envelope is a placeholder, not a voice
        </p>
      )}
      <div class="wave-axis">
        <span>
          <kbd>⌥</kbd> held — speaking
        </span>
        <span class={recording ? 'rec is-live' : 'rec'}>
          {recording ? '● recording' : ''}
        </span>
        <span class="release">released ▲</span>
      </div>
    </div>
  )
}
