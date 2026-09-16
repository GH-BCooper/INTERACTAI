"use client";

import { clsx } from "clsx";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import {
  useCompareVersions,
  useEvalCases,
  useModelVersions,
  useRegistryStatusChange,
  useRegression,
  useScoreVersions,
  useSpeechPanel,
} from "@/lib/api/hooks";
import type { EvalCaseRow, EvalRunRow, ModelVersionRow, RegressionOut } from "@/lib/api/types";

function fmt(v: unknown, digits = 3): string {
  if (v === null || v === undefined) return "not yet measured";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(digits);
  return String(v);
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

function Registry() {
  const { data } = useModelVersions();
  const change = useRegistryStatusChange();
  const [pending, setPending] = useState<{ action: "promote" | "rollback"; version: ModelVersionRow } | null>(null);
  const error = change.error instanceof ApiError ? change.error.message : null;

  return (
    <div className="flex flex-col gap-3">
      {data && data.length === 0 && (
        <p className="text-sm text-[var(--text-tertiary)]">No scorer versions registered yet. The prompted scorer runs as the unregistered baseline.</p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-[var(--text-tertiary)]">
            <tr>
              {["Role", "Name", "Base model", "Adapter", "Dataset rev", "Headline metrics", "Status", ""].map((h) => (
                <th key={h} className="py-2 pr-3">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((v) => (
              <tr key={v.id} className="border-t align-top">
                <td className="py-2 pr-3">{v.role}</td>
                <td className="py-2 pr-3 font-medium">{v.name}</td>
                <td className="py-2 pr-3 font-mono">{v.base_model}</td>
                <td className="py-2 pr-3 font-mono">{v.adapter_key ?? "—"}</td>
                <td className="py-2 pr-3 font-mono">{v.dataset_revision_hash?.slice(0, 10) ?? "—"}</td>
                <td className="py-2 pr-3 font-mono">
                  {Object.entries(v.metrics).length === 0
                    ? "—"
                    : Object.entries(v.metrics)
                        .slice(0, 4)
                        .map(([k, val]) => `${k}=${fmt(val)}`)
                        .join(" · ")}
                </td>
                <td className="py-2 pr-3">
                  <span className={clsx("rounded px-1.5 py-0.5", v.status === "active" ? "bg-[var(--accent)] text-[var(--text-on-accent)]" : "bg-[var(--bg-raised)]")}>
                    {v.status}
                  </span>
                </td>
                <td className="py-2 pr-3 text-right">
                  {(v.status === "candidate" || v.status === "training") && (
                    <Button size="sm" variant="secondary" onClick={() => setPending({ action: "promote", version: v })}>
                      Promote
                    </Button>
                  )}
                  {v.status === "retired" && (
                    <Button size="sm" variant="ghost" onClick={() => setPending({ action: "rollback", version: v })}>
                      Roll back to this
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pending && (
        <div role="alertdialog" aria-label="Confirm status change" className="rounded-md border bg-[var(--bg-raised)] p-4 text-sm">
          <p>
            {pending.action === "promote" ? "Promote" : "Roll back to"} <strong>{pending.version.name}</strong> as the active{" "}
            {pending.version.role}? This is a status change only — the current active version becomes <em>retired</em>, nothing is redeployed.
            {pending.action === "promote" && " Promotion is refused unless every published test-split seed beats the current active version."}
          </p>
          <div className="mt-3 flex gap-2">
            <Button
              size="sm"
              variant={pending.action === "promote" ? "primary" : "danger"}
              disabled={change.isPending}
              onClick={() => change.mutate({ action: pending.action, id: pending.version.id }, { onSettled: () => setPending(null) })}
            >
              Confirm
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setPending(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
      {error && <p className="text-xs text-[var(--danger)]">{error}</p>}
    </div>
  );
}

function SuiteResults({ runs }: { runs: EvalRunRow[] }) {
  const scorer = runs.filter((r) => r.suite !== "speech" && r.suite !== "persona");
  const latest = [...scorer].reverse();
  return latest.length === 0 ? (
    <p className="text-sm text-[var(--text-tertiary)]">No scorer evaluation runs recorded yet.</p>
  ) : (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-[var(--text-tertiary)]">
          <tr>
            {["When", "Configuration", "Split", "QWK", "MAE", "Spearman", "Adjacent", "ECE", "Cost/turn", "Dataset rev"].map((h) => (
              <th key={h} className="py-2 pr-3">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="font-mono">
          {latest.slice(0, 30).map((r) => (
            <tr key={r.id} className="border-t">
              <td className="py-1.5 pr-3">{r.created_at.slice(0, 10)}</td>
              <td className="py-1.5 pr-3">{r.configuration}</td>
              <td className="py-1.5 pr-3">{r.split}{r.published ? " (published)" : ""}</td>
              <td className="py-1.5 pr-3">{fmt(r.qwk)}</td>
              <td className="py-1.5 pr-3">{fmt(r.mae)}</td>
              <td className="py-1.5 pr-3">{fmt(r.spearman)}</td>
              <td className="py-1.5 pr-3">{fmt(r.adjacent_accuracy)}</td>
              <td className="py-1.5 pr-3">{fmt(r.ece)}</td>
              <td className="py-1.5 pr-3">{r.mean_cost_cents === null ? "—" : `${r.mean_cost_cents.toFixed(4)}¢`}</td>
              <td className="py-1.5 pr-3">{r.dataset_revision_hash.slice(0, 10)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CaseGrid() {
  const { data } = useEvalCases();
  const [sortDesc, setSortDesc] = useState(true);
  const rows = useMemo(() => {
    const items: EvalCaseRow[] = [...(data?.items ?? [])];
    items.sort((a, b) => (sortDesc ? b.disagreement - a.disagreement : a.disagreement - b.disagreement));
    return items;
  }, [data, sortDesc]);

  if (data && rows.length === 0) {
    return <p className="text-sm text-[var(--text-tertiary)]">No turns have both a human label and a model score yet.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-[var(--text-tertiary)]">
          <tr>
            <th className="py-2 pr-3">Turn</th>
            <th className="py-2 pr-3">Criterion</th>
            <th className="py-2 pr-3">Human label(s)</th>
            <th className="py-2 pr-3">Model score</th>
            <th className="py-2 pr-3">
              <button type="button" onClick={() => setSortDesc((s) => !s)} className="hover:text-[var(--text-primary)]">
                Disagreement {sortDesc ? "↓" : "↑"}
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={`${c.turn_id}-${c.criterion_key}-${c.model_version}`} className="border-t align-top">
              <td className="max-w-80 py-1.5 pr-3">
                <Link href={`/app/sessions/${c.session_id}?criterion=${c.criterion_key}`} className="text-[var(--accent)] hover:text-[var(--accent-hover)]">
                  {c.turn_text ? `“${c.turn_text.slice(0, 80)}${c.turn_text.length > 80 ? "…" : ""}”` : c.turn_id.slice(0, 8)}
                </Link>
              </td>
              <td className="py-1.5 pr-3 font-mono">{c.criterion_key}</td>
              <td className="py-1.5 pr-3 font-mono">
                {c.human_scores.join(", ")} (mean {c.human_mean.toFixed(1)})
              </td>
              <td className="py-1.5 pr-3 font-mono">
                {c.model_score} <span className="text-[var(--text-tertiary)]">@{c.model_version} · conf {c.confidence.toFixed(2)}</span>
              </td>
              <td className="py-1.5 pr-3 font-mono">
                <span className={clsx(c.disagreement >= 2 && "text-[var(--danger)]")}>{c.disagreement.toFixed(1)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const REGRESSION_METRICS = ["qwk", "mae", "ece"] as const;
const W = 640;
const H = 180;
const PAD = { l: 40, r: 12, t: 16, b: 22 };

function RegressionChart({ data }: { data: RegressionOut }) {
  const [metric, setMetric] = useState<(typeof REGRESSION_METRICS)[number]>("qwk");
  const runs = data.runs.filter((r) => r[metric] !== null);
  const times = [...runs.map((r) => Date.parse(r.created_at)), ...data.deployments.map((d) => Date.parse(d.created_at))];
  if (times.length === 0) {
    return <p className="text-sm text-[var(--text-tertiary)]">No runs or deployments recorded yet.</p>;
  }
  const t0 = Math.min(...times);
  const t1 = Math.max(...times, t0 + 1);
  const vals = runs.map((r) => r[metric] as number);
  const vMin = Math.min(0, ...vals);
  const vMax = Math.max(1, ...vals);
  const x = (t: number) => PAD.l + ((t - t0) / (t1 - t0)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - (v - vMin) / (vMax - vMin)) * (H - PAD.t - PAD.b);
  const byConfig = new Map<string, EvalRunRow[]>();
  for (const r of runs) byConfig.set(`${r.configuration}@${r.prompt_version ?? "-"}`, [...(byConfig.get(`${r.configuration}@${r.prompt_version ?? "-"}`) ?? []), r]);

  return (
    <div>
      <div className="mb-2 flex gap-2 text-xs">
        {REGRESSION_METRICS.map((m) => (
          <button key={m} type="button" onClick={() => setMetric(m)} className={clsx("rounded px-2 py-1", m === metric ? "bg-[var(--bg-raised)] text-[var(--text-primary)]" : "text-[var(--text-secondary)]")}>
            {m.toUpperCase()}
          </button>
        ))}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`${metric} across model and prompt versions over time, with deployment markers`}>
        <line x1={PAD.l} x2={W - PAD.r} y1={H - PAD.b} y2={H - PAD.b} className="stroke-[var(--border)]" />
        {[vMin, vMax].map((v) => (
          <text key={v} x={PAD.l - 6} y={y(v) + 4} textAnchor="end" className="fill-[var(--text-tertiary)] text-[10px]">
            {v.toFixed(1)}
          </text>
        ))}
        {data.deployments.map((d) => (
          <g key={d.id}>
            <line x1={x(Date.parse(d.created_at))} x2={x(Date.parse(d.created_at))} y1={PAD.t} y2={H - PAD.b} strokeDasharray="3 3" className="stroke-[var(--danger)]" />
            <text x={x(Date.parse(d.created_at)) + 3} y={PAD.t - 4} className="fill-[var(--danger)] text-[9px]">
              ▼ {d.label}
            </text>
          </g>
        ))}
        {[...byConfig.entries()].map(([key, rs]) => (
          <g key={key}>
            <polyline points={rs.map((r) => `${x(Date.parse(r.created_at))},${y(r[metric] as number)}`).join(" ")} fill="none" strokeWidth={1.5} className="stroke-[var(--accent)]" />
            {rs.map((r) => (
              <circle key={r.id} cx={x(Date.parse(r.created_at))} cy={y(r[metric] as number)} r={3} className="fill-[var(--accent)]">
                <title>{`${key} · ${metric}=${fmt(r[metric])} · ${r.created_at.slice(0, 10)} · rev ${r.dataset_revision_hash.slice(0, 8)}`}</title>
              </circle>
            ))}
          </g>
        ))}
      </svg>
      <p className="mt-1 text-xs text-[var(--text-tertiary)]">Dashed red lines are deployments (promotions, rollbacks, prompt and service deploys).</p>
    </div>
  );
}

function Comparison() {
  const { data: versions } = useScoreVersions();
  const [a, setA] = useState<string | null>(null);
  const [b, setB] = useState<string | null>(null);
  const { data } = useCompareVersions(a, b);

  return (
    <div className="flex flex-col gap-3 text-xs">
      <div className="flex flex-wrap gap-3">
        {([["Version A", a, setA], ["Version B", b, setB]] as const).map(([label, value, set]) => (
          <label key={label} className="flex flex-col gap-1">
            {label}
            <select className="h-8 rounded-md border bg-[var(--bg-raised)] px-2 font-mono" value={value ?? ""} onChange={(e) => set(e.target.value || null)}>
              <option value="">choose…</option>
              {(versions ?? []).map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
        ))}
      </div>
      {a && b && a === b && <p className="text-[var(--text-tertiary)]">Pick two different versions.</p>}
      {data && (
        <>
          <p>
            {data.shared_cases} identical cases · <strong>{data.disagreements} disagreements</strong> (shown first)
          </p>
          <div className="max-h-96 overflow-auto">
            <table className="w-full text-left">
              <thead className="text-[var(--text-tertiary)]">
                <tr>
                  <th className="py-2 pr-3">Turn</th>
                  <th className="py-2 pr-3">Criterion</th>
                  <th className="py-2 pr-3">A</th>
                  <th className="py-2 pr-3">B</th>
                  <th className="py-2 pr-3">Gap</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {data.items.map((i) => (
                  <tr key={`${i.turn_id}-${i.criterion_key}`} className={clsx("border-t", i.disagrees && "text-[var(--text-primary)]", !i.disagrees && "text-[var(--text-tertiary)]")}>
                    <td className="py-1 pr-3">{i.turn_id.slice(0, 8)}</td>
                    <td className="py-1 pr-3">{i.criterion_key}</td>
                    <td className="py-1 pr-3">{i.score_a ?? "abstain"}</td>
                    <td className="py-1 pr-3">{i.score_b ?? "abstain"}</td>
                    <td className="py-1 pr-3">{i.gap ?? (i.disagrees ? "—" : "0")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function SpeechPanel() {
  const { data } = useSpeechPanel();
  if (data && data.length === 0) return <p className="text-sm text-[var(--text-tertiary)]">No Level 1 run recorded yet. Run make eval-speech.</p>;
  const keys = ["wer_overall", "wer_accented", "wer_technical", "asr_rtf", "tts_rtf", "endpoint_precision", "endpoint_recall", "endpoint_latency_p50_ms", "ttfa_p50_ms", "ttfa_p95_ms"];
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-[var(--text-tertiary)]">
          <tr>
            <th className="py-2 pr-3">Host class</th>
            {keys.map((k) => (
              <th key={k} className="py-2 pr-3">
                {k}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="font-mono">
          {(data ?? []).map((r) => (
            <tr key={r.id} className="border-t">
              <td className="py-1.5 pr-3">
                {r.host_class ?? "unspecified"}
                <div className="text-[var(--text-tertiary)]">{r.created_at.slice(0, 10)}</div>
              </td>
              {keys.map((k) => (
                <td key={k} className={clsx("py-1.5 pr-3", k.endsWith("rtf") && typeof r.metrics[k] === "number" && (r.metrics[k] as number) > 1 && "text-[var(--danger)]")}>
                  {r.metrics[k] === undefined ? "not yet measured" : fmt(r.metrics[k])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EvalsDashboard() {
  const regression = useRegression();
  if (regression.error instanceof ApiError && regression.error.status === 403) {
    return <div className="p-8 text-center text-sm text-[var(--text-secondary)]">Admins only.</div>;
  }
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
      <div>
        <h1 className="text-lg font-medium">Evaluations</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Every number here is an eval_runs row with its dataset revision. Scores measure performance against the authored rubric — they do not predict hiring outcomes.
        </p>
      </div>
      <Section title="Model registry" subtitle="Promotion and rollback are status changes, with confirmation.">
        <Registry />
      </Section>
      <Section title="Suite results" subtitle="Agreement, error, calibration and cost per configuration.">
        {regression.data ? <SuiteResults runs={regression.data.runs} /> : <div className="h-24 animate-pulse rounded bg-[var(--bg-raised)]" />}
      </Section>
      <Section title="Per-case grid" subtitle="Each row links to the turn in its report, with the human label(s) beside the model score. Sorted by disagreement, largest first.">
        <CaseGrid />
      </Section>
      <Section title="Regression chart" subtitle="Metrics across model and prompt versions over time, with deployment markers.">
        {regression.data ? <RegressionChart data={regression.data} /> : <div className="h-40 animate-pulse rounded bg-[var(--bg-raised)]" />}
      </Section>
      <Section title="Comparison" subtitle="Two versions over identical cases; disagreements first.">
        <Comparison />
      </Section>
      <Section title="Speech components" subtitle="Latest Level 1 run per host class. RTF above 1.0 fails the suite.">
        <SpeechPanel />
      </Section>
    </div>
  );
}
