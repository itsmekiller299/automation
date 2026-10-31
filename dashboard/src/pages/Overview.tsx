import {
  ArrowRight,
  Gauge,
  LifeBuoy,
  MessagesSquare,
  Sparkles,
  Timer,
} from "lucide-react";
import { useCallback, useState } from "react";
import { Link } from "react-router-dom";

import { ConfidenceChart, IntentBars, VolumeChart } from "../components/Charts";
import { ChannelBadge } from "../components/ChannelBadge";
import { PageHeader, RefreshButton } from "../components/PageHeader";
import { EmptyState, ErrorState, SectionCard } from "../components/Section";
import { StatCard } from "../components/StatCard";
import { api } from "../lib/api";
import { compactNumber, percent, relativeTime, secondsAgo } from "../lib/format";
import { usePolling } from "../lib/hooks";
import type {
  ConfidenceBucket,
  Handoff,
  IntentStat,
  Overview,
  VolumePoint,
} from "../lib/types";

interface OverviewData {
  overview: Overview;
  intents: IntentStat[];
  volume: VolumePoint[];
  confidence: ConfidenceBucket[];
  handoffs: Handoff[];
}

const RANGES = [7, 14, 30];

export default function OverviewPage() {
  const [days, setDays] = useState(7);

  const loader = useCallback(async (): Promise<OverviewData> => {
    const [overview, intents, volume, confidence, handoffs] = await Promise.all([
      api.overview(days),
      api.intents(days),
      api.volume(days),
      api.confidence(days),
      api.handoffs({ limit: 5 }),
    ]);
    return { overview, intents, volume, confidence, handoffs };
  }, [days]);

  const { data, error, loading, refreshing, updatedAt, refresh } = usePolling(
    loader,
    30_000,
    [days],
  );

  const overview = data?.overview;

  return (
    <div>
      <PageHeader
        eyebrow="Aurora Living · Service desk"
        title="The room, at a glance."
        description="What the assistant handled, what it could not, and where a human stepped in. Numbers refresh quietly every 30 seconds."
        actions={
          <>
            <div className="flex rounded-xl border border-line bg-panel p-1">
              {RANGES.map((range) => (
                <button
                  key={range}
                  type="button"
                  onClick={() => setDays(range)}
                  className={`rounded-lg px-2.5 py-1.5 text-[11px] font-bold transition-colors ${
                    days === range ? "bg-night text-paper" : "text-muted hover:text-ink"
                  }`}
                >
                  {range}d
                </button>
              ))}
            </div>
            <RefreshButton onClick={refresh} refreshing={refreshing} />
          </>
        }
      />

      {error && <ErrorState error={error} onRetry={refresh} />}

      {!error && loading && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="surface h-[150px] animate-pulse bg-line/20" />
          ))}
        </div>
      )}

      {!error && !loading && data && overview && (
        <div className="space-y-4">
          {overview.open_handoffs > 0 && (
            <Link
              to="/handoffs"
              className="group flex flex-col gap-2 rounded-card border border-clay/25 bg-clay-soft/70 px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between"
            >
              <span className="flex items-center gap-3">
                <span className="grid h-7 w-7 place-items-center rounded-full bg-clay text-paper">
                  <LifeBuoy size={14} />
                </span>
                <span className="text-[12px] font-semibold text-ink">
                  {overview.open_handoffs} conversation
                  {overview.open_handoffs === 1 ? "" : "s"} waiting for a human
                </span>
              </span>
              <span className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.08em] text-clay">
                Open queue <ArrowRight size={13} className="transition-transform group-hover:translate-x-0.5" />
              </span>
            </Link>
          )}

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Conversations"
              value={compactNumber(overview.conversations)}
              icon={MessagesSquare}
              hint={`${overview.active_conversations} active · ${compactNumber(
                overview.inbound_messages,
              )} inbound messages`}
            />
            <StatCard
              label="Bot resolution"
              value={percent(overview.resolution_rate)}
              icon={Sparkles}
              tone="moss"
              hint={`${overview.bot_resolved} closed without escalation`}
            />
            <StatCard
              label="Handoff rate"
              value={percent(overview.handoff_rate)}
              icon={LifeBuoy}
              tone={overview.handoff_rate > 0.2 ? "danger" : "amber"}
              hint={`${overview.handoffs} handoffs · ${overview.open_handoffs} still open`}
            />
            <StatCard
              label="Avg confidence"
              value={overview.avg_confidence === null ? "—" : overview.avg_confidence.toFixed(2)}
              icon={Gauge}
              tone={
                overview.avg_confidence !== null && overview.avg_confidence >= 0.9
                  ? "moss"
                  : "amber"
              }
              hint="Calibrated model confidence; below 0.80 routes to a human."
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-12">
            <SectionCard
              eyebrow="Traffic"
              title="Message volume"
              className="xl:col-span-8"
              action={
                <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-muted">
                  <Timer size={12} /> {days} days
                </span>
              }
            >
              <VolumeChart data={data.volume} />
            </SectionCard>

            <SectionCard
              eyebrow="Understanding"
              title="Intent mix"
              className="xl:col-span-4"
              action={
                <Link
                  to="/model"
                  className="text-[10px] font-bold uppercase tracking-[0.08em] text-clay hover:text-ink"
                >
                  Model health
                </Link>
              }
            >
              <IntentBars data={data.intents} />
            </SectionCard>
          </div>

          <div className="grid gap-4 xl:grid-cols-12">
            <SectionCard
              eyebrow="Human queue"
              title="Waiting for a person"
              className="xl:col-span-7"
              bodyClassName="p-0"
              action={
                <Link
                  to="/handoffs"
                  className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-[0.08em] text-clay hover:text-ink"
                >
                  All handoffs <ArrowRight size={12} />
                </Link>
              }
            >
              {data.handoffs.length === 0 ? (
                <EmptyState
                  compact
                  title="Queue is clear"
                  description="No conversations are waiting for a human right now."
                  icon={LifeBuoy}
                />
              ) : (
                <div className="divide-y divide-line">
                  {data.handoffs.map((handoff) => (
                    <Link
                      key={handoff.id}
                      to={`/inbox?c=${handoff.conversation_id}`}
                      className="group flex items-start gap-3 px-5 py-4 transition-colors hover:bg-paper/70"
                    >
                      <span
                        className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                          handoff.priority === "urgent"
                            ? "bg-danger"
                            : handoff.priority === "high"
                              ? "bg-amber"
                              : "bg-moss"
                        }`}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                          <span className="text-[13px] font-semibold text-ink">
                            {handoff.customer_name || "Unknown customer"}
                          </span>
                          <ChannelBadge channel={handoff.channel || "whatsapp"} />
                          <span className="text-[10px] text-muted">
                            {handoff.reason.replace(/_/g, " ")}
                          </span>
                        </div>
                        <p className="mt-1 truncate text-[11px] text-muted">
                          {handoff.last_message || "No message preview available."}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="text-[10px] font-semibold text-muted">
                          {relativeTime(handoff.created_at)}
                        </p>
                        <span className="mt-1 inline-block text-[10px] font-bold uppercase tracking-[0.06em] text-clay opacity-0 transition-opacity group-hover:opacity-100">
                          Open
                        </span>
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </SectionCard>

            <SectionCard
              eyebrow="Calibration"
              title="Confidence distribution"
              className="xl:col-span-5"
              action={
                <span className="text-[10px] font-semibold text-muted">
                  {overview.pending_feedback} corrections queued
                </span>
              }
            >
              <ConfidenceChart data={data.confidence} />
              <p className="mt-4 border-t border-line pt-3 text-[10px] leading-4 text-muted">
                Predictions left of the dashed line fall below the 0.80 threshold and
                are handed to a person. Temperature scaling keeps these scores honest.
              </p>
            </SectionCard>
          </div>

          <p className="pb-2 text-right text-[10px] text-muted">
            {updatedAt ? `Updated ${secondsAgo(updatedAt)}` : "Waiting for data"}
          </p>
        </div>
      )}
    </div>
  );
}
