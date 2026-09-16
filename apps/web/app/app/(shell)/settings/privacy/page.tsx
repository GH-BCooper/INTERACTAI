"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  useDeleteMe,
  useExportMyData,
  usePrivacySettings,
  useUpdatePrivacySettings,
} from "@/lib/api/hooks";
import { useAuthStore } from "@/stores/auth-store";

const RETENTION_OPTIONS = [
  { value: 0, label: "Delete immediately after scoring" },
  { value: 7, label: "7 days" },
  { value: 30, label: "30 days (default)" },
  { value: 90, label: "90 days" },
];

function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function PrivacySettingsPage() {
  const router = useRouter();
  const { data: privacy } = usePrivacySettings();
  const updatePrivacy = useUpdatePrivacySettings();
  const exportData = useExportMyData();
  const deleteMe = useDeleteMe();
  const clearAuth = useAuthStore((s) => s.clear);

  const [trainingConsent, setTrainingConsent] = useState(false);
  const [retentionDays, setRetentionDays] = useState(30);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");

  useEffect(() => {
    if (privacy) {
      setTrainingConsent(privacy.training_consent);
      setRetentionDays(privacy.audio_retention_days);
    }
  }, [privacy]);

  async function toggleTrainingConsent(next: boolean) {
    setTrainingConsent(next);
    await updatePrivacy.mutateAsync({ training_consent: next });
  }

  async function changeRetention(next: number) {
    setRetentionDays(next);
    await updatePrivacy.mutateAsync({ audio_retention_days: next });
  }

  async function doExport() {
    const data = await exportData.mutateAsync();
    downloadJson(`interactai-export-${new Date().toISOString().slice(0, 10)}.json`, data);
  }

  async function doDelete() {
    await deleteMe.mutateAsync();
    clearAuth();
    router.replace("/signin");
  }

  return (
    <div className="flex flex-col gap-8">
      <section>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Training data consent</p>
            <p className="mt-1 max-w-md text-xs text-[var(--text-secondary)]">
              When on, your future sessions may be used (in de-identified form) to improve
              scoring. This is never bundled into anything else — you can revoke it any time,
              and revoking excludes your existing turns from any future training data build.
            </p>
          </div>
          <input
            type="checkbox"
            aria-label="Training data consent"
            checked={trainingConsent}
            onChange={(e) => void toggleTrainingConsent(e.target.checked)}
            className="shrink-0"
          />
        </div>
      </section>

      <section>
        <label className="block text-xs text-[var(--text-secondary)]" htmlFor="retention">
          Audio retention
        </label>
        <select
          id="retention"
          value={retentionDays}
          onChange={(e) => void changeRetention(Number(e.target.value))}
          className="mt-1 w-full rounded-md border bg-[var(--bg-card)] px-3 py-2 text-sm"
        >
          {RETENTION_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-[var(--text-tertiary)]">
          Applies to future sessions. A background job purges recordings past this window.
        </p>
      </section>

      <section>
        <p className="text-sm font-medium">Export your data</p>
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          A JSON archive of your profile, sessions, transcripts and scores.
        </p>
        <Button variant="secondary" size="sm" className="mt-2" onClick={() => void doExport()} disabled={exportData.isPending}>
          {exportData.isPending ? "Preparing…" : "Export as JSON"}
        </Button>
      </section>

      <section className="rounded-lg border border-[var(--danger)]/40 p-4">
        <p className="text-sm font-medium text-[var(--danger)]">Delete account</p>
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          Permanently deletes your account, sessions, transcripts, scores and stored audio.
          This cannot be undone.
        </p>
        {!confirmingDelete ? (
          <Button variant="danger" size="sm" className="mt-3" onClick={() => setConfirmingDelete(true)}>
            Delete my account
          </Button>
        ) : (
          <div className="mt-3 flex flex-col gap-2">
            <label className="text-xs text-[var(--text-secondary)]" htmlFor="delete-confirm">
              Type DELETE to confirm
            </label>
            <input
              id="delete-confirm"
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText(e.target.value)}
              className="w-full rounded-md border bg-[var(--bg-card)] px-3 py-2 text-sm"
            />
            <div className="flex gap-2">
              <Button
                variant="danger"
                size="sm"
                disabled={deleteConfirmText !== "DELETE" || deleteMe.isPending}
                onClick={() => void doDelete()}
              >
                {deleteMe.isPending ? "Deleting…" : "Permanently delete"}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirmingDelete(false)}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
