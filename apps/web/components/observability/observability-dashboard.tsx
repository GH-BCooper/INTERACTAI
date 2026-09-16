"use client";

import { clsx } from "clsx";
import { useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "@/lib/api/client";
import {
  useAdminRecording,
  useCostPanel,
  useLatencyHeader,
  useModelCalls,
  useObservedTurns,
  useStageBreakdown,
  useWaterfall,
} from "@/lib/api/hooks";
import { adminObservability, type LatencyFilter, type ModelCallFilter } from "@/lib/api/resources";
import type { ModelCallOut, StageRow } from "@/lib/api/types";
import { PersonaAudioCache } from "@/lib/report/persona-audio-cache";

import { LatencyChart } from "./latency-chart";

// Fixed pipeline order (TASK 6.1b) — the backend returns stages in this order too.
const STAGE_SHADES = [
  "bg-[var(--accent)]",
  "bg-[var(--text-secondary)]",
  "bg-[var(--accent-hover)]",
  "bg-[var(--danger)]",
  "bg-[var(--text-tertiary)]",
  "bg-[var(--focus-ring)]",
  "bg-[var(--border)]",
];

function ms(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${Math.round(v).toLocaleString()} ms`;
}

function cents(v: number | null | undefined): string {
  if (v === null || v === undefined) return "not yet measured";
  return `$${(v / 100).toFixed(v < 100 ? 4 : 2)}`;
}

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border bg-[var(--bg-card)] p-5">
      <h2 className="text-md font-medium">{title}</h2>
      {subtitle && <p className="mt-1 text-xs text-[var(--text-tertiary)]">{subtitle}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Stat({ label, value, emphasis }: { label: string; value: string; emphasis?: boolean }) {
  return (
    <div>
      <div className="text-xs text-[var(--text-tertiary)]">{label}</div>
      <div className={clsx("font-mono", emphasis ? "text-xl" : "text-lg")}>{value}</div>
    </div>
  );
}

function StageStack({ rows, metric }: { rows: StageRow[]; metric: "p50" | "p95" }) {
  const total = rows.reduce((s, r) => s + (r[metric] ?? 0), 0);
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-[var(--text-secondary)]">
        <span>{metric === "p50" ? "Median" : "p95"} per stage</span>
        <span className="font-mono">Σ {ms(total)} (not an e2e percentile)</span>
      </div>
      <div className="flex h-8 w-full overflow-hidden rounded-md">
        {rows.map((r, i) =>
          r[metric] ? (
            <div
              key={r.stage}
              className={clsx(STAGE_SHADES[i % STAGE_SHADES.length], "h-full")}
              style={{ width: `${((r[metric] ?? 0) / total) * 100}%` }}
              title={`${r.stage}: ${ms(r[metric])}`}
            />
          ) : null,
        )}
      </div>
    </div>
  );
}

function ModelCallDetail({ call }: { call: ModelCallOut }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-md bg-[var(--bg-raised)] p-3 text-xs sm:grid-cols-4">
      {(
        [
          ["role", call.role],
          ["model", call.model],
          ["prompt", call.prompt_version ?? "—"],
          ["tokens", `${call.tokens_in} → ${call.tokens_out}`],
          ["TTFT", ms(call.ttft_ms)],
          ["total", ms(call.total_latency_ms)],
          ["cost", cents(call.cost_cents)],
          ["cache", call.cached ? "hit" : "miss"],
        ] as const
      ).map(([k, v]) => (
        <div key={k}>
          <dt className="text-[var(--text-tertiary)]">{k}</dt>
          <dd className="truncate font-mono">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function Waterfall() {
  const { data: turns } = useObservedTurns();
  const [turnId, setTurnId] = useState<string | null>(null);
  const [openStage, setOpenStage] = useState<string | null>(null);
  const { data: wf } = useWaterfall(turnId);
  const { data: recording } = useAdminRecording(wf?.recording_available ? wf.session_id : null);
  const userAudioRef = useRef<HTMLAudioElement>(null);
  const [personaUrl, setPersonaUrl] = useState<string | null>(null);
  const [personaState, setPersonaState] = useState<"idle" | "loading" | "failed">("idle");

  const cache = useMemo(
    () => (wf ? new PersonaAudioCache(wf.session_id, undefined, adminObservability.replayToken) : null),
    [wf],
  );
  useEffect(() => () => cache?.dispose(), [cache]);
  useEffect(() => {
    setPersonaUrl(null);
    setPersonaState("idle");
    setOpenStage(null);
  }, [turnId]);

  useEffect(() => {
    const first = turns?.[0];
    if (!turnId && first) setTurnId(first.turn_id);
  }, [turns, turnId]);

  const maxMs = Math.max(1, ...(wf?.stages.map((s) => s.duration_ms ?? 0) ?? [1]), wf?.e2e_ms ?? 0);

  function playUserUtterance() {
    const el = userAudioRef.current;
    if (!el || wf?.user_start_ms == null || wf.user_end_ms == null) return;
    el.currentTime = wf.user_start_ms / 1000;
    const stopAt = wf.user_end_ms / 1000;
    const onTime = () => {
      if (el.currentTime >= stopAt) {
        el.pause();
        el.removeEventListener("timeupdate", onTime);
      }
    };
    el.addEventListener("timeupdate", onTime);
    void el.play();
  }

  async function loadPersona() {
    if (!cache || !wf?.persona_text || !wf.persona_voice_id || !wf.persona_turn_id) return;
    setPersonaState("loading");
    const url = await cache.getAudioUrl(wf.persona_turn_id, wf.persona_text, wf.persona_voice_id);
    setPersonaUrl(url);
    setPersonaState(url ? "idle" : "failed");
  }

  return (
    <div className="flex flex-col gap-4">
      <label className="flex flex-col gap-1 text-xs text-[var(--text-secondary)] sm:flex-row sm:items-center sm:gap-3">
        Turn (slowest of the 50 most recent first)
        <select
          className="h-8 rounded-md border bg-[var(--bg-raised)] px-2 font-mono text-xs text-[var(--text-primary)]"
          value={turnId ?? ""}
          onChange={(e) => setTurnId(e.target.value)}
        >
          {(turns ?? []).map((t) => (
            <option key={t.turn_id} value={t.turn_id}>
              {ms(t.e2e_ms)} · {new Date(t.created_at).toLocaleString()} · {t.turn_id.slice(0, 8)}
            </option>
          ))}
        </select>
      </label>

      {turns && turns.length === 0 && <p className="text-sm text-[var(--text-tertiary)]">No turns with an e2e measurement yet.</p>}

      {wf && (
        <>
          <div className="flex flex-col gap-1">
            {wf.stages.map((s) => (
              <div key={s.stage}>
                <button
                  type="button"
                  onClick={() => setOpenStage(openStage === s.stage ? null : s.stage)}
                  className="grid w-full grid-cols-[9rem_1fr_5.5rem] items-center gap-2 rounded px-1 py-1 text-left text-xs hover:bg-[var(--bg-raised)]"
                  aria-expanded={openStage === s.stage}
                >
                  <span className="font-mono text-[var(--text-secondary)]">{s.stage}</span>
                  <span className="h-4 rounded-sm bg-[var(--bg-raised)]">
                    {s.duration_ms !== null && (
                      <span
                        className="block h-4 rounded-sm bg-[var(--accent)]"
                        style={{ width: `${(s.duration_ms / maxMs) * 100}%` }}
                      />
                    )}
                  </span>
                  <span className="text-right font-mono">{s.duration_ms === null ? "not recorded" : ms(s.duration_ms)}</span>
                </button>
                {openStage === s.stage && (
                  <div className="mb-2 ml-1 flex flex-col gap-2">
                    {s.model_calls.length > 0 ? (
                      s.model_calls.map((c) => <ModelCallDetail key={c.id} call={c} />)
                    ) : (
                      <p className="text-xs text-[var(--text-tertiary)]">No model call is attributable to this stage.</p>
                    )}
                  </div>
                )}
              </div>
            ))}
            <div className="grid grid-cols-[9rem_1fr_5.5rem] items-center gap-2 border-t px-1 pt-2 text-xs">
              <span className="font-mono font-medium">e2e (measured)</span>
              <span className="h-4 rounded-sm bg-[var(--bg-raised)]">
                <span className="block h-4 rounded-sm bg-[var(--text-primary)]" style={{ width: `${((wf.e2e_ms ?? 0) / maxMs) * 100}%` }} />
              </span>
              <span className="text-right font-mono font-medium">{ms(wf.e2e_ms)}</span>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-md border p-3">
              <div className="text-xs font-medium text-[var(--text-secondary)]">Prompt input — user utterance (untrusted content)</div>
              <p className="mt-1 text-sm">{wf.user_text ?? "—"}</p>
              <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                Prompt version: {wf.all_model_calls.find((c) => c.role === "persona")?.prompt_version ?? "—"}. The fully
                assembled prompt is not persisted; it is reproducible from content/prompts at that version.
              </p>
              {recording?.url ? (
                <>
                  <audio ref={userAudioRef} src={recording.url} preload="metadata" />
                  <button type="button" onClick={playUserUtterance} className="mt-2 text-xs text-[var(--accent)] hover:text-[var(--accent-hover)]">
                    ▶ Play this utterance
                  </button>
                </>
              ) : (
                <p className="mt-2 text-xs text-[var(--text-tertiary)]">No recording available for this session.</p>
              )}
            </div>
            <div className="rounded-md border p-3">
              <div className="text-xs font-medium text-[var(--text-secondary)]">Response — persona reply</div>
              <p className="mt-1 text-sm">{wf.persona_text ?? "—"}</p>
              {personaUrl ? (
                <audio src={personaUrl} controls autoPlay className="mt-2 w-full" />
              ) : (
                <button
                  type="button"
                  disabled={!wf.persona_text || personaState === "loading"}
                  onClick={() => void loadPersona()}
                  className="mt-2 text-xs text-[var(--accent)] hover:text-[var(--accent-hover)] disabled:opacity-50"
                >
                  {personaState === "loading" ? "Regenerating…" : personaState === "failed" ? "Regeneration failed — retry" : "▶ Regenerate and play (transcript + voice id)"}
                </button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

const SORTABLE: { key: string; label: string }[] = [
  { key: "created_at", label: "When" },
  { key: "tokens_in", label: "In" },
  { key: "tokens_out", label: "Out" },
  { key: "ttft_ms", label: "TTFT" },
  { key: "total_latency_ms", label: "Total" },
  { key: "cost_cents", label: "Cost" },
];

function ModelCallTable() {
  const [filter, setFilter] = useState<ModelCallFilter>({ sort: "created_at", order: "desc", limit: 50, offset: 0 });
  const { data } = useModelCalls(filter);

  function toggleSort(key: string) {
    setFilter((f) => ({ ...f, sort: key, order: f.sort === key && f.order === "desc" ? "asc" : "desc", offset: 0 }));
  }

  const hitRate = data && data.cache_hits + data.cache_misses > 0 ? data.cache_hits / (data.cache_hits + data.cache_misses) : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3 text-xs">
        <label className="flex flex-col gap-1">
          Role
          <select
            className="h-8 rounded-md border bg-[var(--bg-raised)] px-2"
            value={filter.role ?? ""}
            onChange={(e) => setFilter((f) => ({ ...f, role: e.target.value || undefined, offset: 0 }))}
          >
            <option value="">all</option>
            {["persona", "endpointer", "narrator", "planner", "judge", "embedder"].map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          Model contains
          <input
            className="h-8 rounded-md border bg-[var(--bg-raised)] px-2"
            value={filter.model ?? ""}
            onChange={(e) => setFilter((f) => ({ ...f, model: e.target.value || undefined, offset: 0 }))}
          />
        </label>
        <label className="flex flex-col gap-1">
          Cache
          <select
            className="h-8 rounded-md border bg-[var(--bg-raised)] px-2"
            value={filter.cached === undefined ? "" : String(filter.cached)}
            onChange={(e) => setFilter((f) => ({ ...f, cached: e.target.value === "" ? undefined : e.target.value === "true", offset: 0 }))}
          >
            <option value="">all</option>
            <option value="true">hit</option>
            <option value="false">miss</option>
          </select>
        </label>
        <div className="ml-auto text-[var(--text-secondary)]">
          {data && (
            <>
              {data.total.toLocaleString()} calls · cache hit rate{" "}
              <span className="font-mono text-[var(--text-primary)]">{hitRate === null ? "—" : `${(hitRate * 100).toFixed(1)}%`}</span>
            </>
          )}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-[var(--text-tertiary)]">
            <tr>
              <th className="py-2 pr-3">Role</th>
              <th className="py-2 pr-3">Model</th>
              <th className="py-2 pr-3">Prompt</th>
              {SORTABLE.map((s) => (
                <th key={s.key} className="py-2 pr-3">
                  <button type="button" onClick={() => toggleSort(s.key)} className="hover:text-[var(--text-primary)]">
                    {s.label}
                    {filter.sort === s.key ? (filter.order === "desc" ? " ↓" : " ↑") : ""}
                  </button>
                </th>
              ))}
              <th className="py-2 pr-3">Cache</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {(data?.items ?? []).map((c) => (
              <tr key={c.id} className="border-t">
                <td className="py-1.5 pr-3">{c.role}</td>
                <td className="max-w-48 truncate py-1.5 pr-3">{c.model}</td>
                <td className="py-1.5 pr-3">{c.prompt_version ?? "—"}</td>
                <td className="py-1.5 pr-3">{new Date(c.created_at).toLocaleString()}</td>
                <td className="py-1.5 pr-3">{c.tokens_in}</td>
                <td className="py-1.5 pr-3">{c.tokens_out}</td>
                <td className="py-1.5 pr-3">{ms(c.ttft_ms)}</td>
                <td className="py-1.5 pr-3">{ms(c.total_latency_ms)}</td>
                <td className="py-1.5 pr-3">{cents(c.cost_cents)}</td>
                <td className={clsx("py-1.5 pr-3", c.cached ? "text-[var(--accent)]" : "text-[var(--text-tertiary)]")}>{c.cached ? "hit" : "miss"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex justify-end gap-2 text-xs">
        <button
          type="button"
          disabled={(filter.offset ?? 0) === 0}
          onClick={() => setFilter((f) => ({ ...f, offset: Math.max(0, (f.offset ?? 0) - 50) }))}
          className="rounded border px-2 py-1 disabled:opacity-50"
        >
          Previous
        </button>
        <button
          type="button"
          disabled={!data || (filter.offset ?? 0) + 50 >= data.total}
          onClick={() => setFilter((f) => ({ ...f, offset: (f.offset ?? 0) + 50 }))}
          className="rounded border px-2 py-1 disabled:opacity-50"
        >
          Next
        </button>
      </div>
    </div>
  );
}

function CostPanel() {
  const { data } = useCostPanel();
  if (!data) return <div className="h-24 animate-pulse rounded bg-[var(--bg-raised)]" />;
  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Actual spend, scoring (judge calls)" value={cents(data.scoring_actual_cents)} emphasis />
        <Stat label={`Counterfactual — every score from ${data.frontier.model}`} value={cents(data.counterfactual_cents)} emphasis />
        <Stat label="Ratio" value={data.ratio === null ? "not yet measured" : `${data.ratio.toFixed(1)}×`} emphasis />
        <Stat label="Actual spend, all roles" value={cents(data.actual_total_cents)} />
      </div>
      <p className="text-xs text-[var(--text-tertiary)]">
        Counterfactual = {data.turn_scores.toLocaleString()} turn_scores × measured mean judge tokens × ${data.frontier.input_usd_per_mtok}/$
        {data.frontier.output_usd_per_mtok} per MTok ({data.frontier.model} list price as of {data.frontier.as_of}).
      </p>
      <div className="grid gap-4 md:grid-cols-3">
        {(
          [
            ["Per month", data.per_month.map((r) => [r.month.slice(0, 7), r.cents] as const)],
            ["Per user (top 20)", data.per_user.map((r) => [r.user, r.cents] as const)],
            ["Per session (top 20)", data.per_session.map((r) => [r.session_id.slice(0, 8), r.cents] as const)],
          ] as const
        ).map(([title, rows]) => (
          <div key={title}>
            <div className="text-xs font-medium text-[var(--text-secondary)]">{title}</div>
            <ul className="mt-1 max-h-48 overflow-y-auto text-xs">
              {rows.map(([k, v]) => (
                <li key={k} className="flex justify-between border-t py-1 font-mono">
                  <span className="truncate pr-2">{k}</span>
                  <span>{cents(v)}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Phase 6 TASK 6.1 — ordered top to bottom exactly as the spec lists it. */
export function ObservabilityDashboard() {
  const [filter, setFilter] = useState<LatencyFilter>({ days: 30 });
  const latency = useLatencyHeader(filter);
  const stages = useStageBreakdown(filter);

  if (latency.error instanceof ApiError && latency.error.status === 403) {
    return <div className="p-8 text-center text-sm text-[var(--text-secondary)]">Admins only.</div>;
  }
  const d = latency.data;
  const overBudget = d?.overall.p95 != null && d.overall.p95 > d.target_p95_ms;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
      <div>
        <h1 className="text-lg font-medium">Observability</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">End of speech → first audible word. Budget: p95 ≤ 1400 ms.</p>
      </div>

      <Section title="Latency — end-of-speech to first audio" subtitle="Queried directly from latency_events where stage = 'e2e'. Percentiles do not add; this is not a sum of stages.">
        <div className="mb-4 flex flex-wrap gap-3 text-xs">
          <label className="flex flex-col gap-1">
            Window
            <select className="h-8 rounded-md border bg-[var(--bg-raised)] px-2" value={filter.days} onChange={(e) => setFilter((f) => ({ ...f, days: Number(e.target.value) }))}>
              {[1, 7, 30, 90, 365].map((n) => (
                <option key={n} value={n}>
                  last {n} day{n > 1 ? "s" : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            Scenario family
            <select className="h-8 rounded-md border bg-[var(--bg-raised)] px-2" value={filter.family ?? ""} onChange={(e) => setFilter((f) => ({ ...f, family: e.target.value || undefined }))}>
              <option value="">all</option>
              {(d?.families ?? []).map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            Host class
            <select className="h-8 rounded-md border bg-[var(--bg-raised)] px-2" value={filter.host_class ?? ""} onChange={(e) => setFilter((f) => ({ ...f, host_class: e.target.value || undefined }))}>
              <option value="">all</option>
              {(d?.host_classes ?? []).map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
        </div>
        {d ? (
          <>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Stat label="p50" value={ms(d.overall.p50)} />
              <Stat label="p90" value={ms(d.overall.p90)} />
              <div>
                <div className="text-xs text-[var(--text-tertiary)]">p95 (target 1400 ms)</div>
                <div className={clsx("font-mono text-xl", overBudget ? "text-[var(--danger)]" : "text-[var(--accent)]")}>{ms(d.overall.p95)}</div>
              </div>
              <Stat label="turns measured" value={d.overall.n.toLocaleString()} />
            </div>
            <div className="mt-4">
              {d.series.length > 0 ? <LatencyChart data={d} /> : <p className="text-sm text-[var(--text-tertiary)]">No e2e events in this window.</p>}
            </div>
          </>
        ) : (
          <div className="h-48 animate-pulse rounded bg-[var(--bg-raised)]" />
        )}
      </Section>

      <Section title="Stage breakdown" subtitle="Pipeline order. Use these to find which component to attack — not to compute the end-to-end number.">
        {stages.data ? (
          <div className="flex flex-col gap-4">
            <StageStack rows={stages.data} metric="p50" />
            <StageStack rows={stages.data} metric="p95" />
            <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
              {stages.data.map((s, i) => (
                <div key={s.stage} className="flex items-center gap-2">
                  <span className={clsx("h-3 w-3 shrink-0 rounded-sm", STAGE_SHADES[i % STAGE_SHADES.length])} />
                  <span className="font-mono">{s.stage}</span>
                  <span className="ml-auto font-mono text-[var(--text-secondary)]">
                    {s.n === 0 ? "no data" : `${Math.round(s.p50 ?? 0)} / ${Math.round(s.p95 ?? 0)}`}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="h-24 animate-pulse rounded bg-[var(--bg-raised)]" />
        )}
      </Section>

      <Section title="Turn waterfall" subtitle="Select a turn; click a stage for its model call. User audio is cut from the stored recording; persona audio is regenerated from transcript + voice id (never stored).">
        <Waterfall />
      </Section>

      <Section title="Model calls" subtitle="Every invocation. The cache column is the evidence that prefix caching is actually hitting.">
        <ModelCallTable />
      </Section>

      <Section title="Cost" subtitle="Actual spend beside the counterfactual had every score come from a frontier model.">
        <CostPanel />
      </Section>
    </div>
  );
}
