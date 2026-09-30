import { ArrowRight, Github, Hourglass } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { AudioProofStrip, type ProofTurn } from "@/components/landing/audio-proof-strip";
import { CopyCommand } from "@/components/landing/copy-command";
import { GitHubStars } from "@/components/landing/github-stars";
import { TwoAgentDiagram } from "@/components/landing/two-agent-diagram";
import { ButtonAnchor, ButtonLink } from "@/components/ui/button";
import { Wordmark } from "@/components/ui/logo";
import { REPO } from "@/lib/repo";

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
  return v === null || v === undefined ? "not yet measured" : `${typeof v === "number" ? v.toLocaleString("en-US") : String(v)}${unit}`;
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
    <p className="mt-2 font-mono text-xs text-[var(--text-tertiary)]">
      eval_runs {run.eval_run_id.slice(0, 8)} · rev {run.dataset_revision.slice(0, 10)} · {run.configuration} · {run.host_class ?? "host n/a"} ·{" "}
      {run.date}
    </p>
  );
}

const FAMILIES = [
  { name: "Technical", body: "System design and engineering-judgement questions, with follow-ups when an answer stays vague." },
  { name: "Behavioural", body: "STAR-style questions about real situations: conflict, ownership, failure, influence." },
  { name: "Negotiation", body: "Hold your ground on an offer against a counterpart who pushes back." },
  { name: "Viva", body: "Defend your own work to an examiner who probes the weakest part of it." },
];

const AUDIENCE = [
  { title: "Candidates", body: "Rehearse the answer out loud before the real interview, then see exactly which words cost you." },
  { title: "Career changers", body: "Practise telling an unfamiliar story until it sounds like yours, at a difficulty you choose." },
  { title: "Students", body: "Prepare for a viva or a first technical interview without needing someone free to play the examiner." },
];

const FAQ = [
  {
    q: "Does the score predict whether I get the job?",
    a: "No. It measures your answer against a rubric the scenario's author wrote, and says so on every report. It makes no claim about hiring outcomes.",
  },
  {
    q: "Where do the scores come from?",
    a: "A separate scoring model, never the interviewer. Every score must cite the exact words it is based on, checked by exact match; when there is too little signal you see “not enough signal”, never a guess.",
  },
  {
    q: "What happens to my audio?",
    a: "Your recording is kept for 30 days by default so you can replay it, and you can delete it from any report or shorten retention in Settings. The interviewer's voice is never stored; it is regenerated from the transcript.",
  },
  {
    q: "Can I run it myself?",
    a: "Yes. The whole stack runs locally with Docker, local models and no external API keys. See “Run it yourself” below.",
  },
];

/** Phase 6 TASK 6.6 — the public landing page. Server Component; the only client islands are
 * the audio strip, the star count and the copy button. Every number is read from
 * published-metrics.json (scripts/publish_metrics.py, from eval_runs) or the demo bundle — none
 * is typed into this file. */
export default function LandingPage() {
  const turns = proofTurns();
  const lat = metrics.latency;
  const persona = metrics.persona;
  const speech = metrics.speech;

  // docs/ui-audit-2026-09.md §2: runs that don't exist yet collapse into one honest "pending"
  // card, instead of "not yet measured" repeated down the page. Never a placeholder number.
  const pending = [
    !lat && "Latency",
    !(metrics.scorer && metrics.human_ceiling) && "Scorer agreement with humans (QWK)",
    !(speech || persona) && "Speech and persona suites",
  ].filter((x): x is string => Boolean(x));

  return (
    <main className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-transparent bg-[var(--bg-page)]/80 backdrop-blur-md supports-[backdrop-filter]:bg-[var(--bg-page)]/70">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4 sm:px-6">
          <Link href="/" aria-label="InteractAI home">
            <Wordmark />
          </Link>
          <nav className="flex items-center gap-4 text-sm text-[var(--text-secondary)]">
            <Link href="/demo" className="hover:text-[var(--text-primary)]">
              Demo
            </Link>
            <a href={`https://github.com/${REPO}`} className="hidden hover:text-[var(--text-primary)] sm:inline">
              GitHub
            </a>
            <ButtonLink href="/signin" size="sm" variant="secondary">
              Sign in
            </ButtonLink>
          </nav>
        </div>
      </header>

      {/* 1. Hero — with the product itself above the fold: a real recorded exchange. */}
      <section className="mx-auto grid max-w-5xl items-center gap-10 px-4 pb-16 pt-10 sm:px-6 md:grid-cols-[1.1fr_1fr] md:pt-16">
        <div className="animate-rise-in">
          <h1 className="text-xl font-medium">Rehearse a hard interview out loud, and get a score you can check.</h1>
          <p className="mt-4 max-w-xl text-base text-[var(--text-secondary)]">
            An AI interviewer answers you by voice, in character. A separate coach scores every answer afterwards and links
            each score to the exact words you said.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <ButtonLink href="/demo" variant="primary" size="lg">
              Try a 60-second session <ArrowRight size={16} aria-hidden />
            </ButtonLink>
            <ButtonAnchor href={`https://github.com/${REPO}`} variant="secondary" size="lg">
              <Github size={16} aria-hidden /> View on GitHub <GitHubStars />
            </ButtonAnchor>
          </div>
          <p className="mt-3 text-xs text-[var(--text-tertiary)]">No signup for the demo.</p>
        </div>

        <div className="animate-rise-in rounded-xl border bg-[var(--bg-card)] p-4 [animation-delay:80ms]">
          <p className="text-sm font-medium">Listen to a real exchange</p>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            Real interviewer replies and real measured latency. Target p95 ≤ 1400 ms; this CPU-only laptop misses it.
          </p>
          <div className="mt-3">
            <AudioProofStrip src={demo.recording.url} turns={turns} />
          </div>
          <p className="mt-3 font-mono text-xs text-[var(--text-tertiary)]">
            {demo.provenance.host_class} · {demo.provenance.recorded_at.slice(0, 10)} · persona {demo.provenance.persona_model} ·
            candidate answers scripted + synthesized
          </p>
        </div>
      </section>

      {/* 2. How it works */}
      <section className="border-y bg-[var(--bg-card)]">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6">
          <h2 className="text-md font-medium">How it works</h2>
          <div className="mt-6 grid gap-6 md:grid-cols-3">
            {[
              { img: "/landing/speak.png", title: "Speak", body: "Pick a scenario and answer out loud. The interviewer follows up when you are vague and presses harder on the hard tier." },
              { img: "/landing/scores.png", title: "Get scored against a rubric", body: "Every score cites the words it is based on, checked by exact match. Too little signal shows “not enough signal”, never a guess." },
              { img: "/landing/replay.png", title: "Replay the moment", body: "Click evidence and the recording jumps to the moment you said it. Delivery metrics are measured, not judged." },
            ].map((p, i) => (
              <figure key={p.title} className="flex flex-col gap-3">
                <Image src={p.img} alt={`Screenshot: ${p.title}`} width={1200} height={750} className="w-full rounded-lg border" sizes="(min-width: 768px) 30vw, 100vw" />
                <figcaption>
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <span className="flex h-5 w-5 items-center justify-center rounded-full border font-mono text-xs text-[var(--text-secondary)]">{i + 1}</span>
                    {p.title}
                  </div>
                  <p className="mt-1 text-sm text-[var(--text-secondary)]">{p.body}</p>
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      </section>

      {/* 3. Scenario showcase */}
      <section className="mx-auto max-w-5xl px-4 py-16 sm:px-6">
        <h2 className="text-md font-medium">Four kinds of hard conversation</h2>
        <p className="mt-1 max-w-3xl text-sm text-[var(--text-secondary)]">
          Each scenario has an interviewer persona, a rubric with written anchors for every score, and three difficulty tiers.
        </p>
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {FAMILIES.map((f) => (
            <div key={f.name} className="rounded-lg border bg-[var(--bg-card)] p-4">
              <p className="text-sm font-medium">{f.name}</p>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 4. Two-agent diagram */}
      <section className="border-y bg-[var(--bg-card)]">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6">
          <h2 className="text-md font-medium">Two agents, one hard rule</h2>
          <p className="mt-1 max-w-3xl text-sm text-[var(--text-secondary)]">
            The persona sits on the latency path and must answer fast. The coach never touches that path: scoring is queued and can
            take as long as it needs.
          </p>
          <div className="mt-6 rounded-lg border bg-[var(--bg-page)] p-4">
            <TwoAgentDiagram />
          </div>
        </div>
      </section>

      {/* 5. Evaluation callout */}
      <section className="mx-auto max-w-5xl px-4 py-16 sm:px-6">
        <h2 className="text-md font-medium">Measured, with provenance</h2>
        <p className="mt-1 max-w-3xl text-sm text-[var(--text-secondary)]">
          Each number below is an eval_runs row: its dataset revision, configuration and host are printed under it.
        </p>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {lat && (
            <div className="rounded-lg border bg-[var(--bg-card)] p-5">
              <h3 className="text-sm font-medium">Latency, end of speech → first audio</h3>
              <p className="mt-2 font-mono text-lg">
                p50 {measured(lat.p50_ms, " ms")}
                <br />
                p90 {measured(lat.p90_ms, " ms")}
                <br />
                p95 {measured(lat.p95_ms, " ms")}
              </p>
              <p className="mt-1 text-xs text-[var(--text-secondary)]">Target p95 ≤ 1400 ms · n = {measured(lat.n)}</p>
              <Provenance run={lat} />
            </div>
          )}
          {metrics.scorer && metrics.human_ceiling && (
            <div className="rounded-lg border bg-[var(--bg-card)] p-5">
              <h3 className="text-sm font-medium">Scorer agreement with humans (QWK)</h3>
              <p className="mt-2 font-mono text-lg">
                model {measured(metrics.scorer.qwk)}
                <br />
                human ceiling {measured(metrics.human_ceiling.qwk)}
              </p>
              <p className="mt-1 text-xs text-[var(--text-secondary)]">
                Published only from a human-labelled test split, beside the agreement between two human annotators.
              </p>
              <Provenance run={metrics.scorer} />
            </div>
          )}
          {(speech || persona) && (
            <div className="rounded-lg border bg-[var(--bg-card)] p-5">
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
          )}
          {pending.length > 0 && (
            <div className="rounded-lg border border-dashed p-5">
              <h3 className="flex items-center gap-2 text-sm font-medium">
                <Hourglass size={14} aria-hidden className="text-[var(--text-tertiary)]" /> Evaluation runs pending
              </h3>
              <ul className="mt-2 flex flex-col gap-1 text-sm text-[var(--text-secondary)]">
                {pending.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                Shown here once a run exists. Nothing is estimated in the meantime.
              </p>
            </div>
          )}
        </div>
      </section>

      {/* 6. Who it's for */}
      <section className="border-y bg-[var(--bg-card)]">
        <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6">
          <h2 className="text-md font-medium">Who it&apos;s for</h2>
          <div className="mt-6 grid gap-6 md:grid-cols-3">
            {AUDIENCE.map((a) => (
              <div key={a.title}>
                <p className="text-sm font-medium">{a.title}</p>
                <p className="mt-1 text-sm text-[var(--text-secondary)]">{a.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 7. FAQ */}
      <section className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
        <h2 className="text-md font-medium">Questions</h2>
        <div className="mt-4 divide-y rounded-lg border">
          {FAQ.map((f) => (
            <details key={f.q} className="group px-4 py-3 [&_summary::-webkit-details-marker]:hidden">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-medium">
                {f.q}
                <ArrowRight size={14} aria-hidden className="shrink-0 text-[var(--text-tertiary)] transition-transform duration-150 group-open:rotate-90" />
              </summary>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">{f.a}</p>
            </details>
          ))}
        </div>
      </section>

      {/* 8. Self-host */}
      <section className="mx-auto max-w-5xl px-4 pb-16 sm:px-6">
        <h2 className="text-md font-medium">Run it yourself</h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          The whole stack with local models (Ollama, faster-whisper, Piper) and no external API keys.
        </p>
        <div className="mt-4">
          <CopyCommand command={SELF_HOST_COMMAND} />
        </div>
      </section>

      {/* 9. Footer */}
      <footer className="border-t">
        <div className="mx-auto flex max-w-5xl flex-col gap-4 px-4 py-8 text-xs text-[var(--text-tertiary)] sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div className="flex flex-col gap-2">
            <Wordmark size={16} className="text-sm text-[var(--text-secondary)]" />
            <span className="max-w-md">
              InteractAI measures performance against a rubric its scenario author wrote. It does not predict hiring outcomes.
            </span>
          </div>
          <nav aria-label="Footer" className="flex flex-wrap gap-4">
            <Link href="/demo" className="hover:text-[var(--text-primary)]">
              Demo
            </Link>
            <a href={`https://github.com/${REPO}`} className="hover:text-[var(--text-primary)]">
              Source
            </a>
            <Link href="/privacy" className="hover:text-[var(--text-primary)]">
              Privacy
            </Link>
            <Link href="/terms" className="hover:text-[var(--text-primary)]">
              Terms
            </Link>
            <Link href="/signin" className="hover:text-[var(--text-primary)]">
              Sign in
            </Link>
          </nav>
        </div>
      </footer>
    </main>
  );
}
