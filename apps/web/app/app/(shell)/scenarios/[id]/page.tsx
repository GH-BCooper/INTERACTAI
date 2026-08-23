"use client";

import { Play, Volume2 } from "lucide-react";
import { notFound, useParams } from "next/navigation";
import { useState } from "react";

import { StartSessionDialog } from "@/components/dashboard/start-session-dialog";
import { ScoreBadge } from "@/components/score/score-badge";
import { Button } from "@/components/ui/button";
import { usePersonas, useRubric, useScenario, useScenarioProgress } from "@/lib/api/hooks";
import { fetchVoicePreviewUrl } from "@/lib/audio/voice-preview";

function DetailSkeleton() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="h-8 w-64 animate-pulse rounded bg-[var(--bg-card)]" />
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 h-96 animate-pulse rounded-lg border bg-[var(--bg-card)]" />
        <div className="h-64 animate-pulse rounded-lg border bg-[var(--bg-card)]" />
      </div>
    </div>
  );
}

function VoicePreviewButton({ personaId }: { personaId: string }) {
  const [state, setState] = useState<"idle" | "loading" | "playing" | "failed">("idle");

  async function play() {
    setState("loading");
    const url = await fetchVoicePreviewUrl(personaId);
    if (!url) {
      setState("failed");
      return;
    }
    const audio = new Audio(url);
    audio.addEventListener("ended", () => setState("idle"));
    setState("playing");
    void audio.play();
  }

  return (
    <Button variant="secondary" size="sm" onClick={() => void play()} disabled={state === "loading" || state === "playing"}>
      <Volume2 size={14} />
      {state === "loading" ? "Loading…" : state === "playing" ? "Playing…" : state === "failed" ? "Preview unavailable" : "Preview voice"}
    </Button>
  );
}

export default function ScenarioDetailPage() {
  const params = useParams<{ id: string }>();
  const scenarioId = params.id;
  const { data: scenario, isPending, error } = useScenario(scenarioId);
  const { data: personas } = usePersonas();
  const { data: rubric } = useRubric(scenario?.rubric_id);
  const { data: scenarioProgress } = useScenarioProgress();
  const [showStart, setShowStart] = useState(false);

  if (error && "status" in error && (error as { status: number }).status === 404) notFound();
  if (isPending || !scenario) return <DetailSkeleton />;

  const persona = personas?.find((p) => p.id === scenario.persona_id) ?? null;
  const progress = scenarioProgress?.[scenario.id];

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <p className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
        {scenario.family} · {scenario.difficulty}
      </p>
      <h1 className="mt-1 text-lg font-medium">{scenario.title}</h1>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <section>
            <h2 className="text-md font-medium">Brief</h2>
            <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-[var(--text-secondary)]">
              {scenario.brief}
            </p>
          </section>

          {persona && (
            <section>
              <h2 className="text-md font-medium">Your interviewer</h2>
              <div className="mt-2 flex items-start justify-between gap-4 rounded-lg border bg-[var(--bg-card)] p-4">
                <div>
                  <p className="text-sm font-medium">{persona.name}</p>
                  <p className="mt-1 text-xs capitalize text-[var(--text-tertiary)]">
                    {persona.archetype} · {persona.temperament}
                  </p>
                  <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">{persona.brief}</p>
                </div>
                <VoicePreviewButton personaId={persona.id} />
              </div>
            </section>
          )}

          {rubric && (
            <section>
              <h2 className="text-md font-medium">What you&apos;re judged on</h2>
              <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                The rubric is shown so you know what to expect — the persona won&apos;t reveal it during the
                conversation.
              </p>
              <div className="mt-3 flex flex-col gap-3">
                {rubric.criteria.map((c) => (
                  <div key={c.id} className="rounded-lg border bg-[var(--bg-card)] p-3">
                    <p className="text-sm font-medium">{c.name}</p>
                    <p className="mt-0.5 text-xs text-[var(--text-secondary)]">{c.description}</p>
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs text-[var(--text-tertiary)] hover:text-[var(--text-primary)]">
                        Anchor descriptors
                      </summary>
                      <ul className="mt-2 flex flex-col gap-1 text-xs text-[var(--text-secondary)]">
                        {["1", "2", "3", "4", "5"].map((point) => (
                          <li key={point}>
                            <span className="font-mono font-medium">{point}</span> —{" "}
                            {c.anchor_descriptors[point]}
                          </li>
                        ))}
                      </ul>
                    </details>
                  </div>
                ))}
              </div>
            </section>
          )}

          {progress && progress.recent_attempts.length > 0 && (
            <section>
              <h2 className="text-md font-medium">Previous attempts</h2>
              <ul className="mt-2 flex flex-col gap-2">
                {progress.recent_attempts.map((a) => (
                  <li key={a.session_id}>
                    <a
                      href={`/app/sessions/${a.session_id}`}
                      className="flex items-center justify-between rounded-lg border bg-[var(--bg-card)] px-4 py-2.5 text-sm hover:bg-[var(--bg-raised)]"
                    >
                      <span>{new Date(a.created_at).toLocaleDateString()}</span>
                      <ScoreBadge score={a.overall_score} />
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        <aside className="h-fit rounded-lg border bg-[var(--bg-card)] p-4">
          <p className="text-sm font-medium">Ready when you are</p>
          <dl className="mt-3 flex flex-col gap-2 text-xs text-[var(--text-secondary)]">
            <div className="flex justify-between">
              <dt>Difficulty</dt>
              <dd className="capitalize">{scenario.difficulty}</dd>
            </div>
            <div className="flex justify-between">
              <dt>Expected length</dt>
              <dd>{scenario.duration_minutes} min</dd>
            </div>
            {progress && (
              <div className="flex justify-between">
                <dt>Your best score</dt>
                <dd>
                  <ScoreBadge score={progress.best_score} />
                </dd>
              </div>
            )}
          </dl>
          <Button variant="primary" size="md" className="mt-4 w-full" onClick={() => setShowStart(true)}>
            <Play size={16} />
            Start
          </Button>
        </aside>
      </div>

      {showStart && <StartSessionDialog scenario={scenario} onClose={() => setShowStart(false)} />}
    </div>
  );
}
