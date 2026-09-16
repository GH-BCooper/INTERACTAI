/** Phase 6 TASK 6.6 — "an actual diagram, not a bullet list". The one architectural idea: the
 * persona is on the latency path, the coach is off it, and the only thing between them is a
 * queue. Pure SVG, theme tokens only. */
export function TwoAgentDiagram() {
  return (
    <svg
      viewBox="0 0 760 330"
      className="h-auto w-full"
      role="img"
      aria-labelledby="two-agent-title two-agent-desc"
    >
      <title id="two-agent-title">Two-agent architecture</title>
      <desc id="two-agent-desc">
        Browser audio goes to the realtime service, which runs endpointing, speech recognition, the persona model and
        text-to-speech inside a 1400 millisecond budget and streams the reply back. Each finished turn is written to
        Postgres and a job is queued; the coach worker scores it later, off the latency path, and writes scores and the
        report.
      </desc>
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" className="fill-[var(--text-secondary)]" />
        </marker>
      </defs>

      {/* latency path band */}
      <rect x="150" y="18" width="470" height="140" rx="12" className="fill-[var(--bg-raised)] stroke-[var(--accent)]" strokeDasharray="6 4" />
      <text x="166" y="40" className="fill-[var(--accent)] text-[12px] font-medium">LATENCY PATH · p95 budget 1400 ms</text>

      {/* browser */}
      <rect x="12" y="62" width="112" height="56" rx="8" className="fill-[var(--bg-card)] stroke-[var(--border)]" />
      <text x="68" y="86" textAnchor="middle" className="fill-[var(--text-primary)] text-[13px] font-medium">Browser</text>
      <text x="68" y="104" textAnchor="middle" className="fill-[var(--text-tertiary)] text-[11px]">mic · speaker</text>

      {/* pipeline stages */}
      {[
        { x: 170, label: "Endpoint", sub: "VAD cascade" },
        { x: 282, label: "ASR", sub: "faster-whisper" },
        { x: 394, label: "Persona", sub: "LLM, streamed" },
        { x: 506, label: "TTS", sub: "Piper, chunked" },
      ].map((s) => (
        <g key={s.label}>
          <rect x={s.x} y="62" width="96" height="56" rx="8" className="fill-[var(--bg-card)] stroke-[var(--border)]" />
          <text x={s.x + 48} y="86" textAnchor="middle" className="fill-[var(--text-primary)] text-[13px] font-medium">
            {s.label}
          </text>
          <text x={s.x + 48} y="104" textAnchor="middle" className="fill-[var(--text-tertiary)] text-[11px]">
            {s.sub}
          </text>
        </g>
      ))}
      <line x1="124" y1="80" x2="168" y2="80" className="stroke-[var(--text-secondary)]" markerEnd="url(#arrow)" />
      <line x1="266" y1="90" x2="280" y2="90" className="stroke-[var(--text-secondary)]" markerEnd="url(#arrow)" />
      <line x1="378" y1="90" x2="392" y2="90" className="stroke-[var(--text-secondary)]" markerEnd="url(#arrow)" />
      <line x1="490" y1="90" x2="504" y2="90" className="stroke-[var(--text-secondary)]" markerEnd="url(#arrow)" />
      <path d="M554,118 C554,146 90,146 68,120" fill="none" className="stroke-[var(--text-secondary)]" markerEnd="url(#arrow)" />
      <text x="310" y="150" textAnchor="middle" className="fill-[var(--text-secondary)] text-[11px]">spoken reply, first chunk streamed</text>
      <text x="146" y="74" textAnchor="middle" className="fill-[var(--text-tertiary)] text-[10px]">20 ms PCM</text>

      {/* handoff */}
      <line x1="442" y1="158" x2="442" y2="204" className="stroke-[var(--text-secondary)]" markerEnd="url(#arrow)" />
      <text x="452" y="186" className="fill-[var(--text-secondary)] text-[11px]">turn written · job queued (fire-and-forget)</text>

      <rect x="300" y="206" width="160" height="44" rx="8" className="fill-[var(--bg-card)] stroke-[var(--border)]" />
      <text x="380" y="233" textAnchor="middle" className="fill-[var(--text-primary)] text-[12px] font-medium">Postgres + Redis queue</text>

      {/* off path band */}
      <rect x="150" y="262" width="470" height="60" rx="12" className="fill-none stroke-[var(--border)]" />
      <text x="166" y="284" className="fill-[var(--text-tertiary)] text-[12px] font-medium">OFF THE LATENCY PATH · slowness is invisible</text>
      <rect x="480" y="270" width="128" height="44" rx="8" className="fill-[var(--bg-card)] stroke-[var(--border)]" />
      <text x="544" y="290" textAnchor="middle" className="fill-[var(--text-primary)] text-[13px] font-medium">Coach</text>
      <text x="544" y="305" textAnchor="middle" className="fill-[var(--text-tertiary)] text-[10px]">scorer · evidence · narrator</text>
      <line x1="460" y1="236" x2="500" y2="268" className="stroke-[var(--text-secondary)]" markerEnd="url(#arrow)" />
      <text x="166" y="306" className="fill-[var(--text-tertiary)] text-[11px]">scores + evidence spans → report with synced replay</text>
    </svg>
  );
}
