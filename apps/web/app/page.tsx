import { Github } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { AudioProofStrip, type ProofTurn } from "@/components/landing/audio-proof-strip";
import { CopyCommand } from "@/components/landing/copy-command";
import { GitHubStars, REPO } from "@/components/landing/github-stars";
import { TwoAgentDiagram } from "@/components/landing/two-agent-diagram";

import demo from "../public/demo/sample-session.json";
import published from "../public/published-metrics.json";

const SELF_HOST_COMMAND = `git clone https://github.com/${REPO}.git && cd INTERACTAI && docker compose -f compose.selfhost.yml up --build`;

interface PublishedRun {
  eval_run_id: string;
  configuration: string;
  dataset_revision: string;
  host_class: string | null;
  date: string;
  qwk: number | null;
  metrics: Record<string, unknown>;
}

interface Published {
  latency: (PublishedRun & { p50_ms: number | null; p90_ms: number | null; p95_ms: number | null; n: number | null }) | null;
  persona: PublishedRun | null;
  speech: PublishedRun | null;
  scorer: PublishedRun | null;
  human_ceiling: PublishedRun | null;
}

const metrics = published as unknown as Published;

function measured(v: unknown, unit = ""): string {
  return v === null || v === undefined ? "not yet measured" : `${typeof v === "number" ? v.toLocaleString() : String(v)}${unit}`;
}

function proofTurns(): ProofTurn[] {
  const turns = [...demo.turns].sort((a, b) => a.start_ms - b.start_ms);
  const latency = demo.latency_by_turn as Record<string, { e2e?: number }>;
  const out: ProofTurn[] = [];
  turns.forEach((t, i) => {
    const next = turns[i + 1];
    if (t.speaker !== "user" || !next || next.speaker !== "persona") return;
    out.push({
      id: t.id,
      answer: t.text,
      reply: next.text,
      startMs: t.start_ms,
      endMs: next.end_ms,
      e2eMs: latency[t.id]?.e2e ?? null,
    });
  });
  return out;
}

function Provenance({ run }: { run: PublishedRun | null }) {
  if (!run) return null;
  return (
    <p className="mt-2 font-mono text-[11px] text-[var(--text-tertiary)]">
      eval_runs {run.eval_run_id.slice(0, 8)} · rev {run.dataset_revision.slice(0, 10)} · {run.configuration} · {run.host_class ?? "host n/a"} ·{" "}
      {run.date}
    </p>
  );
}

/** Phase 6 TASK 6.6 — the public landing page. Server Component; the only client islands are
 * the audio strip, the star count and the copy button. Every number is read from
 * published-metrics.json (scripts/publish_metrics.py, from eval_runs) or the demo bundle — none
 * is typed into this file. */
export default function LandingPage() {
  const turns = proofTurns();
  const lat = metrics.latency;
  const persona = metrics.persona;
  const speech = metrics.speech;

  return (
    <main className="min-h-dvh">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
        <span className="text-sm font-medium">InteractAI</span>
        <nav className="flex items-center gap-4 text-sm text-[var(--text-secondary)]">
          <Link href="/demo" className="hover:text-[var(--text-primary)]">
            Demo
          </Link>
          <a href={`https://github.com/${REPO}`} className="hover:text-[var(--text-primary)]">
            GitHub
          </a>
          <Link href="/signin" className="hover:text-[var(--text-primary)]">
            Sign in
          </Link>
        </nav>
      </header>

      {/* 1. Hero */}
      <section className="mx-auto max-w-5xl px-6 pb-12 pt-10">
        <h1 className="max-w-3xl text-xl font-medium">Rehearse a hard interview out loud, and get a score you can check.</h1>
        <p className="mt-4 max-w-2xl text-base text-[var(--text-secondary)]">
          An AI interviewer answers you by voice, in character. A separate coach scores every answer afterwards and links
          each score to the exact words you said.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-3">
          <Link
            href="/demo"
            className="inline-flex h-11 items-center rounded-md bg-[var(--accent)] px-5 text-sm font-medium text-[var(--text-on-accent)] hover:bg-[var(--accent-hover)]"
          >
            Try a 60-second session
          </Link>
          <a
            href={`https://github.com/${REPO}`}
            className="inline-flex h-11 items-center gap-2 rounded-md border bg-[var(--bg-card)] px-4 text-sm font-medium hover:bg-[var(--bg-raised)]"
          >
            <Github size={16} aria-hidden /> View on GitHub <GitHubStars />
          </a>
        </div>
        <p className="mt-3 text-xs text-[var(--text-tertiary)]">No signup for the demo.</p>
      </section>

      {/* 2. Audio proof strip */}
      <section className="mx-auto max-w-5xl px-6 pb-16">
        <h2 className="text-md font-medium">Listen to a real exchange</h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Real interviewer replies and real measured latency. Target p95 ≤ 1400 ms; this CPU-only laptop misses it.
        </p>
        <p className="mt-1 font-mono text-[11px] text-[var(--text-tertiary)]">
          {demo.provenance.host_class} · {demo.provenance.recorded_at.slice(0, 10)} · persona {demo.provenance.persona_model} · candidate
          answers scripted + synthesized
        </p>
        <div className="mt-4">
          <AudioProofStrip src={demo.recording.url} turns={turns} />
        </div>
      </section>

      {/* 3. How it works */}
      <section className="border-y bg-[var(--bg-card)]">
        <div className="mx-auto max-w-5xl px-6 py-16">
          <h2 className="text-md font-medium">How it works</h2>
          <div className="mt-6 grid gap-6 md:grid-cols-3">
            {[
              { img: "/landing/speak.png", title: "Speak", body: "Pick a scenario and answer out loud. The interviewer follows up when you are vague and presses harder on the hard tier." },
              { img: "/landing/scores.png", title: "Get scored against a rubric", body: "Every score cites the words it is based on, checked by exact match. Too little signal shows “not enough signal”, never a guess." },
              { img: "/landing/replay.png", title: "Replay the moment", body: "Click evidence and the recording jumps to the moment you said it. Delivery metrics are measured, not judged." },
            ].map((p) => (
              <figure key={p.title} className="flex flex-col gap-3">
                <Image src={p.img} alt={`Screenshot: ${p.title}`} width={1200} height={750} className="w-full rounded-lg border" sizes="(min-width: 768px) 30vw, 100vw" />
                <figcaption>
                  <div className="text-sm font-medium">{p.title}</div>
                  <p className="mt-1 text-sm text-[var(--text-secondary)]">{p.body}</p>
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      </section>

      {/* 4. Two-agent diagram */}
      <section className="mx-auto max-w-5xl px-6 py-16">
        <h2 className="text-md font-medium">Two agents, one hard rule</h2>
        <p className="mt-1 max-w-3xl text-sm text-[var(--text-secondary)]">
          The persona sits on the latency path and must answer fast. The coach never touches that path: scoring is queued
          and can take as long as it needs.
        </p>
        <div className="mt-6 rounded-lg border bg-[var(--bg-card)] p-4">
          <TwoAgentDiagram />
        </div>
      </section>

      {/* 5. Evaluation callout */}
      <section className="border-y bg-[var(--bg-card)]">
        <div className="mx-auto grid max-w-5xl gap-8 px-6 py-16 md:grid-cols-3">
          <div>
            <h3 className="text-sm font-medium">Latency, end of speech → first audio</h3>
            <p className="mt-2 font-mono text-lg">
              p50 {measured(lat?.p50_ms, " ms")}
              <br />
              p90 {measured(lat?.p90_ms, " ms")}
              <br />
              p95 {measured(lat?.p95_ms, " ms")}
            </p>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">Target p95 ≤ 1400 ms · n = {measured(lat?.n)}</p>
            <Provenance run={lat} />
          </div>
          <div>
            <h3 className="text-sm font-medium">Scorer agreement with humans (QWK)</h3>
            <p className="mt-2 font-mono text-lg">
              model {measured(metrics.scorer?.qwk)}
              <br />
              human ceiling {measured(metrics.human_ceiling?.qwk)}
            </p>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
              Published only from a human-labelled test split, beside the agreement between two human annotators.
            </p>
            <Provenance run={metrics.scorer} />
          </div>
          <div>
            <h3 className="text-sm font-medium">Speech and persona suites</h3>
            <p className="mt-2 font-mono text-sm">
              WER {measured(speech?.metrics.wer_overall)} (technical {measured(speech?.metrics.wer_technical)})
              <br />
              ASR RTF {measured(speech?.metrics.asr_rtf)}
              <br />
              character breaks {measured(persona?.metrics.character_break_rate)}
            </p>
            <Provenance run={speech} />
            <Provenance run={persona} />
          </div>
        </div>
      </section>

      {/* 6. Self-host */}
      <section className="mx-auto max-w-5xl px-6 py-16">
        <h2 className="text-md font-medium">Run it yourself</h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          The whole stack with local models (Ollama, faster-whisper, Piper) and no external API keys.
        </p>
        <div className="mt-4">
          <CopyCommand command={SELF_HOST_COMMAND} />
        </div>
      </section>

      {/* 7. Footer */}
      <footer className="border-t">
        <div className="mx-auto flex max-w-5xl flex-col gap-2 px-6 py-8 text-xs text-[var(--text-tertiary)] sm:flex-row sm:justify-between">
          <span>InteractAI measures performance against a rubric its scenario author wrote. It does not predict hiring outcomes.</span>
          <span className="flex gap-4">
            <Link href="/demo">Demo</Link>
            <a href={`https://github.com/${REPO}`}>Source</a>
            <Link href="/signin">Sign in</Link>
          </span>
        </div>
      </footer>
    </main>
  );
}
