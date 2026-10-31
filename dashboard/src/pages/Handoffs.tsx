import {
  ArrowRight,
  Check,
  ChevronDown,
  Clock,
  LifeBuoy,
  Radio,
  UserRoundPlus,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "../components/Badge";
import { ChannelBadge } from "../components/ChannelBadge";
import { Modal } from "../components/Modal";
import { PageHeader, RefreshButton } from "../components/PageHeader";
import { EmptyState, ErrorState, SectionCard, SkeletonRows } from "../components/Section";
import { useToast } from "../components/Toast";
import { api, ApiError } from "../lib/api";
import {
  ageHours,
  cn,
  priorityTone,
  relativeTime,
  statusTone,
} from "../lib/format";
import { usePolling } from "../lib/hooks";
import type { Handoff } from "../lib/types";

const STATUSES = [
  { value: "", label: "Active queue" },
  { value: "open", label: "Unassigned" },
  { value: "assigned", label: "Assigned" },
  { value: "resolved", label: "Resolved" },
];

function currentAgent(): string {
  try {
    return localStorage.getItem("orbit.agent") || "dashboard";
  } catch {
    return "dashboard";
  }
}

export default function HandoffsPage() {
  const toast = useToast();
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [modal, setModal] = useState<"assign" | "resolve" | null>(null);
  const [target, setTarget] = useState<Handoff | null>(null);
  const [agent, setAgent] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const loader = useMemo(
    () => () => api.handoffs({ status: status || undefined, priority: priority || undefined }),
    [status, priority],
  );
  const { data, error, loading, refreshing, refresh } = usePolling(loader, 20_000, [
    status,
    priority,
  ]);

  const handoffs = data || [];
  const urgent = handoffs.filter((item) => item.priority === "urgent").length;
  const unassigned = handoffs.filter((item) => !item.assigned_to).length;
  const oldest = handoffs.reduce(
    (max, item) => Math.max(max, ageHours(item.created_at)),
    0,
  );

  const runAction = async (action: () => Promise<unknown>, message: string) => {
    setBusy(true);
    try {
      await action();
      toast.push(message);
      setModal(null);
      setTarget(null);
      setAgent("");
      setNote("");
      refresh();
    } catch (caught) {
      toast.push(caught instanceof ApiError ? caught.message : "Action failed.", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Human queue"
        title="Nobody falls through."
        description="Everything the assistant would not guess at, ordered by urgency and age. Assign, add context, and close the loop without leaving the console."
        actions={<RefreshButton onClick={refresh} refreshing={refreshing} />}
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <div className="surface flex items-center gap-4 px-5 py-4">
          <span className="grid h-9 w-9 place-items-center rounded-full bg-clay-soft text-clay">
            <LifeBuoy size={16} />
          </span>
          <div>
            <p className="font-display text-[28px] leading-none text-ink">{handoffs.length}</p>
            <p className="mt-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
              In this view
            </p>
          </div>
        </div>
        <div className="surface flex items-center gap-4 px-5 py-4">
          <span className="grid h-9 w-9 place-items-center rounded-full bg-danger-soft text-danger">
            <Radio size={16} />
          </span>
          <div>
            <p className="font-display text-[28px] leading-none text-ink">{urgent}</p>
            <p className="mt-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
              Urgent · {unassigned} unassigned
            </p>
          </div>
        </div>
        <div className="surface flex items-center gap-4 px-5 py-4">
          <span className="grid h-9 w-9 place-items-center rounded-full bg-amber-soft text-amber">
            <Clock size={16} />
          </span>
          <div>
            <p className="font-display text-[28px] leading-none text-ink">
              {oldest ? `${Math.floor(oldest)}h` : "—"}
            </p>
            <p className="mt-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
              Oldest open handoff
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-12">
        <div className="space-y-3 xl:col-span-8">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <select
                value={status}
                onChange={(event) => setStatus(event.target.value)}
                className="field appearance-none py-1.5 pl-3 pr-8 text-[11px] font-semibold"
              >
                {STATUSES.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={12}
                className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted"
              />
            </div>
            <div className="relative">
              <select
                value={priority}
                onChange={(event) => setPriority(event.target.value)}
                className="field appearance-none py-1.5 pl-3 pr-8 text-[11px] font-semibold"
              >
                <option value="">Any priority</option>
                <option value="urgent">Urgent</option>
                <option value="high">High</option>
                <option value="normal">Normal</option>
                <option value="low">Low</option>
              </select>
              <ChevronDown
                size={12}
                className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted"
              />
            </div>
            <span className="ml-auto text-[10px] font-semibold text-muted">
              {handoffs.length} handoff{handoffs.length === 1 ? "" : "s"}
            </span>
          </div>

          {error && <ErrorState error={error} onRetry={refresh} />}
          {!error && loading && (
            <div className="surface p-5">
              <SkeletonRows rows={4} />
            </div>
          )}
          {!error && !loading && handoffs.length === 0 && (
            <div className="surface">
              <EmptyState
                title={status === "resolved" ? "No resolved handoffs" : "The queue is clear"}
                description={
                  status === "resolved"
                    ? "Resolved handoffs will appear here for audit."
                    : "No conversations need a person right now. The bot is handling what it can prove."
                }
                icon={LifeBuoy}
              />
            </div>
          )}

          {!error &&
            !loading &&
            handoffs.map((handoff) => (
              <article
                key={handoff.id}
                className="surface group overflow-hidden transition-colors hover:border-line-strong"
              >
                <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={cn(
                          "rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.06em]",
                          priorityTone(handoff.priority),
                        )}
                      >
                        {handoff.priority}
                      </span>
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.06em]",
                          statusTone(handoff.status),
                        )}
                      >
                        {handoff.status}
                      </span>
                      {handoff.channel && <ChannelBadge channel={handoff.channel} />}
                      <span className="text-[9px] font-semibold text-muted">
                        {relativeTime(handoff.created_at)}
                      </span>
                    </div>

                    <h3 className="mt-2.5 font-display text-[24px] leading-tight text-ink">
                      {handoff.customer_name || "Unknown customer"}
                    </h3>
                    <p className="mt-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-clay">
                      {handoff.reason.replace(/_/g, " ")}
                    </p>
                    <p className="mt-2 line-clamp-2 max-w-2xl text-[12px] leading-5 text-muted">
                      {handoff.last_message || "No recent message on this thread."}
                    </p>
                    {handoff.note && (
                      <p className="mt-2 rounded-lg border border-line bg-paper px-3 py-2 text-[11px] leading-4 text-ink-soft">
                        {handoff.note}
                      </p>
                    )}
                    <div className="mt-3 flex flex-wrap items-center gap-3 text-[10px] text-muted">
                      <span>
                        {handoff.assigned_to
                          ? `Assigned to ${handoff.assigned_to}`
                          : "Waiting for an owner"}
                      </span>
                      <span>·</span>
                      <span>source: {handoff.source}</span>
                      {handoff.resolved_at && (
                        <>
                          <span>·</span>
                          <span>resolved {relativeTime(handoff.resolved_at)}</span>
                        </>
                      )}
                    </div>
                  </div>

                  <div className="flex shrink-0 flex-wrap items-center gap-2 sm:flex-col sm:items-stretch">
                    <Link
                      to={`/inbox?c=${handoff.conversation_id}`}
                      className="btn-primary px-3 py-1.5 text-[11px]"
                    >
                      Open thread <ArrowRight size={12} />
                    </Link>
                    {handoff.status !== "resolved" && (
                      <>
                        <button
                          type="button"
                          className="btn-secondary px-3 py-1.5 text-[11px]"
                          onClick={() => {
                            setTarget(handoff);
                            setAgent(handoff.assigned_to || currentAgent());
                            setModal("assign");
                          }}
                        >
                          <UserRoundPlus size={12} /> Assign
                        </button>
                        <button
                          type="button"
                          className="btn-secondary px-3 py-1.5 text-[11px]"
                          onClick={() => {
                            setTarget(handoff);
                            setNote("");
                            setAgent(currentAgent());
                            setModal("resolve");
                          }}
                        >
                          <Check size={12} /> Resolve
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </article>
            ))}
        </div>

        <aside className="space-y-4 xl:col-span-4">
          <SectionCard eyebrow="Routing" title="When the bot steps back">
            <ol className="space-y-3.5">
              {[
                ["Confidence below 0.80", "The calibrated intent score is too low to answer safely."],
                ["Frustration or complaint", "Sentiment and complaint intent trigger a human."],
                ["Explicit request", "“Agent”, “human”, or “manager” is honoured immediately."],
                ["Out of scope", "Anything outside verified catalogue, orders, returns, or policy."],
              ].map(([title, text], index) => (
                <li key={title} className="flex gap-3">
                  <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full border border-line text-[9px] font-bold text-muted">
                    {index + 1}
                  </span>
                  <div>
                    <p className="text-[11px] font-semibold text-ink">{title}</p>
                    <p className="mt-0.5 text-[10px] leading-4 text-muted">{text}</p>
                  </div>
                </li>
              ))}
            </ol>
            <p className="mt-4 border-t border-line pt-3 text-[10px] leading-4 text-muted">
              WhatsApp replies outside the 24-hour service window use the approved
              template. Instagram threads fail closed when the window has expired.
            </p>
          </SectionCard>

          <SectionCard eyebrow="Notifications" title="Who hears about it">
            <div className="space-y-3 text-[11px] leading-5 text-muted">
              <div className="flex items-start gap-2.5">
                <Badge tone="moss">Slack</Badge>
                <span>Configured webhook receives reason, priority, and a masked customer handle.</span>
              </div>
              <div className="flex items-start gap-2.5">
                <Badge tone="amber">Email</Badge>
                <span>SMTP recipients get the same handoff summary for after-hours cover.</span>
              </div>
              <div className="flex items-start gap-2.5">
                <Badge tone="clay">Dashboard</Badge>
                <span>Every escalation is persisted here with its full audit trail.</span>
              </div>
            </div>
          </SectionCard>
        </aside>
      </div>

      <Modal
        open={modal === "assign"}
        onClose={() => setModal(null)}
        title="Assign handoff"
        description={
          target
            ? `Give ${target.customer_name || "this customer"} a named owner.`
            : "Give this handoff a named owner."
        }
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setModal(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={!agent.trim() || busy || !target}
              onClick={() =>
                target &&
                runAction(
                  () => api.assignHandoff(target.id, agent.trim()),
                  `Assigned to ${agent.trim()}.`,
                )
              }
            >
              Assign
            </button>
          </>
        }
      >
        <label className="block">
          <span className="eyebrow mb-1.5 block">Agent name</span>
          <input
            value={agent}
            onChange={(event) => setAgent(event.target.value)}
            className="field"
            autoFocus
          />
        </label>
      </Modal>

      <Modal
        open={modal === "resolve"}
        onClose={() => setModal(null)}
        title="Resolve handoff"
        description="This closes the handoff and marks the conversation resolved. Add a note for the audit trail."
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setModal(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={busy || !target}
              onClick={() =>
                target &&
                runAction(
                  () => api.resolveHandoff(target.id, note.trim() || undefined, agent.trim() || undefined),
                  "Handoff resolved.",
                )
              }
            >
              Mark resolved
            </button>
          </>
        }
      >
        <label className="block">
          <span className="eyebrow mb-1.5 block">Resolution note</span>
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            rows={3}
            placeholder="What fixed it?"
            className="field resize-none"
            autoFocus
          />
        </label>
      </Modal>
    </div>
  );
}
