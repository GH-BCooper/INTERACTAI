"use client";

import { clsx } from "clsx";
import { ArrowLeft, Briefcase, Check, Code, HandCoins } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ProfileFields, type ProfileValues } from "@/components/settings/profile-fields";
import { Button, ButtonLink } from "@/components/ui/button";
import { Wordmark } from "@/components/ui/logo";
import { useCompleteOnboarding, useCreateSession, useMe, useScenarios, useUpdateProfile } from "@/lib/api/hooks";
import type { ExperienceLevel, Goal } from "@/lib/api/types";

const GOAL_CARDS: { goal: Goal; title: string; body: string; icon: typeof Briefcase }[] = [
  {
    goal: "job_interview",
    title: "A job interview",
    body: "Behavioural and situational questions — the STAR-style conversation.",
    icon: Briefcase,
  },
  {
    goal: "technical_interview",
    title: "A technical interview",
    body: "System design and engineering-judgement questions.",
    icon: Code,
  },
  {
    goal: "salary_negotiation",
    title: "A salary negotiation",
    body: "Practise holding your ground on an offer.",
    icon: HandCoins,
  },
];

const GOAL_TO_FAMILY: Record<Goal, string> = {
  job_interview: "behavioural",
  technical_interview: "technical",
  salary_negotiation: "negotiation",
};

const STEP_LABELS = ["Your goal", "About you", "First session"] as const;

/** docs/ui-audit-2026-09.md §3: a labelled rail and "Step n of 3", not three bare bars. */
function ProgressRail({ step }: { step: 1 | 2 | 3 }) {
  return (
    <div>
      <p className="text-xs text-[var(--text-tertiary)]">
        Step {step} of 3 · {STEP_LABELS[step - 1]}
      </p>
      <ol className="mt-2 grid grid-cols-3 gap-2" aria-label="Onboarding progress">
        {STEP_LABELS.map((label, i) => {
          const s = i + 1;
          return (
            <li key={label} aria-current={step === s ? "step" : undefined} className="flex flex-col gap-1.5">
              <span
                className={clsx(
                  "h-1.5 rounded-full transition-colors duration-150",
                  s <= step ? "bg-[var(--accent)]" : "bg-[var(--border)]",
                )}
              />
              <span
                className={clsx(
                  "flex items-center gap-1 text-xs",
                  s === step ? "text-[var(--text-primary)]" : "text-[var(--text-tertiary)]",
                )}
              >
                {s < step && <Check size={12} aria-hidden />}
                {label}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function GoalStep({ onChoose, pending }: { onChoose: (goal: Goal) => void; pending: boolean }) {
  return (
    <div>
      <h1 className="text-lg font-medium">What are you preparing for?</h1>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">Pick one — you can practise the others later.</p>
      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {GOAL_CARDS.map(({ goal, title, body, icon: Icon }) => (
          <button
            key={goal}
            type="button"
            disabled={pending}
            onClick={() => onChoose(goal)}
            className="flex flex-col items-start gap-2 rounded-lg border bg-[var(--bg-card)] p-4 text-left transition-colors hover:bg-[var(--bg-raised)] disabled:opacity-50"
          >
            <Icon size={20} className="text-[var(--accent)]" />
            <span className="text-sm font-medium">{title}</span>
            <span className="text-xs text-[var(--text-secondary)]">{body}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function ProfileStep({
  onContinue,
  onBack,
  pending,
}: {
  onContinue: (fields: { target_role: string; experience_level: ExperienceLevel; resume_text: string }) => void;
  onBack: () => void;
  pending: boolean;
}) {
  const [values, setValues] = useState<ProfileValues>({
    goal: "",
    targetRole: "",
    experienceLevel: "early_career",
    resumeText: "",
  });

  return (
    <div>
      <h1 className="text-lg font-medium">Tell us a little about you</h1>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        Used to tailor practice sessions — never shown to the persona verbatim.
      </p>

      <div className="mt-6">
        <ProfileFields values={values} onChange={setValues} showGoal={false} allowUnset={false} resumeRows={6} />
      </div>

      <div className="mt-6 flex items-center justify-between">
        <Button variant="ghost" onClick={onBack} disabled={pending}>
          <ArrowLeft size={14} aria-hidden /> Back
        </Button>
        <Button
          variant="primary"
          disabled={pending}
          onClick={() =>
            onContinue({
              target_role: values.targetRole,
              experience_level: (values.experienceLevel || "early_career") as ExperienceLevel,
              resume_text: values.resumeText,
            })
          }
        >
          {pending ? "Saving…" : "Continue"}
        </Button>
      </div>
    </div>
  );
}

function LaunchingStep() {
  return (
    <div className="flex flex-col items-center gap-3 py-12 text-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--accent)] border-t-transparent" />
      <p className="text-sm text-[var(--text-secondary)]">Setting up your first session…</p>
    </div>
  );
}

export default function OnboardingPage() {
  const router = useRouter();
  const { data: me, isPending: mePending } = useMe();
  const updateProfile = useUpdateProfile();
  const createSession = useCreateSession();
  const completeOnboarding = useCompleteOnboarding();
  const [launching, setLaunching] = useState(false);
  // "Back" from step 2 re-opens the goal choice locally; picking a goal again saves it and moves on.
  const [editingGoal, setEditingGoal] = useState(false);

  const profile = me?.profile ?? null;
  const serverStep: 1 | 2 | 3 = !profile?.goal ? 1 : !profile.experience_level ? 2 : 3;
  const step: 1 | 2 | 3 = editingGoal && serverStep === 2 ? 1 : serverStep;

  const { data: goalScenarios } = useScenarios(
    profile?.goal ? { family: GOAL_TO_FAMILY[profile.goal], difficulty: "gentle" } : undefined,
  );
  // Fallback if the goal's family has no "gentle" tier seeded — a real scenario beats a stuck
  // spinner (CLAUDE.md §10 is about fabricating numbers, not about degrading gracefully to a
  // real, different scenario).
  const { data: anyScenarios } = useScenarios();
  const [launchFailed, setLaunchFailed] = useState(false);

  useEffect(() => {
    if (me?.user.onboarded_at) router.replace("/app");
  }, [me, router]);

  useEffect(() => {
    if (step !== 3 || launching || launchFailed) return;
    if (goalScenarios === undefined || anyScenarios === undefined) return; // still loading
    const scenario = goalScenarios[0] ?? anyScenarios[0];
    if (!scenario) {
      setLaunchFailed(true);
      return;
    }
    setLaunching(true);
    void (async () => {
      try {
        const session = await createSession.mutateAsync({
          scenario_id: scenario.id,
          difficulty: "gentle",
          target_minutes: 5,
        });
        await completeOnboarding.mutateAsync();
        router.replace(`/app/practice/${session.id}?onboarding=1`);
      } catch {
        setLaunching(false);
        setLaunchFailed(true);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, goalScenarios, anyScenarios, launching, launchFailed]);

  if (mePending || !me || me.user.onboarded_at) {
    return <div className="flex min-h-dvh items-center justify-center" />;
  }

  return (
    <div className="mx-auto flex min-h-dvh max-w-lg flex-col justify-center px-6 py-12">
      <Wordmark className="mb-10 text-sm" />
      <ProgressRail step={step} />
      {/* Keyed by step so each step slides in (400ms panel motion token). */}
      <div key={step} className="mt-8 animate-panel-in">
        {step === 1 && (
          <GoalStep
            pending={updateProfile.isPending}
            onChoose={(goal) => updateProfile.mutate({ goal }, { onSuccess: () => setEditingGoal(false) })}
          />
        )}
        {step === 2 && (
          <ProfileStep
            onBack={() => setEditingGoal(true)}
            pending={updateProfile.isPending}
            onContinue={({ target_role, experience_level, resume_text }) =>
              updateProfile.mutate({
                target_role: target_role || null,
                experience_level,
                resume_text: resume_text || null,
              })
            }
          />
        )}
        {step === 3 && !launchFailed && <LaunchingStep />}
        {step === 3 && launchFailed && (
          <div className="text-center">
            <p className="text-sm text-[var(--text-secondary)]">
              We couldn&apos;t start your first session automatically.
            </p>
            <ButtonLink href="/app/scenarios" variant="primary" size="sm" className="mt-3">
              Browse scenarios instead
            </ButtonLink>
          </div>
        )}
      </div>
    </div>
  );
}
