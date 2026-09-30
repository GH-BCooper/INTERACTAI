"use client";

import { Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { ProfileFields, type ProfileValues } from "@/components/settings/profile-fields";
import { SaveStatus } from "@/components/settings/save-status";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useMe, useUpdateProfile } from "@/lib/api/hooks";

const EMPTY: ProfileValues = { goal: "", targetRole: "", experienceLevel: "", resumeText: "" };

export default function ProfileSettingsPage() {
  const { data: me } = useMe();
  const updateProfile = useUpdateProfile();
  const [values, setValues] = useState<ProfileValues>(EMPTY);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    if (me?.profile) {
      setValues({
        goal: me.profile.goal ?? "",
        targetRole: me.profile.target_role ?? "",
        experienceLevel: me.profile.experience_level ?? "",
        resumeText: me.profile.resume_text ?? "",
      });
    }
  }, [me]);

  async function save() {
    try {
      await updateProfile.mutateAsync({
        resume_text: values.resumeText || null,
        clear_resume: values.resumeText.trim() === "",
        target_role: values.targetRole || null,
        goal: values.goal || null,
        experience_level: values.experienceLevel || null,
      });
      setSavedAt(Date.now());
    } catch {
      // SaveStatus shows it.
    }
  }

  async function deleteResume() {
    setValues((v) => ({ ...v, resumeText: "" }));
    try {
      await updateProfile.mutateAsync({ clear_resume: true });
      setSavedAt(Date.now());
    } catch {
      // SaveStatus shows it.
    }
  }

  const error = updateProfile.error
    ? updateProfile.error instanceof ApiError
      ? updateProfile.error.message
      : "Couldn't save. Try again."
    : null;

  return (
    <div>
      <p className="mb-6 text-sm text-[var(--text-secondary)]">
        This context is used to tailor practice sessions — it is never shown to the persona verbatim beyond what a
        scenario brief calls for.
      </p>

      <ProfileFields
        values={values}
        onChange={setValues}
        resumeRows={10}
        resumeAction={
          values.resumeText && (
            <button
              type="button"
              onClick={() => void deleteResume()}
              className="flex items-center gap-1 text-xs text-[var(--danger)] hover:text-[var(--danger-hover)]"
            >
              <Trash2 size={12} aria-hidden /> Delete resume
            </button>
          )
        }
      />

      <div className="mt-6 flex items-center gap-3">
        <Button variant="primary" onClick={() => void save()} disabled={updateProfile.isPending}>
          Save changes
        </Button>
        <SaveStatus pending={updateProfile.isPending} savedAt={savedAt} error={error} />
      </div>
    </div>
  );
}
