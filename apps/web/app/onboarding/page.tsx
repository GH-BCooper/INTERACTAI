"use client";

import { Briefcase, Code, HandCoins } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
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

const EXPERIENCE_LEVELS: { value: ExperienceLevel; label: string }[] = [
  { value: "student", label: "Student" },
  { value: "early_career", label: "Early career" },
  { value: "mid_level", label: "Mid-level" },
  { value: "senior", label: "Senior" },
  { value: "staff_plus", label: "Staff+" },
];

const GOAL_TO_FAMILY: Record<Goal, string> = {
  job_interview: "behavioural",
  technical_interview: "technical",
  salary_negotiation: "negotiation",
};

function ProgressRail({ step }: { step: 1 | 2 | 3 }) {
  return (
    <ol className="flex items-center gap-2" aria-label="Onboarding progress">
      {[1, 2, 3].map((s) => (
        <li
          key={s}
          aria-current={step === s ? "step" : undefined}
          className={`h-1.5 w-10 rounded-full ${s <= step ? "bg-[var(--accent)]" : "bg-[var(--border)]"}`}
        />
      ))}
    </ol>
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
  pending,
}: {
  onContinue: (fields: { target_role: string; experience_level: ExperienceLevel; resume_text: string }) => void;
  pending: boolean;
}) {
  const [targetRole, setTargetRole] = useState("");
  const [experienceLevel, setExperienceLevel] = useState<ExperienceLevel>("early_career");
  const [resumeText, setResumeText] = useState("");

  return (
    <div>
      <h1 className="text-lg font-medium">Tell us a little about you</h1>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        Used to tailor practice sessions — never shown to the persona verbatim.
      </p>

      <label className="mt-6 block text-xs text-[var(--text-secondary)]" htmlFor="target-role">
        Target role
      </label>
      <input
        id="target-role"
        value={targetRole}
        onChange={(e) => setTargetRole(e.target.value)}
        placeholder="e.g. Senior backend engineer"
        className="mt-1 w-full rounded-md border bg-[var(--bg-card)] px-3 py-2 text-sm"
      />

      <label className="mt-4 block text-xs text-[var(--text-secondary)]" htmlFor="experience-level">
        Experience level
      </label>
      <select
        id="experience-level"
        value={experienceLevel}
        onChange={(e) => setExperienceLevel(e.target.value as ExperienceLevel)}
        className="mt-1 w-full rounded-md border bg-[var(--bg-card)] px-3 py-2 text-sm"
      >
        {EXPERIENCE_LEVELS.map((l) => (
          <option key={l.value} value={l.value}>
            {l.label}
          </option>
        ))}
      </select>

      <label className="mt-4 block text-xs text-[var(--text-secondary)]" htmlFor="resume-text">
        Resume (optional)
      </label>
      <textarea
        id="resume-text"
        value={resumeText}
        onChange={(e) => setResumeText(e.target.value)}
        rows={6}
        placeholder="Paste your resume as plain text."
        className="mt-1 w-full rounded-md border bg-[var(--bg-card)] px-3 py-2 text-sm"
      />
      <p className="mt-1 text-xs text-[var(--text-tertiary)]">
        Optional. If you paste it, it&apos;s used to tailor your practice questions and is never shared outside your
        account — you can delete it any time in Settings.
      </p>

      <Button
        variant="primary"
        size="md"
        className="mt-5"
        disabled={pending}
        onClick={() => onContinue({ target_role: targetRole, experience_level: experienceLevel, resume_text: resumeText })}
      >
        {pending ? "Saving…" : "Continue"}
      </Button>
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

  const profile = me?.profile ?? null;
  const step: 1 | 2 | 3 = !profile?.goal ? 1 : !profile.experience_level ? 2 : 3;

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
      <ProgressRail step={step} />
      <div className="mt-6">
        {step === 1 && (
          <GoalStep
            pending={updateProfile.isPending}
            onChoose={(goal) => updateProfile.mutate({ goal })}
          />
        )}
        {step === 2 && (
          <ProfileStep
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
            <a href="/app/scenarios" className="mt-3 inline-block">
              <Button variant="primary" size="sm">
                Browse scenarios instead
              </Button>
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
