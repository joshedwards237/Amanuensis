/**
 * The replay widget — SITE_PRD §6. The page's centrepiece and its only rich
 * motion.
 *
 * One real dictation: the actual audio, the actual transcript the model
 * produced, the actual `LatencyBreakdown` row. Nothing here is simulated and
 * nothing is typed — every millisecond arrives from the session JSON the export
 * wrote, and CI diffs that against the database.
 *
 * Three decisions carry the whole thing, and each one is a decision *not* to do
 * the obvious:
 *
 * **No text appears during playback.** The transcript area is empty while audio
 * plays, and that emptiness is the exhibit — it is PRD §7.1 made visible. The
 * product is batch; streaming partials are a §3 non-goal. A typewriter effect
 * is the single most predictable move for a dictation product and it would be a
 * lie twice over: the product does not stream, and injection is an atomic paste.
 * The transcript lands in one frame, at every rate, including 1/20x.
 *
 * **Bars stay proportional; labels take the legibility floor.** See `dwell.ts`.
 *
 * **The widget has no broken state.** Audio 404, JavaScript off, hydration
 * failure — all three land on the complete static end state, with the 1/20x
 * replay still working because it needs no audio at all. Worst case it degrades
 * from replay to record, and a record from `history.db` is still evidence.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'preact/hooks'
import { StageBars } from './replay/StageBars'
import { Waveform } from './replay/Waveform'
import { advance, dwellComplete, initialDwell, type DwellState } from './replay/dwell'
import { createTransport, intervals as toIntervals, totalMs } from './replay/transport'
import type { Peaks, Phase, Rate, Session } from './replay/types'

interface Props {
  session: Session
  peaks: Peaks
  audioSrc: string
  headline?: { label: string; n: number; p50: number; p95: number }
}

const OPEN_BOX = '␣'

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * Render every run of whitespace the rules pass cares about as visible boxes.
 *
 * Leading runs *and* internal runs of two or more. An earlier version marked
 * only the leading run, which meant `collapse_whitespace` could fire on a
 * doubled internal space and the diff claiming to show what changed would not
 * show it — the exhibit would be quietly incomplete in exactly the direction
 * that flatters the product. The string itself is never altered; only its
 * rendering.
 */
function visibleWhitespace(text: string) {
  const parts: Array<{ ws: boolean; value: string }> = []
  const pattern = /^[ \t]+|[ \t]{2,}/g
  let last = 0
  for (const match of text.matchAll(pattern)) {
    const at = match.index ?? 0
    if (at > last) parts.push({ ws: false, value: text.slice(last, at) })
    parts.push({ ws: true, value: match[0] })
    last = at + match[0].length
  }
  if (last < text.length) parts.push({ ws: false, value: text.slice(last) })
  if (parts.length === 0) return <>{text}</>
  return (
    <>
      {parts.map((part, i) =>
        part.ws ? (
          <span
            key={i}
            class="ws"
            title={`${part.value.length} space${part.value.length > 1 ? 's' : ''}`}
          >
            {OPEN_BOX.repeat(part.value.length)}
          </span>
        ) : (
          <span key={i}>{part.value}</span>
        ),
      )}
    </>
  )
}

export default function Replay({ session, peaks, audioSrc, headline }: Props) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  // Server-render the COMPLETE end state, then step back to idle once
  // hydrated. §6.10: with JavaScript off, or the island failing to hydrate, the
  // widget must still show the whole record — waveform, transcript, labelled
  // bars. Rendering 'idle' on the server would ship a play button that does
  // nothing and an empty transcript line, which is the one degradation the
  // spec forbids: a broken state rather than a static record.
  const [phase, setPhase] = useState<Phase>('done')
  const [playedS, setPlayedS] = useState(0)
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  // Seeded high so the server-rendered end state draws every bar full; the
  // mount effect above resets it for interactive readers.
  const [elapsedMs, setElapsedMs] = useState(Number.MAX_SAFE_INTEGER)
  const [dwell, setDwell] = useState<DwellState>({ index: 99, since: 0 })
  const [audioOk, setAudioOk] = useState(true)
  const [showRaw, setShowRaw] = useState(false)
  const [rate, setRate] = useState<Rate>(1)

  useEffect(() => {
    // Runs only in the browser, so non-JS readers keep the end state above.
    setPhase('idle')
    setElapsedMs(0)
  }, [])

  const list = useMemo(() => toIntervals(session.stages), [session.stages])
  const total = useMemo(() => totalMs(list), [list])
  const restore = session.stages.find((s) => !s.in_g1)
  const landed = phase === 'done'

  // Persist-before-inject, checked rather than asserted. The page's headline is
  // an ordering claim; if a future row ever violated it the widget would be
  // illustrating something false, and a console warning in dev is cheaper than
  // discovering that from a screenshot.
  useEffect(() => {
    const persist = list.find((i) => i.stage.key === 'persist')
    const inject = list.find((i) => i.stage.key === 'inject')
    if (persist && inject && persist.endMs > inject.startMs) {
      // eslint-disable-next-line no-console
      console.warn(
        `[replay] session ${session.id} has persist completing after inject begins — ` +
          'the page headline claims the opposite. Check the export.',
      )
    }
  }, [list, session.id])

  const runGap = useCallback(
    (chosen: Rate) => {
      setPhase('release')
      setDwell(initialDwell)
      let wallStart = 0
      const transport = createTransport({
        durationMs: total,
        rate: chosen,
        onTick: (ms) => {
          const wall = performance.now()
          if (wallStart === 0) wallStart = wall
          setElapsedMs(ms)
          setDwell((prev) => advance(prev, list, ms, wall))
        },
        onDone: () => {
          setElapsedMs(total)
          setPhase('done')
          // Labels may still be catching up after the bars finish — that is the
          // dwell floor working, not a stall. Let them finish on their own.
          const settle = window.setInterval(() => {
            setDwell((prev) => {
              const next = advance(prev, list, total, performance.now())
              if (dwellComplete(next, list)) window.clearInterval(settle)
              return next
            })
          }, 60)
        },
      })
      transport.start()
      return transport
    },
    [list, total],
  )

  const play = useCallback(() => {
    const reduced = prefersReducedMotion()
    const chosen: Rate = reduced ? Infinity : 1
    setRate(chosen)
    const audio = audioRef.current
    if (!audio || !audioOk) {
      // No audio: skip straight to the gap. §6.10 — the slow replay in
      // particular must work with the asset missing entirely.
      setPlayedS(session.duration_s)
      runGap(reduced ? Infinity : 20)
      return
    }
    setPhase('capture')
    setPlayedS(0)
    setElapsedMs(0)
    setDwell(initialDwell)
    void audio.play().catch(() => {
      setAudioOk(false)
      setPlayedS(session.duration_s)
      runGap(20)
    })
  }, [audioOk, runGap, session.duration_s])

  const replaySlow = useCallback(() => {
    setRate(20)
    setElapsedMs(0)
    runGap(prefersReducedMotion() ? Infinity : 20)
  }, [runGap])

  // During capture the audio element is the authority: if playback stutters the
  // playhead stutters with it, because a waveform that runs ahead of its own
  // sound is drawing something that did not happen.
  const onTimeUpdate = useCallback(() => {
    const audio = audioRef.current
    if (audio) setPlayedS(audio.currentTime)
  }, [])

  const onEnded = useCallback(() => {
    setPlayedS(session.duration_s)
    runGap(prefersReducedMotion() ? Infinity : 1)
  }, [runGap, session.duration_s])

  const glyph =
    phase === 'capture' ? '●' : phase === 'release' ? '◐' : '○'
  const glyphLabel =
    phase === 'capture' ? 'recording' : phase === 'release' ? 'transcribing' : 'idle'

  const shown = showRaw && session.raw_transcript !== null
    ? session.raw_transcript
    : session.transcript

  return (
    <figure class="replay">
      <header class="replay-head">
        <span class="t-label">Recorded session</span>
        <span class="t-data meta">
          {session.recorded_on} · one row of history.db · {session.engine} · tier{' '}
          {session.tier}
        </span>
        <span class={`glyph${phase === 'capture' ? ' is-live' : ''}`} aria-hidden="true">
          {glyph}
        </span>
        <span class="visually-hidden">{glyphLabel}</span>
      </header>

      <div class="replay-body">
        <Waveform
          peaks={peaks.peaks}
          durationS={peaks.duration_s}
          releaseAtS={peaks.release_at_s}
          playedS={playedS}
          recording={phase === 'capture'}
          placeholder={(peaks as { placeholder?: boolean }).placeholder === true}
        />

        <div class="cursor-line" aria-live="polite">
          {landed ? (
            <span class="t-data">{visibleWhitespace(shown)}</span>
          ) : (
            <span class="caret" aria-hidden="true">
              ▍
            </span>
          )}
        </div>
        <p class="t-caption cursor-note">
          {landed
            ? 'Text lands all at once, because paste is atomic.'
            : 'Nothing appears until you release the key. This tool is batch, not streaming — the empty line is the product, not a loading state.'}
        </p>

        {landed && session.raw_transcript !== null && (
          <div class="diff">
            <div class="diff-controls" role="group" aria-label="Transcript version">
              <button
                type="button"
                class={showRaw ? '' : 'is-on'}
                onClick={() => setShowRaw(false)}
                aria-pressed={!showRaw}
              >
                processed
              </button>
              <button
                type="button"
                class={showRaw ? 'is-on' : ''}
                onClick={() => setShowRaw(true)}
                aria-pressed={showRaw}
              >
                raw
              </button>
            </div>
            <details>
              <summary>what the rules pass changed</summary>
              <div class="t-data scroll-x">
                <p class="k">raw</p>
                <p class="v">{visibleWhitespace(session.raw_transcript)}</p>
                <p class="k">processed</p>
                <p class="v">{visibleWhitespace(session.transcript)}</p>
                <p class="k">rules that fired</p>
                <p class="v">
                  {session.fired_entries.length > 0
                    ? session.fired_entries.join(', ')
                    : 'none'}
                </p>
              </div>
            </details>
          </div>
        )}

        <p class="t-label gap-label">
          {rate === 1
            ? 'the gap, at real speed'
            : 'the gap, magnified — shown at 1/20×; it played above at 1×'}
        </p>

        <StageBars
          intervals={list}
          restore={restore}
          elapsedMs={elapsedMs}
          activeIndex={dwell.index}
          g1Ms={session.g1_ms}
        />

        <table class="visually-hidden">
          <caption>Measured latency by stage for this recorded session</caption>
          <thead>
            <tr>
              <th scope="col">Stage</th>
              <th scope="col">Milliseconds</th>
              <th scope="col">Counted in the release-to-text figure</th>
            </tr>
          </thead>
          <tbody>
            {session.stages.map((s) => (
              <tr key={s.key}>
                <th scope="row">{s.label}</th>
                <td>{s.ms}</td>
                <td>{s.in_g1 ? 'yes' : 'no'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <footer class="replay-foot">
        <div class="controls">
          <button type="button" onClick={play} disabled={phase === 'capture'}>
            {phase === 'idle' ? '▶ play' : '↺ replay'}
          </button>
          <button type="button" onClick={replaySlow}>
            replay at 1/20×
          </button>
        </div>
        {!audioOk && (
          <p class="t-caption">
            Audio unavailable — the waveform, transcript and timings above are the
            session as stored.
          </p>
        )}
        <details class="receipt">
          <summary>the history.db row this came from</summary>
          <div class="t-data scroll-x">
            {Object.entries(session.row).map(([k, v]) => (
              <div key={k} class="kv">
                <span class="k">{k}</span>
                <span class="v">{v === null ? 'NULL' : String(v)}</span>
              </div>
            ))}
          </div>
        </details>
        {headline && (
          <p class="t-caption">
            This session: {session.g1_ms} ms. Across {headline.n} dictations of{' '}
            {headline.label}: p50 {headline.p50} ms, p95 {headline.p95} ms.
          </p>
        )}
      </footer>

      {audioOk && (
        <audio
          ref={audioRef}
          src={audioSrc}
          preload="metadata"
          onTimeUpdate={onTimeUpdate}
          onEnded={onEnded}
          onError={() => setAudioOk(false)}
        />
      )}
    </figure>
  )
}
