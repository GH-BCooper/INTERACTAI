"use client";

import { Play } from "lucide-react";
import Link from "next/link";
import { notFound, useParams } from "next/navigation";
import { useState } from "react";

import { StartSessionDialog } from "@/components/dashboard/start-session-dialog";
import { VoicePreviewButton } from "@/components/dashboard/voice-preview-button";
import { ScoreBadge } from "@/components/score/score-badge";
import { Button } from "@/components/ui/button";
import { LocalDate } from "@/components/ui/local-date";
import { capitalize, DifficultyMeter, Skeleton } from "@/components/ui/primitives";
import { usePersonas, useRubric, useScenario, useScenarioProgress } from "@/lib/api/hooks";

function DetailSkeleton() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6" aria-busy="true">
      <Skeleton className="h-3 w-32" />
      <Skeleton className="mt-2 h-7 w-64" />
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-3 lg:col-span-2">
          <Skeleton className="h-5 w-20" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-4/5" />
          <Skeleton className="mt-4 h-28 w-full rounded-lg" />
        </div>
        <Skeleton className="h-52 rounded-lg" />
      </div>
    </div>
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
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <p className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">{capitalize(scenario.family)}</p>
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
                  <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                    {capitalize(persona.archetype)} · {capitalize(persona.temperament)}
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
                    <Link
                      href={`/app/sessions/${a.session_id}`}
                      className="flex items-center justify-between rounded-lg border bg-[var(--bg-card)] px-4 py-2.5 text-sm transition-colors duration-150 hover:bg-[var(--bg-raised)]"
                    >
                      <LocalDate value={a.created_at} relative />
                      <ScoreBadge score={a.overall_score} />
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        <aside className="h-fit rounded-lg border bg-[var(--bg-card)] p-4 lg:sticky lg:top-6">
          <p className="text-sm font-medium">Ready when you are</p>
          <dl className="mt-3 flex flex-col gap-2 text-xs text-[var(--text-secondary)]">
            <div className="flex justify-between">
              <dt>Difficulty</dt>
              <dd>
                <DifficultyMeter difficulty={scenario.difficulty} />
              </dd>
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

      <StartSessionDialog open={showStart} scenario={scenario} onClose={() => setShowStart(false)} />
    </div>
  );
}
