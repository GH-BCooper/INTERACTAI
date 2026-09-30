"use client";

import { CheckCircle2, KeyRound, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { SaveStatus } from "@/components/settings/save-status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { LocalDate } from "@/components/ui/local-date";
import { Card, Pill } from "@/components/ui/primitives";
import { Switch } from "@/components/ui/switch";
import {
  useDeleteProvider,
  useModelsSettings,
  useProviders,
  useSaveProvider,
  useTestProvider,
  useUpdateModelsSettings,
} from "@/lib/api/hooks";

export default function ModelsSettingsPage() {
  const { data: providers } = useProviders();
  const saveProvider = useSaveProvider();
  const deleteProvider = useDeleteProvider();
  const testProvider = useTestProvider();
  const { data: modelsSettings } = useModelsSettings();
  const updateModelsSettings = useUpdateModelsSettings();

  const [apiKey, setApiKey] = useState("");
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [preferLocal, setPreferLocal] = useState(false);
  const [preferSavedAt, setPreferSavedAt] = useState<number | null>(null);

  useEffect(() => {
    if (modelsSettings) setPreferLocal(modelsSettings.prefer_local_models);
  }, [modelsSettings]);

  const groq = providers?.find((p) => p.provider === "groq") ?? null;

  async function save() {
    await saveProvider.mutateAsync({ provider: "groq", apiKey });
    setApiKey("");
    setTestResult(null);
  }

  async function test() {
    const result = await testProvider.mutateAsync("groq");
    setTestResult({ success: result.success, message: result.message });
  }

  return (
    <div className="flex flex-col gap-8">
      <section>
        <p className="text-sm font-medium">Groq API key</p>
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          Bring your own key to route persona/scoring calls through your own Groq account
          instead of the shared default.
        </p>

        {groq ? (
          <Card className="mt-3 flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-center gap-3 text-sm">
              <KeyRound size={16} aria-hidden className="shrink-0 text-[var(--text-tertiary)]" />
              <div className="min-w-0">
                {/* The key itself is never sent back to the browser — only that one exists. */}
                <p className="font-mono tracking-wider" aria-label="Saved Groq key, hidden">
                  gsk_••••••••••••
                </p>
                <p className="mt-0.5 text-xs text-[var(--text-tertiary)]">
                  {groq.last_tested_at ? (
                    <>
                      Last tested <LocalDate value={groq.last_tested_at} relative />
                    </>
                  ) : (
                    "Not tested yet"
                  )}
                </p>
              </div>
              {groq.last_test_status === "success" && (
                <Pill tone="ok">
                  <CheckCircle2 size={12} aria-hidden /> Working
                </Pill>
              )}
              {groq.last_test_status === "failed" && (
                <Pill tone="bad">
                  <XCircle size={12} aria-hidden /> Failed
                </Pill>
              )}
              {groq.last_test_status !== "success" && groq.last_test_status !== "failed" && <Pill>Untested</Pill>}
            </div>
            <div className="flex shrink-0 gap-2">
              <Button variant="secondary" size="sm" onClick={() => void test()} disabled={testProvider.isPending}>
                {testProvider.isPending ? "Testing…" : "Test connection"}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void deleteProvider.mutateAsync("groq")}
                disabled={deleteProvider.isPending}
              >
                Remove
              </Button>
            </div>
          </Card>
        ) : (
          <div className="mt-3 flex gap-2">
            <Input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="gsk_…"
              aria-label="Groq API key"
              autoComplete="off"
              className="flex-1"
            />
            <Button variant="primary" onClick={() => void save()} disabled={!apiKey || saveProvider.isPending}>
              {saveProvider.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        )}

        {testResult && (
          <p className={`mt-2 text-xs ${testResult.success ? "text-[var(--status-ok)]" : "text-[var(--status-bad)]"}`}>
            {testResult.message}
          </p>
        )}
      </section>

      <Card className="p-4">
        <Switch
          label="Prefer local models"
          description="Route to the locally-hosted model where available instead of the hosted default."
          checked={preferLocal}
          onChange={(next) => {
            setPreferLocal(next);
            updateModelsSettings.mutate(
              { prefer_local_models: next },
              {
                onSuccess: () => setPreferSavedAt(Date.now()),
                onError: () => setPreferLocal(!next),
              },
            );
          }}
        />
        <div className="mt-2 flex justify-end">
          <SaveStatus
            pending={updateModelsSettings.isPending}
            savedAt={preferSavedAt}
            error={updateModelsSettings.error ? "Couldn't save. Try again." : null}
          />
        </div>
      </Card>
    </div>
  );
}
