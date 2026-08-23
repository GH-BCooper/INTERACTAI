"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
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
          <div className="mt-3 flex items-center justify-between rounded-lg border bg-[var(--bg-card)] p-3">
            <div className="flex items-center gap-2 text-sm">
              {groq.last_test_status === "success" && <CheckCircle2 size={16} className="text-[var(--score-strong)]" />}
              {groq.last_test_status === "failed" && <XCircle size={16} className="text-[var(--score-weak)]" />}
              <span>A key is saved ({groq.last_test_status.replace("_", " ")})</span>
            </div>
            <div className="flex gap-2">
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
          </div>
        ) : (
          <div className="mt-3 flex gap-2">
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="gsk_…"
              aria-label="Groq API key"
              className="flex-1 rounded-md border bg-[var(--bg-card)] px-3 py-2 text-sm"
            />
            <Button variant="primary" size="sm" onClick={() => void save()} disabled={!apiKey || saveProvider.isPending}>
              {saveProvider.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        )}

        {testResult && (
          <p className={`mt-2 text-xs ${testResult.success ? "text-[var(--score-strong)]" : "text-[var(--score-weak)]"}`}>
            {testResult.message}
          </p>
        )}
      </section>

      <section>
        <label className="flex items-center justify-between text-sm">
          <span>
            Prefer local models
            <span className="mt-0.5 block text-xs text-[var(--text-secondary)]">
              Route to the locally-hosted model where available instead of the hosted default.
            </span>
          </span>
          <input
            type="checkbox"
            checked={preferLocal}
            onChange={(e) => {
              setPreferLocal(e.target.checked);
              void updateModelsSettings.mutateAsync({ prefer_local_models: e.target.checked });
            }}
            className="shrink-0"
          />
        </label>
      </section>
    </div>
  );
}
