"use client";

import { Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { useMe, useUpdateProfile } from "@/lib/api/hooks";
import type { ExperienceLevel, Goal } from "@/lib/api/types";

const GOALS: { value: Goal; label: string }[] = [
  { value: "job_interview", label: "Job interview" },
  { value: "technical_interview", label: "Technical interview" },
  { value: "salary_negotiation", label: "Salary negotiation" },
];

const EXPERIENCE_LEVELS: { value: ExperienceLevel; label: string }[] = [
  { value: "student", label: "Student" },
  { value: "early_career", label: "Early career" },
  { value: "mid_level", label: "Mid-level" },
  { value: "senior", label: "Senior" },
  { value: "staff_plus", label: "Staff+" },
];

export default function ProfileSettingsPage() {
  const { data: me } = useMe();
  const updateProfile = useUpdateProfile();
  const [resumeText, setResumeText] = useState("");
  const [targetRole, setTargetRole] = useState("");
  const [goal, setGoal] = useState<Goal | "">("");
  const [experienceLevel, setExperienceLevel] = useState<ExperienceLevel | "">("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (me?.profile) {
      setResumeText(me.profile.resume_text ?? "");
      setTargetRole(me.profile.target_role ?? "");
      setGoal(me.profile.goal ?? "");
      setExperienceLevel(me.profile.experience_level ?? "");
    }
  }, [me]);

  async function save() {
    setSaved(false);
    await updateProfile.mutateAsync({
      resume_text: resumeText || null,
      clear_resume: resumeText.trim() === "",
      target_role: targetRole || null,
      goal: goal || null,
      experience_level: experienceLevel || null,
    });
    setSaved(true);
  }

  async function deleteResume() {
    setResumeText("");
    await updateProfile.mutateAsync({ clear_resume: true });
    setSaved(true);
  }

  return (
    <div>
      <p className="text-sm text-[var(--text-secondary)]">
        This context is used to tailor practice sessions — it is never shown to the persona
        verbatim beyond what a scenario brief calls for.
      </p>

      <label className="mt-6 block text-xs text-[var(--text-secondary)]" htmlFor="goal-select">
        What are you preparing for?
      </label>
      <select
        id="goal-select"
        value={goal}
        onChange={(e) => setGoal(e.target.value as Goal)}
        className="mt-1 w-full rounded-md border bg-[var(--bg-card)] px-3 py-2 text-sm"
      >
        <option value="">Not set</option>
        {GOALS.map((g) => (
          <option key={g.value} value={g.value}>
            {g.label}
          </option>
        ))}
      </select>

      <label className="mt-4 block text-xs text-[var(--text-secondary)]" htmlFor="target-role">
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
        <option value="">Not set</option>
        {EXPERIENCE_LEVELS.map((l) => (
          <option key={l.value} value={l.value}>
            {l.label}
          </option>
        ))}
      </select>

      <div className="mt-4 flex items-center justify-between">
        <label className="block text-xs text-[var(--text-secondary)]" htmlFor="resume-text">
          Resume text
        </label>
        {resumeText && (
          <button
            type="button"
            onClick={() => void deleteResume()}
            className="flex items-center gap-1 text-xs text-[var(--danger)] hover:text-[var(--danger-hover)]"
          >
            <Trash2 size={12} /> Delete resume
          </button>
        )}
      </div>
      <textarea
        id="resume-text"
        value={resumeText}
        onChange={(e) => setResumeText(e.target.value)}
        rows={10}
        placeholder="Paste your resume as plain text."
        className="mt-1 w-full rounded-md border bg-[var(--bg-card)] px-3 py-2 text-sm"
      />

      <div className="mt-4 flex items-center gap-3">
        <Button variant="primary" onClick={() => void save()} disabled={updateProfile.isPending}>
          {updateProfile.isPending ? "Saving…" : "Save"}
        </Button>
        {saved && <span className="text-xs text-[var(--text-tertiary)]">Saved.</span>}
      </div>
    </div>
  );
}
