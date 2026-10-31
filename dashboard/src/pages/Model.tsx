import {
  AlertTriangle,
  BrainCircuit,
  Check,
  Database,
  Download,
  ExternalLink,
  FlaskConical,
  Gauge,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { Badge } from "../components/Badge";
import { ConfidenceChart, DriftScale, IntentBars } from "../components/Charts";
import { PageHeader, RefreshButton } from "../components/PageHeader";
import { EmptyState, ErrorState, SectionCard } from "../components/Section";
import { useToast } from "../components/Toast";
import { api, ApiError } from "../lib/api";
import { cn, percent, relativeTime } from "../lib/format";
import { usePolling } from "../lib/hooks";
import type {
  ConfidenceBucket,
  Drift,
  EvaluationReport,
  FeedbackResponse,
  IntentStat,
  Ready,
} from "../lib/types";

interface ModelData {
  ready: Ready | null;
  drift: Drift;
  confidence: ConfidenceBucket[];
  intents: IntentStat[];
  feedback: FeedbackResponse;
  evaluation: EvaluationReport;
}

export default function ModelPage() {
  const toast = useToast();
  const [exporting, setExporting] = useState(false);
  const [marking, setMarking] = useState<string | null>(null);

  const loader = useCallback(async (): Promise<ModelData> => {
    const [ready, drift, confidence, intents, feedback, evaluation] = await Promise.all([
      api.ready().catch(() => null),
      api.drift(),
      api.confidence(14),
      api.intents(14),
      api.feedback("pending"),
      api.evaluation().catch(
        (error): EvaluationReport => ({
          available: false,
          hint: error instanceof ApiError ? error.message : "Evaluation report unavailable.",
        }),
      ),
    ]);
    return { ready, drift, confidence, intents, feedback, evaluation };
  }, []);

  const { data, error, loading, refreshing, refresh } = usePolling(loader, 30_000);
  const report = data?.evaluation.available ? data.evaluation.report : undefined;
  const pending = data?.feedback.items || [];

  const shifts = useMemo(() => {
    if (!data) return [];
    return Object.entries(data.drift.intent_shift)
      .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
      .slice(0, 5);
  }, [data]);

  const exportQueue = async () => {
    setExporting(true);
    try {
      await api.downloadFeedback();
      toast.push("Retraining queue exported as JSONL.");
    } catch (caught) {
      toast.push(caught instanceof ApiError ? caught.message : "Export failed.", "error");
    } finally {
      setExporting(false);
    }
  };

  const markExported = async (id: string) => {
    setMarking(id);
    try {
      await api.markFeedbackExported(id);
      toast.push("Marked as exported.");
      refresh();
    } catch (caught) {
      toast.push(caught instanceof ApiError ? caught.message : "Could not update feedback.", "error");
    } finally {
      setMarking(null);
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Model & learning"
        title="Proof over vibes."
        description="Calibration, held-out metrics, live drift, and the corrections that feed the next training run. If a number is not measured, it says so."
        actions={
          <>
            <button
              type="button"
              onClick={() => void exportQueue()}
              disabled={exporting || !pending.length}
              className="btn-secondary"
            >
              <Download size={14} className={cn(exporting && "animate-pulse")} />
              Export queue
            </button>
            <RefreshButton onClick={refresh} refreshing={refreshing} />
          </>
        }
      />

      {error && <ErrorState error={error} onRetry={refresh} />}
      {!error && loading && (
        <div className="grid gap-4 xl:grid-cols-12">
          <div className="surface h-80 animate-pulse bg-line/20 xl:col-span-8" />
          <div className="surface h-80 animate-pulse bg-line/20 xl:col-span-4" />
        </div>
      )}

      {!error && !loading && data && (
        <div className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-12">
            <SectionCard
              eyebrow="Held-out evaluation"
              title="Intent quality"
              className="xl:col-span-8"
              action={
                report ? (
                  <Badge tone={report.target.met ? "moss" : "danger"} dot>
                    {report.target.met ? "Target met" : "Below target"}
                  </Badge>
                ) : (
                  <Badge tone="amber" dot>
                    Not evaluated
                  </Badge>
                )
              }
            >
              {report ? (
                <>
                  <div className="grid gap-6 sm:grid-cols-[1.2fr_2fr]">
                    <div>
                      <p className="eyebrow">Macro-F1</p>
                      <p className="mt-1 font-display text-[68px] leading-[0.9] tracking-tight text-ink">
                        {report.intent.macro_f1.toFixed(3)}
                      </p>
                      <p className="mt-2 text-[11px] text-muted">
                        Target {report.target.macro_f1.toFixed(2)} ·{" "}
                        {report.records} held-out utterances
                      </p>
                      <div className="mt-5 flex flex-wrap gap-2">
                        <Badge tone="neutral">{report.model_version}</Badge>
                        <Badge tone="neutral">{report.backend}</Badge>
                        <Badge tone="neutral">{report.split}</Badge>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-x-5 gap-y-4 self-start">
                      <Metric label="Accuracy" value={report.intent.accuracy.toFixed(3)} />
                      <Metric label="Weighted F1" value={report.intent.weighted_f1.toFixed(3)} />
                      <Metric label="Entity F1" value={report.entities.f1.toFixed(3)} />
                      <Metric
                        label="Calibration ECE"
                        value={report.calibration.ece_calibrated.toFixed(3)}
                        note={`T = ${report.temperature}`}
                      />
                      <Metric
                        label="Handoff simulation"
                        value={percent(report.handoff_simulation.handoff_rate, 1)}
                        note="below 0.80"
                      />
                      <Metric
                        label="High-confidence acc."
                        value={report.handoff_simulation.accuracy_above_threshold.toFixed(3)}
                      />
                    </div>
                  </div>

                  <div className="mt-6 overflow-x-auto border-t border-line pt-4">
                    <table className="w-full min-w-[560px] border-collapse text-[11px]">
                      <thead>
                        <tr>
                          <th className="table-head pb-2">Intent</th>
                          <th className="table-head pb-2 text-right">Precision</th>
                          <th className="table-head pb-2 text-right">Recall</th>
                          <th className="table-head pb-2 text-right">F1</th>
                          <th className="table-head pb-2 text-right">Support</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(report.intent.per_intent).map(([intent, row]) => (
                          <tr key={intent} className="border-t border-line/70">
                            <td className="py-1.5 font-semibold capitalize text-ink-soft">
                              {intent.replace(/_/g, " ")}
                            </td>
                            <td className="py-1.5 text-right tabular-nums text-muted">
                              {row.precision.toFixed(3)}
                            </td>
                            <td className="py-1.5 text-right tabular-nums text-muted">
                              {row.recall.toFixed(3)}
                            </td>
                            <td
                              className={cn(
                                "py-1.5 text-right font-semibold tabular-nums",
                                row.f1 >= 0.9 ? "text-moss" : "text-amber",
                              )}
                            >
                              {row.f1.toFixed(3)}
                            </td>
                            <td className="py-1.5 text-right tabular-nums text-muted">
                              {row.support}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="mt-3 text-[10px] leading-4 text-muted">{report.data_note}</p>
                </>
              ) : (
                <div className="grid gap-5 sm:grid-cols-[1fr_240px]">
                  <div>
                    <p className="text-[13px] font-semibold text-ink">
                      No evaluation artifact yet.
                    </p>
                    <p className="mt-1.5 max-w-lg text-[11px] leading-5 text-muted">
                      {data.evaluation.hint ||
                        "Train and evaluate the model, then this panel fills with held-out metrics."}
                    </p>
                    <div className="mt-4 space-y-2 rounded-xl border border-line bg-paper p-3 font-mono text-[10px] text-ink-soft">
                      <p>make dataset</p>
                      <p>make train</p>
                      <p>make eval</p>
                    </div>
                  </div>
                  <div className="grid place-items-center rounded-xl border border-dashed border-line bg-paper/60 p-5">
                    <EmptyState
                      compact
                      icon={FlaskConical}
                      title="Awaiting metrics"
                      description="The dashboard will not invent a score."
                    />
                  </div>
                </div>
              )}
            </SectionCard>

            <SectionCard
              eyebrow="Live window · 7 days"
              title="Drift monitor"
              className="xl:col-span-4"
              action={
                <Badge tone={data.drift.flagged ? "danger" : "moss"} dot>
                  {data.drift.flagged ? "Review" : "Stable"}
                </Badge>
              }
            >
              <DriftScale
                value={data.drift.total_variation}
                threshold={data.drift.thresholds.total_variation}
              />
              <p className="mt-4 text-[11px] leading-5 text-muted">{data.drift.note}</p>

              <div className="mt-5 grid grid-cols-2 gap-3">
                <div className="rounded-xl border border-line bg-paper p-3">
                  <p className="text-[9px] font-bold uppercase tracking-[0.08em] text-muted">
                    This week
                  </p>
                  <p className="mt-1 font-display text-[24px] leading-none text-ink">
                    {data.drift.current_window.samples}
                  </p>
                  <p className="mt-1 text-[9px] text-muted">samples</p>
                </div>
                <div className="rounded-xl border border-line bg-paper p-3">
                  <p className="text-[9px] font-bold uppercase tracking-[0.08em] text-muted">
                    Avg confidence
                  </p>
                  <p className="mt-1 font-display text-[24px] leading-none text-ink">
                    {data.drift.current_window.avg_confidence?.toFixed(2) ?? "—"}
                  </p>
                  <p className="mt-1 text-[9px] text-muted">
                    {data.drift.confidence_delta >= 0 ? "+" : ""}
                    {data.drift.confidence_delta.toFixed(3)} vs prior
                  </p>
                </div>
              </div>

              <div className="mt-5">
                <p className="eyebrow mb-2.5">Largest intent shifts</p>
                <div className="space-y-2">
                  {shifts.map(([intent, shift]) => (
                    <div key={intent} className="flex items-center gap-2">
                      <span className="w-28 truncate text-[10px] capitalize text-ink-soft">
                        {intent.replace(/_/g, " ")}
                      </span>
                      <div className="relative h-1.5 flex-1 rounded-full bg-line/60">
                        <span className="absolute left-1/2 top-0 h-full w-px bg-line-strong" />
                        <span
                          className={cn(
                            "absolute top-0 h-full rounded-full",
                            shift >= 0 ? "bg-clay/70" : "bg-moss/60",
                          )}
                          style={{
                            left: shift >= 0 ? "50%" : `${50 - Math.min(50, Math.abs(shift) * 250)}%`,
                            width: `${Math.min(50, Math.abs(shift) * 250)}%`,
                          }}
                        />
                      </div>
                      <span className="w-10 text-right text-[9px] tabular-nums text-muted">
                        {shift >= 0 ? "+" : ""}
                        {(shift * 100).toFixed(1)}
                      </span>
                    </div>
                  ))}
                  {!shifts.length && (
                    <p className="text-[10px] text-muted">Not enough history to compare.</p>
                  )}
                </div>
              </div>
            </SectionCard>
          </div>

          <div className="grid gap-4 xl:grid-cols-12">
            <SectionCard
              eyebrow="Calibration"
              title="Confidence distribution"
              className="xl:col-span-5"
              action={<Gauge size={15} className="text-muted" />}
            >
              <ConfidenceChart data={data.confidence} threshold={0.8} />
              <div className="mt-4 flex items-start gap-2 border-t border-line pt-3 text-[10px] leading-4 text-muted">
                <ShieldCheck size={13} className="mt-0.5 shrink-0 text-moss" />
                Temperature scaling is fitted on validation data after early stopping.
                It changes confidence, never the predicted class.
              </div>
            </SectionCard>

            <SectionCard
              eyebrow="Traffic"
              title="Intent mix · 14 days"
              className="xl:col-span-7"
              action={<BrainCircuit size={15} className="text-muted" />}
            >
              <IntentBars data={data.intents} />
            </SectionCard>
          </div>

          <SectionCard
            eyebrow="Feedback loop"
            title="Corrections waiting to train"
            action={
              <button
                type="button"
                onClick={() => void exportQueue()}
                className="btn-secondary px-3 py-1.5 text-[11px]"
                disabled={!pending.length || exporting}
              >
                <Download size={12} /> Download JSONL
              </button>
            }
            bodyClassName="p-0"
          >
            {pending.length === 0 ? (
              <EmptyState
                compact
                title="No pending corrections"
                description="When an agent fixes an intent in the inbox, it lands here for the next training run."
                icon={Database}
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] border-collapse text-[11px]">
                  <thead className="bg-paper/70">
                    <tr>
                      <th className="table-head px-5 py-3">Utterance</th>
                      <th className="table-head px-3 py-3">Predicted</th>
                      <th className="table-head px-3 py-3">Corrected</th>
                      <th className="table-head px-3 py-3">Agent</th>
                      <th className="table-head px-3 py-3">When</th>
                      <th className="table-head px-5 py-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pending.map((item) => (
                      <tr key={item.id} className="border-t border-line/70">
                        <td className="max-w-[340px] px-5 py-3">
                          <p className="truncate text-ink-soft">{item.utterance}</p>
                        </td>
                        <td className="px-3 py-3">
                          <span className="text-[10px] text-muted">{item.predicted_intent}</span>
                        </td>
                        <td className="px-3 py-3">
                          <span className="inline-flex items-center gap-1 rounded-full bg-moss-soft px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.04em] text-moss">
                            <Check size={9} /> {item.corrected_intent}
                          </span>
                        </td>
                        <td className="px-3 py-3 text-muted">{item.agent || "—"}</td>
                        <td className="px-3 py-3 text-muted">{relativeTime(item.created_at)}</td>
                        <td className="px-5 py-3 text-right">
                          <button
                            type="button"
                            onClick={() => void markExported(item.id)}
                            disabled={marking === item.id}
                            className="text-[10px] font-bold uppercase tracking-[0.06em] text-clay hover:text-ink disabled:opacity-40"
                          >
                            Mark exported
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SectionCard>

          <div className="grid gap-4 md:grid-cols-3">
            <InfoTile
              icon={BrainCircuit}
              label="Intent model"
              value={data.ready?.nlu || "unknown"}
              detail="Loaded from the NLU pipeline; falls back to rules if weights are absent."
            />
            <InfoTile
              icon={Database}
              label="Retrieval"
              value={data.ready?.rag || "unknown"}
              detail="Grounded FAQ answers only. Semantic search with a lexical fallback."
            />
            <InfoTile
              icon={AlertTriangle}
              label="Environment"
              value={data.ready?.environment || "unknown"}
              detail={`Queue: ${data.ready?.queue || "unknown"} · outbound: ${
                data.ready?.outbound_mode || "unknown"
              }`}
            />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-line bg-panel px-5 py-4">
            <p className="text-[11px] leading-5 text-muted">
              Retraining loop: export corrected JSONL → merge into the stratified dataset →
              retrain → re-evaluate → export ONNX → restart the API.
            </p>
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-[0.08em] text-clay hover:text-ink"
            >
              API docs <ExternalLink size={11} />
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div>
      <p className="eyebrow">{label}</p>
      <p className="mt-1 text-[20px] font-semibold tracking-tight text-ink">{value}</p>
      {note && <p className="mt-0.5 text-[9px] text-muted">{note}</p>}
    </div>
  );
}

function InfoTile({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: typeof RefreshCw;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="surface p-4">
      <div className="flex items-center justify-between">
        <p className="eyebrow">{label}</p>
        <Icon size={14} className="text-muted" />
      </div>
      <p className="mt-3 truncate text-[14px] font-semibold text-ink">{value}</p>
      <p className="mt-1.5 text-[10px] leading-4 text-muted">{detail}</p>
    </div>
  );
}
