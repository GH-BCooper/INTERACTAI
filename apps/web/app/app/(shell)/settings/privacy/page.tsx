"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { SaveStatus } from "@/components/settings/save-status";
import { Button } from "@/components/ui/button";
import { FieldHint, Input, Label, Select } from "@/components/ui/field";
import { Card } from "@/components/ui/primitives";
import { Switch } from "@/components/ui/switch";
import { downloadJson } from "@/lib/download";
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
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    if (privacy) {
      setTrainingConsent(privacy.training_consent);
      setRetentionDays(privacy.audio_retention_days);
    }
  }, [privacy]);

  async function savePrivacy(body: { training_consent?: boolean; audio_retention_days?: number }) {
    try {
      await updatePrivacy.mutateAsync(body);
      setSavedAt(Date.now());
    } catch {
      // Roll the control back to the server's value; SaveStatus shows the failure.
      if (privacy) {
        setTrainingConsent(privacy.training_consent);
        setRetentionDays(privacy.audio_retention_days);
      }
    }
  }

  async function toggleTrainingConsent(next: boolean) {
    setTrainingConsent(next);
    await savePrivacy({ training_consent: next });
  }

  async function changeRetention(next: number) {
    setRetentionDays(next);
    await savePrivacy({ audio_retention_days: next });
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
      <div className="flex justify-end">
        <SaveStatus
          pending={updatePrivacy.isPending}
          savedAt={savedAt}
          error={updatePrivacy.error ? "Couldn't save that change. Try again." : null}
        />
      </div>

      <Card className="p-4">
        <Switch
          label={<span className="font-medium">Training data consent</span>}
          description="When on, your future sessions may be used (in de-identified form) to improve scoring. This is never bundled into anything else — you can revoke it any time, and revoking excludes your existing turns from any future training data build."
          checked={trainingConsent}
          onChange={(next) => void toggleTrainingConsent(next)}
        />
      </Card>

      <section>
        <Label htmlFor="retention">Audio retention</Label>
        <Select
          id="retention"
          className="mt-1"
          value={retentionDays}
          onChange={(e) => void changeRetention(Number(e.target.value))}
        >
          {RETENTION_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
        <FieldHint>
          Applies to future sessions. A background job purges recordings past this window. You can also delete a
          single recording from its report.
        </FieldHint>
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

      <section aria-labelledby="danger-zone" className="mt-4 border-t pt-8">
        <h2 id="danger-zone" className="text-xs font-medium uppercase tracking-wide text-[var(--danger)]">
          Danger zone
        </h2>
        <div className="mt-3 rounded-lg border border-[var(--danger)]/40 p-4">
        <p className="text-sm font-medium">Delete account</p>
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
            <Label htmlFor="delete-confirm">
              Type <span className="font-mono text-[var(--text-primary)]">DELETE</span> to confirm
            </Label>
            <Input
              id="delete-confirm"
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText(e.target.value)}
              autoComplete="off"
              autoFocus
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
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setConfirmingDelete(false);
                  setDeleteConfirmText("");
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}
        </div>
      </section>
    </div>
  );
}
