"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { useMe, useUpdateProfile } from "@/lib/api/hooks";

export default function SettingsPage() {
  const { data: me } = useMe();
  const updateProfile = useUpdateProfile();
  const [resumeText, setResumeText] = useState("");
  const [targetRole, setTargetRole] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (me?.profile) {
      setResumeText(me.profile.resume_text ?? "");
      setTargetRole(me.profile.target_role ?? "");
    }
  }, [me]);

  async function save() {
    setSaved(false);
    await updateProfile.mutateAsync({
      resume_text: resumeText || null,
      clear_resume: resumeText.trim() === "",
      target_role: targetRole || null,
    });
    setSaved(true);
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <h1 className="text-lg font-medium">Settings</h1>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        This context is used to tailor practice sessions — it is never shown to the persona
        verbatim beyond what a scenario brief calls for.
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

      <label className="mt-4 block text-xs text-[var(--text-secondary)]" htmlFor="resume-text">
        Resume text
      </label>
      <textarea
        id="resume-text"
        value={resumeText}
        onChange={(e) => setResumeText(e.target.value)}
        rows={10}
        placeholder="Paste your resume as plain text."
        className="mt-1 w-full rounded-md border bg-[var(--bg-card)] px-3 py-2 text-sm"
      />

      <div className="mt-4 flex items-center gap-3">
        <Button variant="primary" onClick={save} disabled={updateProfile.isPending}>
          {updateProfile.isPending ? "Saving…" : "Save"}
        </Button>
        {saved && <span className="text-xs text-[var(--text-tertiary)]">Saved.</span>}
      </div>
    </div>
  );
}
