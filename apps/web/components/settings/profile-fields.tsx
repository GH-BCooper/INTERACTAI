"use client";

import { Lock } from "lucide-react";
import type { ReactNode } from "react";

import { FieldHint, Input, Label, Select, Textarea } from "@/components/ui/field";
import type { ExperienceLevel, Goal } from "@/lib/api/types";

export const GOALS: { value: Goal; label: string }[] = [
  { value: "job_interview", label: "Job interview" },
  { value: "technical_interview", label: "Technical interview" },
  { value: "salary_negotiation", label: "Salary negotiation" },
];

export const EXPERIENCE_LEVELS: { value: ExperienceLevel; label: string }[] = [
  { value: "student", label: "Student" },
  { value: "early_career", label: "Early career" },
  { value: "mid_level", label: "Mid-level" },
  { value: "senior", label: "Senior" },
  { value: "staff_plus", label: "Staff+" },
];

/** Soft guidance, not a server limit: long enough for a full CV, short enough to stay useful
 * as persona context. The counter turns to a status colour past it; nothing is truncated. */
export const RESUME_SOFT_LIMIT = 8000;

export interface ProfileValues {
  goal: Goal | "";
  targetRole: string;
  experienceLevel: ExperienceLevel | "";
  resumeText: string;
}

/** docs/ui-audit-2026-09.md §11: the same profile fields in onboarding and Settings › Profile, so
 * the two can never drift apart. `showGoal` is off in onboarding (the goal is step 1 there). */
export function ProfileFields({
  values,
  onChange,
  showGoal = true,
  allowUnset = true,
  resumeRows = 8,
  resumeAction,
}: {
  values: ProfileValues;
  onChange: (next: ProfileValues) => void;
  showGoal?: boolean;
  allowUnset?: boolean;
  resumeRows?: number;
  resumeAction?: ReactNode;
}) {
  const set = <K extends keyof ProfileValues>(key: K, value: ProfileValues[K]) => onChange({ ...values, [key]: value });
  const length = values.resumeText.length;

  return (
    <div className="flex flex-col gap-4">
      {showGoal && (
        <div>
          <Label htmlFor="goal-select">What are you preparing for?</Label>
          <Select id="goal-select" className="mt-1" value={values.goal} onChange={(e) => set("goal", e.target.value as Goal | "")}>
            {allowUnset && <option value="">Not set</option>}
            {GOALS.map((g) => (
              <option key={g.value} value={g.value}>
                {g.label}
              </option>
            ))}
          </Select>
        </div>
      )}

      <div>
        <Label htmlFor="target-role">Target role</Label>
        <Input
          id="target-role"
          className="mt-1"
          value={values.targetRole}
          onChange={(e) => set("targetRole", e.target.value)}
          placeholder="e.g. Senior backend engineer"
          autoComplete="organization-title"
        />
      </div>

      <div>
        <Label htmlFor="experience-level">Experience level</Label>
        <Select
          id="experience-level"
          className="mt-1"
          value={values.experienceLevel}
          onChange={(e) => set("experienceLevel", e.target.value as ExperienceLevel | "")}
        >
          {allowUnset && <option value="">Not set</option>}
          {EXPERIENCE_LEVELS.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </Select>
      </div>

      <div>
        <div className="flex items-center justify-between">
          <Label htmlFor="resume-text">Resume (optional)</Label>
          {resumeAction}
        </div>
        <Textarea
          id="resume-text"
          className="mt-1"
          value={values.resumeText}
          onChange={(e) => set("resumeText", e.target.value)}
          rows={resumeRows}
          placeholder="Paste your resume as plain text."
          aria-describedby="resume-privacy resume-count"
        />
        <div className="mt-1 flex items-start justify-between gap-4">
          <FieldHint className="mt-0 flex items-start gap-1.5">
            <Lock size={12} aria-hidden className="mt-0.5 shrink-0" />
            <span id="resume-privacy">
              Private to your account. Used only to tailor questions, never read out verbatim, and scrubbed of personal
              details before anyone reviews a transcript. Delete it any time.
            </span>
          </FieldHint>
          <span
            id="resume-count"
            className={`shrink-0 font-mono text-xs ${length > RESUME_SOFT_LIMIT ? "text-[var(--status-bad)]" : "text-[var(--text-tertiary)]"}`}
          >
            {length.toLocaleString()} / {RESUME_SOFT_LIMIT.toLocaleString()}
          </span>
        </div>
      </div>
    </div>
  );
}
